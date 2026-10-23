"""Receipt read, image and update endpoints (docs/06_schema_api.md §6.3.2–§6.3.4).

OCR and the LLM are stubbed at the pipeline boundary (same as
``tests/test_receipts_upload.py``): these tests cover the route contracts —
pagination, status filtering, tenancy isolation, blob streaming, audit logging
and the math recomputation on verify — not EasyOCR or a paid model call.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import storage
from app.core.auth import ACCOUNTANT_HEADER
from app.core.database import SessionLocal
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_audit_log import ReceiptAuditLog
from app.pipeline.ocr_engine import OCRToken
from app.schemas.receipt import (
    ExtractedField,
    LineItemSchema,
    ParsedReceiptSchema,
)

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


def _create_client(client: TestClient) -> str:
    response = client.post("/api/clients", json=ACCOUNTANT_BODY)
    assert response.status_code == 201
    return response.json()["id"]


def _upload(client: TestClient, client_id: str, filename: str = "receipt.jpg"):
    return client.post(
        UPLOAD_URL.format(client_id=client_id),
        files=[("files", (filename, JPEG_BYTES, "image/jpeg"))],
    )


def _detail_url(client_id: str, receipt_id: str) -> str:
    return f"/api/v1/clients/{client_id}/receipts/{receipt_id}"


def _image_url(client_id: str, receipt_id: str) -> str:
    return f"{_detail_url(client_id, receipt_id)}/image"


def _upload_one(
    client: TestClient, client_id: str, filename: str = "receipt.jpg"
) -> str:
    response = _upload(client, client_id, filename)
    assert response.status_code == 202
    return response.json()["receipts"][0]["id"]


# --------------------------------------------------------------------------- #
# Inbox list (§6.3.2)
# --------------------------------------------------------------------------- #


def test_list_returns_receipt_with_inbox_shape(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload_one(client, client_id)

    response = client.get(f"/api/v1/clients/{client_id}/receipts")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 50
    assert body["offset"] == 0
    item = body["items"][0]
    uuid.UUID(item["id"])
    assert item["id"] == receipt_id
    assert item["filename"] == "receipt.jpg"
    assert item["merchant_name"] == "Kim Guan Hardware"
    assert item["invoice_date"] == (date.today() - timedelta(days=3)).isoformat()
    # Money must arrive as decimal strings, never JSON floats.
    for field in ("subtotal", "tax_amount", "grand_total", "math_discrepancy"):
        assert isinstance(item[field], str), field
    assert item["grand_total"] == "14.50"
    assert item["math_discrepancy"] == "0.00"
    assert item["status"] == ReceiptStatus.STATUS_AUTO_VERIFIED.value
    assert item["validation_flags"] == []
    assert item["overall_confidence"] > 0.0
    assert item["line_item_count"] == 1
    assert item["image_url"] == _image_url(client_id, receipt_id)


def test_list_status_filter_switches_on_verify(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload_one(client, client_id)
    base = f"/api/v1/clients/{client_id}/receipts"

    # The upload auto-verified, so it already counts under the VERIFIED filter.
    assert client.get(base, params={"status": "NEEDS_REVIEW"}).json()["total"] == 0
    assert client.get(base, params={"status": "VERIFIED"}).json()["total"] == 1
    assert client.get(base, params={"status": "ALL"}).json()["total"] == 1
    assert client.get(base, params={"status": "EXPORTED"}).json()["total"] == 0

    response = client.put(
        _detail_url(client_id, receipt_id),
        json={
            "line_items": [
                {
                    "description": 'PVC Pipe 2"',
                    "quantity": "1.00",
                    "unit_price": "14.50",
                    "line_total": "14.50",
                }
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == ReceiptStatus.STATUS_VERIFIED.value

    assert client.get(base, params={"status": "VERIFIED"}).json()["total"] == 1
    assert client.get(base, params={"status": "ALL"}).json()["total"] == 1
    assert client.get(base, params={"status": "NEEDS_REVIEW"}).json()["total"] == 0
    assert client.get(base, params={"status": "EXPORTED"}).json()["total"] == 0


def test_list_reports_status_counts_for_every_bucket(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    """``status_counts`` is the inbox tab badge: one grouped count, never filtered.

    ``ALL`` must count every row whatever its status settles at (including the
    terminal ones the fixed-size buckets cannot hold), and ``VERIFIED`` is the
    union of the two verified spellings so a marker never reads zero.
    """
    stub_pipeline()
    client_id = _create_client(client)
    _upload_one(client, client_id)
    base = f"/api/v1/clients/{client_id}/receipts"

    counts = client.get(base).json()["status_counts"]
    assert counts["ALL"] == 1
    assert counts["VERIFIED"] == 1
    assert counts["NEEDS_REVIEW"] == 0
    assert counts["EXPORTED"] == 0

    # The active filter must not narrow the counts: asking for one bucket tells
    # the accountant how much work sits in every other bucket.
    filtered = client.get(base, params={"status": "NEEDS_REVIEW"}).json()
    assert filtered["total"] == 0
    assert filtered["status_counts"] == counts


def test_list_limit_and_offset_paginate(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    for index in range(3):
        _upload_one(client, client_id, f"receipt-{index}.jpg")
    base = f"/api/v1/clients/{client_id}/receipts"

    first = client.get(base, params={"limit": 2, "offset": 0}).json()
    second = client.get(base, params={"limit": 2, "offset": 2}).json()

    assert first["total"] == 3
    assert first["limit"] == 2
    assert first["offset"] == 0
    assert len(first["items"]) == 2
    assert len(second["items"]) == 1


def test_list_rejects_unknown_status_filter(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)

    response = client.get(
        f"/api/v1/clients/{client_id}/receipts", params={"status": "BOGUS"}
    )

    assert response.status_code == 422


def test_list_rejects_out_of_range_limit(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    base = f"/api/v1/clients/{client_id}/receipts"

    assert client.get(base, params={"limit": 0}).status_code == 422
    assert client.get(base, params={"limit": 201}).status_code == 422


# --------------------------------------------------------------------------- #
# Detail (§6.3.3)
# --------------------------------------------------------------------------- #


def test_detail_returns_fields_line_items_and_tokens(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload_one(client, client_id)

    response = client.get(_detail_url(client_id, receipt_id))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == receipt_id
    assert body["client_id"] == client_id
    assert body["status"] == ReceiptStatus.STATUS_AUTO_VERIFIED.value
    assert body["filename"] == "receipt.jpg"

    names = {field["name"] for field in body["fields"]}
    assert {"merchant_name", "grand_total", "invoice_date", "subtotal"} <= names
    for field in body["fields"]:
        assert isinstance(field["confidence"], float)

    assert len(body["line_items"]) == 1
    line = body["line_items"][0]
    assert line["line_index"] == 0
    assert line["description"] == 'PVC Pipe 2"'
    assert line["quantity"] == "1.00"
    assert line["line_total"] == "14.50"
    assert line["unit_price"] == "14.50"
    assert line["confidence"] == pytest.approx(0.93, abs=0.001)
    assert line["bbox"] == [0.05, 0.15, 0.9, 0.18]

    assert len(body["ocr_tokens"]) == len(_tokens())
    token_texts = {token["text"] for token in body["ocr_tokens"]}
    assert "KIM GUAN HARDWARE" in token_texts
    for token in body["ocr_tokens"]:
        assert set(token) == {"text", "confidence", "bbox", "line_num"}

    assert body["image_url"] == _image_url(client_id, receipt_id)


# --------------------------------------------------------------------------- #
# Image streaming (§6.3.3)
# --------------------------------------------------------------------------- #


def test_image_streams_stored_blob(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload_one(client, client_id)

    response = client.get(_image_url(client_id, receipt_id))

    assert response.status_code == 200
    assert response.content == JPEG_BYTES
    assert response.headers["content-type"] == "image/jpeg"


def test_image_missing_blob_returns_404(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload_one(client, client_id)

    with SessionLocal() as db:
        receipt = db.get(Receipt, uuid.UUID(receipt_id))
        assert receipt is not None
        relative = receipt.storage_path
    (storage.storage_root() / relative).unlink()

    response = client.get(_image_url(client_id, receipt_id))

    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Update & verify (§6.3.4)
# --------------------------------------------------------------------------- #


def test_update_replaces_header_and_line_items(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload_one(client, client_id)

    response = client.put(
        _detail_url(client_id, receipt_id),
        json={
            "merchant_name": "Uncle Lim Kopi",
            "grand_total": "25.00",
            "tax_amount": None,
            "subtotal": None,
            "line_items": [
                {
                    "description": "Teh O Peng",
                    "quantity": "1.00",
                    "unit_price": "4.00",
                    "line_total": "4.00",
                },
                {
                    "description": "Kaya Toast",
                    "quantity": "2.00",
                    "unit_price": "8.00",
                    "line_total": "16.00",
                },
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == ReceiptStatus.STATUS_VERIFIED.value
    assert body["verified_by"] is not None
    assert body["math_discrepancy"] == "5.00"

    detail = client.get(_detail_url(client_id, receipt_id)).json()
    assert detail["merchant_name"] == "Uncle Lim Kopi"
    assert detail["grand_total"] == "25.00"
    assert detail["tax_amount"] is None
    assert detail["subtotal"] is None
    assert detail["status"] == ReceiptStatus.STATUS_VERIFIED.value
    assert detail["math_discrepancy"] == "5.00"
    assert "MATH_MISMATCH_DELTA_5.00" in detail["validation_flags"]
    assert [line["line_index"] for line in detail["line_items"]] == [0, 1]
    assert [line["description"] for line in detail["line_items"]] == [
        "Teh O Peng",
        "Kaya Toast",
    ]


def test_update_writes_audit_log_rows(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload_one(client, client_id)

    response = client.put(
        _detail_url(client_id, receipt_id),
        json={
            "merchant_name": "Uncle Lim Kopi",
            "tax_amount": None,
            "line_items": [
                {
                    "description": "Teh O Peng",
                    "quantity": "1.00",
                    "unit_price": "4.00",
                    "line_total": "4.00",
                }
            ],
        },
    )
    assert response.status_code == 200

    with SessionLocal() as db:
        rows = (
            db.execute(
                select(ReceiptAuditLog).where(
                    ReceiptAuditLog.receipt_id == uuid.UUID(receipt_id)
                )
            )
            .scalars()
            .all()
        )

    logged = {(row.field_name, row.old_value, row.new_value) for row in rows}
    assert ("merchant_name", "Kim Guan Hardware", "Uncle Lim Kopi") in logged
    assert ("tax_amount", "0.00", None) in logged
    # L2: the audit log names the row that actually changed instead of
    # recording "1 rows -> 1 rows", which told a reviewer nothing.
    assert (
        "line_items[0]",
        'PVC Pipe 2" @ 14.50',
        "Teh O Peng @ 4.00",
    ) in logged


def test_update_omitted_keys_leave_fields_alone(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload_one(client, client_id)

    response = client.put(
        _detail_url(client_id, receipt_id),
        json={
            "line_items": [
                {
                    "description": "Kopi C Peng",
                    "quantity": "1.00",
                    "unit_price": "5.50",
                    "line_total": "5.50",
                }
            ]
        },
    )

    assert response.status_code == 200
    detail = client.get(_detail_url(client_id, receipt_id)).json()
    # Absent keys are left alone, not cleared.
    assert detail["merchant_name"] == "Kim Guan Hardware"
    assert detail["grand_total"] == "14.50"
    assert detail["invoice_number"] == "INV-99120"
    assert [line["description"] for line in detail["line_items"]] == ["Kopi C Peng"]


def test_update_clears_grand_total_to_zero_discrepancy(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload_one(client, client_id)

    response = client.put(
        _detail_url(client_id, receipt_id), json={"grand_total": None}
    )

    assert response.status_code == 200
    assert response.json()["math_discrepancy"] == "0.00"
    detail = client.get(_detail_url(client_id, receipt_id)).json()
    assert detail["grand_total"] is None
    assert not any(
        flag.startswith("MATH_MISMATCH_DELTA_") for flag in detail["validation_flags"]
    )


# --------------------------------------------------------------------------- #
# Tenancy isolation (§6.3.5)
# --------------------------------------------------------------------------- #


def test_routes_reject_foreign_tenant(
    client: TestClient,
    stub_pipeline,
    _storage_root: Path,
    other_accountant_id: uuid.UUID,
) -> None:
    stub_pipeline()
    other_headers = {ACCOUNTANT_HEADER: str(other_accountant_id)}

    created = client.post("/api/clients", json=ACCOUNTANT_BODY, headers=other_headers)
    assert created.status_code == 201
    foreign_client_id = created.json()["id"]
    receipt_id = _upload_as(client, other_headers, foreign_client_id)

    for path in (
        f"/api/v1/clients/{foreign_client_id}/receipts",
        _detail_url(foreign_client_id, receipt_id),
        _image_url(foreign_client_id, receipt_id),
    ):
        assert client.get(path).status_code == 404, path

    assert (
        client.put(_detail_url(foreign_client_id, receipt_id), json={}).status_code
        == 404
    )


def _upload_as(client: TestClient, headers: dict[str, str], client_id: str) -> str:
    response = client.post(
        UPLOAD_URL.format(client_id=client_id),
        files=[("files", ("receipt.jpg", JPEG_BYTES, "image/jpeg"))],
        headers=headers,
    )
    assert response.status_code == 202
    return response.json()["receipts"][0]["id"]


def test_unknown_receipt_returns_404(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    missing = str(uuid.uuid4())

    assert client.get(_detail_url(client_id, missing)).status_code == 404
    assert client.get(_image_url(client_id, missing)).status_code == 404
    assert client.put(_detail_url(client_id, missing), json={}).status_code == 404


def test_unknown_client_returns_404(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    missing = str(uuid.uuid4())

    assert client.get(f"/api/v1/clients/{missing}/receipts").status_code == 404
    assert client.get(_detail_url(missing, str(uuid.uuid4()))).status_code == 404


# --------------------------------------------------------------------------- #
# M1: terminal failures are reachable from the inbox
# --------------------------------------------------------------------------- #


def test_error_bucket_is_a_real_filter_and_counts_add_up(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    """Every status must belong to exactly one tab.

    ``ERROR`` was missing from the filter enum while ``ALL`` counted ERR rows, so
    the tab badges summed to less than the total and a failed upload was
    unreachable from any tab — it could only be found by guessing its URL.
    """
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload_one(client, client_id)

    with SessionLocal() as db:
        receipt = db.get(Receipt, uuid.UUID(receipt_id))
        assert receipt is not None
        receipt.status = ReceiptStatus.ERR_UNREADABLE
        receipt.processing_error = "OCR engine returned no tokens"
        db.commit()

    base = f"/api/v1/clients/{client_id}/receipts"

    errors = client.get(base, params={"status": "ERROR"})
    assert errors.status_code == 200
    assert errors.json()["total"] == 1
    item = errors.json()["items"][0]
    # The reason travels with the list row so the inbox can show it (M1).
    assert item["processing_error"] == "OCR engine returned no tokens"

    counts = client.get(base).json()["status_counts"]
    buckets = [
        "NEEDS_REVIEW",
        "VERIFIED",
        "EXPORTED",
        "REJECTED",
        "ERROR",
        "PROCESSING",
    ]
    assert counts["ALL"] == 1
    assert sum(counts[name] for name in buckets) == counts["ALL"]
    assert counts["ERROR"] == 1
