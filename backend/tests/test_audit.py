"""Audit trail for manual overrides (docs/06_schema_api.md §6.1.4, §6.3.4).

Every ``PUT`` records one row per changed field, plus a ``status`` row when the
verification state actually transitions; ``POST /reject`` records its own
``status`` row. The route returns that history newest-first and is tenant-guarded
like every other receipt route.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.auth import ACCOUNTANT_HEADER
from app.core.database import SessionLocal
from app.models.client import Client
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_audit_log import ReceiptAuditLog
from app.pipeline.ocr_engine import OCRToken
from app.schemas.receipt import ExtractedField, LineItemSchema, ParsedReceiptSchema

ACCOUNTANT_BODY = {
    "business_name": "Kim Guan Hardware",
    "industry_category": "HARDWARE",
}
UPLOAD_URL = "/api/v1/clients/{client_id}/receipts/upload"
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def _tokens() -> list[OCRToken]:
    return [
        OCRToken(
            text=text,
            confidence=confidence,
            bbox=[0.05, 0.05 * i, 0.9, 0.05 * i + 0.03],
            line_num=i,
        )
        for i, (text, confidence) in enumerate(
            [
                ("KIM GUAN HARDWARE", 0.96),
                ("INV-99120", 0.94),
                ('PVC PIPE 2"', 0.91),
                ("14.50", 0.93),
                ("TOTAL 14.50", 0.95),
            ]
        )
    ]


def _parsed() -> ParsedReceiptSchema:
    return ParsedReceiptSchema(
        merchant_name="Kim Guan Hardware",
        invoice_date=date.today() - timedelta(days=3),
        invoice_number="INV-99120",
        subtotal=Decimal("14.50"),
        tax_amount=Decimal("0.00"),
        grand_total=Decimal("14.50"),
        line_items=[
            LineItemSchema(
                line_index=0,
                description='PVC Pipe 2"',
                quantity=Decimal("1.00"),
                unit_price=Decimal("14.50"),
                line_total=Decimal("14.50"),
                confidence=0.93,
                bbox=[0.05, 0.15, 0.9, 0.18],
            )
        ],
        fields=[
            ExtractedField(name="merchant_name", confidence=0.96),
            ExtractedField(name="invoice_date", confidence=0.94),
            ExtractedField(name="grand_total", confidence=0.95),
            ExtractedField(name="subtotal", confidence=0.93),
        ],
    )


@pytest.fixture(autouse=True)
def _storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep uploaded blobs out of the repository working tree."""
    monkeypatch.setenv("KENYALANG_STORAGE_ROOT", str(tmp_path / "storage"))
    return tmp_path / "storage"


@pytest.fixture
def stub_pipeline(monkeypatch: pytest.MonkeyPatch):
    """Replace the OCR + LLM boundary with a deterministic receipt."""

    def install():
        monkeypatch.setattr(
            "app.api.receipts.process_receipt_image", lambda *_a, **_k: _tokens()
        )
        monkeypatch.setattr(
            "app.api.receipts.extract_receipt", lambda _t, **_: _parsed()
        )

    return install


def _create_client(client: TestClient, headers: dict[str, str] | None = None) -> str:
    response = client.post("/api/clients", json=ACCOUNTANT_BODY, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def _upload(
    client: TestClient, client_id: str, headers: dict[str, str] | None = None
) -> str:
    response = client.post(
        UPLOAD_URL.format(client_id=client_id),
        files=[("files", ("receipt.jpg", JPEG_BYTES, "image/jpeg"))],
        headers=headers,
    )
    assert response.status_code == 202
    return response.json()["receipts"][0]["id"]


def _detail_url(client_id: str, receipt_id: str) -> str:
    return f"/api/v1/clients/{client_id}/receipts/{receipt_id}"


def _audit_url(client_id: str, receipt_id: str) -> str:
    return f"{_detail_url(client_id, receipt_id)}/audit"


def _audit_items(client: TestClient, client_id: str, receipt_id: str) -> list[dict]:
    response = client.get(_audit_url(client_id, receipt_id))
    assert response.status_code == 200
    return response.json()["items"]


def _parse_timestamp(value: str) -> datetime:
    """Parse the API's ISO-8601 timestamp regardless of ``Z``/offset rendering."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# --------------------------------------------------------------------------- #
# One row per change
# --------------------------------------------------------------------------- #


def test_successive_updates_log_one_row_per_changed_field(
    client: TestClient, stub_pipeline, _storage_root: Path, accountant_id: uuid.UUID
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload(client, client_id)

    first = client.put(
        _detail_url(client_id, receipt_id), json={"merchant_name": "Uncle Lim Kopi"}
    )
    assert first.status_code == 200
    second = client.put(
        _detail_url(client_id, receipt_id), json={"grand_total": "20.00"}
    )
    assert second.status_code == 200

    with SessionLocal() as db:
        rows = (
            db.execute(
                select(ReceiptAuditLog)
                .where(ReceiptAuditLog.receipt_id == uuid.UUID(receipt_id))
                .order_by(ReceiptAuditLog.created_at)
            )
            .scalars()
            .all()
        )

    by_field: dict[str, list[ReceiptAuditLog]] = {}
    for row in rows:
        by_field.setdefault(row.field_name, []).append(row)

    # Each changed field produced exactly one row -- the second PUT changed one
    # field and did not re-log what the first PUT already recorded.
    assert set(by_field) == {"merchant_name", "grand_total", "status"}
    assert {name: len(group) for name, group in by_field.items()} == {
        "merchant_name": 1,
        "grand_total": 1,
        "status": 1,
    }

    merchant_row = by_field["merchant_name"][0]
    assert merchant_row.old_value == "Kim Guan Hardware"
    assert merchant_row.new_value == "Uncle Lim Kopi"
    assert merchant_row.user_id == accountant_id

    total_row = by_field["grand_total"][0]
    assert total_row.old_value == "14.50"
    assert total_row.new_value == "20.00"

    status_row = by_field["status"][0]
    assert status_row.old_value in {
        ReceiptStatus.STATUS_AUTO_VERIFIED.value,
        ReceiptStatus.STATUS_NEEDS_REVIEW.value,
    }
    assert status_row.new_value == ReceiptStatus.STATUS_VERIFIED.value
    # The receipt auto-verified on upload, so this is the AUTO_VERIFIED path.
    assert status_row.old_value == ReceiptStatus.STATUS_AUTO_VERIFIED.value


# --------------------------------------------------------------------------- #
# Read route shape and ordering
# --------------------------------------------------------------------------- #


def test_audit_route_returns_newest_first_with_uuid_ids(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload(client, client_id)

    for body in (
        {"merchant_name": "Uncle Lim Kopi"},
        {"invoice_number": "INV-00001"},
        {"grand_total": "20.00"},
    ):
        assert (
            client.put(_detail_url(client_id, receipt_id), json=body).status_code
            == 200
        )

    items = _audit_items(client, client_id, receipt_id)

    assert len(items) >= 3
    for item in items:
        # `id` must be a canonical UUID string, not an integer/opaque handle.
        assert uuid.UUID(item["id"]) == uuid.UUID(str(uuid.UUID(item["id"])))
        assert item["created_at"]

    timestamps = [_parse_timestamp(item["created_at"]) for item in items]
    assert timestamps == sorted(timestamps, reverse=True)


# --------------------------------------------------------------------------- #
# Rejections are audited too
# --------------------------------------------------------------------------- #


def test_reject_writes_status_audit_row(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload(client, client_id)

    response = client.post(f"{_detail_url(client_id, receipt_id)}/reject")

    assert response.status_code == 200
    assert response.json()["status"] == ReceiptStatus.STATUS_REJECTED.value

    items = _audit_items(client, client_id, receipt_id)
    status_rows = [item for item in items if item["field_name"] == "status"]
    assert len(status_rows) == 1
    assert status_rows[0]["new_value"] == ReceiptStatus.STATUS_REJECTED.value
    assert status_rows[0]["old_value"] == ReceiptStatus.STATUS_AUTO_VERIFIED.value


# --------------------------------------------------------------------------- #
# Tenancy isolation (§6.3.5)
# --------------------------------------------------------------------------- #


def test_cross_tenant_audit_is_not_found(
    client: TestClient, other_accountant_id: uuid.UUID
) -> None:
    other_headers = {ACCOUNTANT_HEADER: str(other_accountant_id)}
    foreign_client_id = _create_client(client, headers=other_headers)

    with SessionLocal() as db:
        foreign_client = db.get(Client, uuid.UUID(foreign_client_id))
        assert foreign_client is not None
        receipt = Receipt(
            client_id=foreign_client.id,
            original_filename="foreign.jpg",
            storage_path="tenants/foreign/foreign.jpg",
            mime_type="image/jpeg",
            file_size_bytes=64,
            status=ReceiptStatus.STATUS_NEEDS_REVIEW,
            validation_flags=[],
            field_provenance=[],
            ocr_raw_tokens=[],
        )
        db.add(receipt)
        db.commit()
        foreign_receipt_id = str(receipt.id)

    response = client.get(_audit_url(foreign_client_id, foreign_receipt_id))

    assert response.status_code == 404
