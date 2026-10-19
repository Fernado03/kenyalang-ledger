from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from app.pipeline.ocr_engine import OCRToken
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_audit_log import ReceiptAuditLog
from app.schemas.receipt import (
    ExtractedField,
    LineItemSchema,
    ParsedReceiptSchema,
)

ACCOUNTANT_BODY = {
    "business_name": "Reject & Export Test Client",
    "sst_registration_number": "W10-1808-32000018",
}

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
UPLOAD_URL = "/api/v1/clients/{client_id}/receipts/upload"

@pytest.fixture(autouse=True)
def _storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("KENYALANG_STORAGE_ROOT", str(tmp_path / "storage"))
    return tmp_path / "storage"


def _tokens() -> list[OCRToken]:
    return [
        OCRToken(text="KIM GUAN HARDWARE", confidence=0.96, bbox=[0.05, 0.05, 0.60, 0.10], line_num=0),
        OCRToken(text="INV-99120", confidence=0.94, bbox=[0.05, 0.15, 0.40, 0.20], line_num=1),
        OCRToken(text="PVC PIPE", confidence=0.92, bbox=[0.05, 0.25, 0.40, 0.30], line_num=2),
        OCRToken(text="TOTAL", confidence=0.99, bbox=[0.05, 0.40, 0.30, 0.45], line_num=3),
        OCRToken(text="105.47", confidence=0.97, bbox=[0.70, 0.40, 0.95, 0.45], line_num=4),
    ]


@pytest.fixture
def stub_pipeline(monkeypatch: pytest.MonkeyPatch):
    def install(parsed_data: ParsedReceiptSchema | None = None):
        target_parsed = parsed_data or _parsed()
        monkeypatch.setattr(
            "app.api.receipts.process_receipt_image", lambda *_a, **_k: _tokens()
        )
        monkeypatch.setattr(
            "app.api.receipts.extract_receipt", lambda _t, **_: target_parsed
        )

    return install


def _parsed(
    grand_total: str = "105.47",
    line_total: str = "99.50",
    tax_amount: str = "5.97",
    invoice_date: date | None = None,
) -> ParsedReceiptSchema:
    inv_date = invoice_date or date(2026, 9, 12)
    return ParsedReceiptSchema(
        merchant_name="Kim Guan Hardware",
        merchant_brn="202001012345",
        merchant_sst="W10-1808-32000018",
        invoice_date=inv_date,
        invoice_number="INV-99120",
        subtotal=Decimal(line_total),
        tax_amount=Decimal(tax_amount),
        grand_total=Decimal(grand_total),
        line_items=[
            LineItemSchema(
                line_index=0,
                description="PVC Pipe 2\"",
                quantity=Decimal("1"),
                unit_price=Decimal(line_total),
                line_total=Decimal(line_total),
                confidence=0.95,
            )
        ],
        fields=[
            ExtractedField(name="merchant_name", confidence=0.96),
            ExtractedField(name="invoice_date", confidence=0.94),
            ExtractedField(name="invoice_number", confidence=0.95),
            ExtractedField(name="grand_total", confidence=0.95),
            ExtractedField(name="subtotal", confidence=0.93),
            ExtractedField(name="tax_amount", confidence=0.92),
        ],
    )


def _create_client(client: TestClient) -> str:
    response = client.post("/api/clients", json=ACCOUNTANT_BODY)
    assert response.status_code == 201
    return response.json()["id"]


def _upload_one(client: TestClient, client_id: str) -> str:
    response = client.post(
        UPLOAD_URL.format(client_id=client_id),
        files=[("files", ("receipt.jpg", JPEG_BYTES, "image/jpeg"))],
    )
    assert response.status_code == 202
    return response.json()["receipts"][0]["id"]


def test_reject_client_receipt_updates_status_and_audit_log(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline(_parsed(grand_total="70.00", line_total="50.00"))  # flags for review
    client_id = _create_client(client)
    receipt_id = _upload_one(client, client_id)

    base = f"/api/v1/clients/{client_id}/receipts"
    assert client.get(base, params={"status": "NEEDS_REVIEW"}).json()["total"] == 1

    # Call reject endpoint
    reject_res = client.post(f"{base}/{receipt_id}/reject")
    assert reject_res.status_code == 200
    body = reject_res.json()
    assert body["status"] == ReceiptStatus.STATUS_REJECTED.value

    # Verify status changed in database
    with SessionLocal() as db:
        rec = db.get(Receipt, uuid.UUID(receipt_id))
        assert rec is not None
        assert rec.status == ReceiptStatus.STATUS_REJECTED

        # Verify audit log was written
        audit = db.execute(
            select(ReceiptAuditLog).where(
                ReceiptAuditLog.receipt_id == uuid.UUID(receipt_id),
                ReceiptAuditLog.field_name == "status",
            )
        ).scalar_one()
        assert audit.old_value == ReceiptStatus.STATUS_NEEDS_REVIEW.value
        assert audit.new_value == ReceiptStatus.STATUS_REJECTED.value

    # Verify inbox filters: no longer in NEEDS_REVIEW, appears in ALL and REJECTED
    assert client.get(base, params={"status": "NEEDS_REVIEW"}).json()["total"] == 0
    assert client.get(base, params={"status": "ALL"}).json()["total"] == 1
    assert client.get(base, params={"status": "REJECTED"}).json()["total"] == 1


def test_export_download_is_pure_and_mark_transitions_status(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline(_parsed(invoice_date=date(2026, 9, 12)))
    client_id = _create_client(client)
    receipt_id = _upload_one(client, client_id)

    base = f"/api/v1/clients/{client_id}/receipts"

    # Initially auto-verified
    assert client.get(base, params={"status": "VERIFIED"}).json()["total"] == 1
    assert client.get(base, params={"status": "EXPORTED"}).json()["total"] == 0

    # Both downloads are pure reads: neither one changes status
    csv_res = client.get(
        f"/api/v1/clients/{client_id}/exports/accounting-csv?month=2026-09"
    )
    assert csv_res.status_code == 200
    assert 'PVC Pipe 2"' in csv_res.text
    json_res = client.get(
        f"/api/v1/clients/{client_id}/exports/myinvois-json?month=2026-09"
    )
    assert json_res.status_code == 200
    assert len(json_res.json()["Invoice"]) == 1
    assert client.get(base, params={"status": "EXPORTED"}).json()["total"] == 0
    assert client.get(base, params={"status": "VERIFIED"}).json()["total"] == 1

    # The explicit mark action performs the transition
    mark = client.post(
        f"/api/v1/clients/{client_id}/exports/mark?month=2026-09"
    )
    assert mark.status_code == 200
    assert mark.json() == {"updated": 1}
    assert client.get(base, params={"status": "EXPORTED"}).json()["total"] == 1
    assert client.get(base, params={"status": "VERIFIED"}).json()["total"] == 0

    with SessionLocal() as db:
        rec = db.get(Receipt, uuid.UUID(receipt_id))
        assert rec is not None
        assert rec.status == ReceiptStatus.STATUS_EXPORTED
        assert rec.exported_at is not None
        audit = db.execute(
            select(ReceiptAuditLog).where(
                ReceiptAuditLog.receipt_id == uuid.UUID(receipt_id),
                ReceiptAuditLog.field_name == "status",
            )
        ).scalar_one()
        assert audit.old_value == ReceiptStatus.STATUS_AUTO_VERIFIED.value
        assert audit.new_value == ReceiptStatus.STATUS_EXPORTED.value

    # Idempotent: a second mark updates nothing, and the receipt still exports
    second = client.post(
        f"/api/v1/clients/{client_id}/exports/mark?month=2026-09"
    )
    assert second.status_code == 200
    assert second.json() == {"updated": 0}
    again = client.get(
        f"/api/v1/clients/{client_id}/exports/accounting-csv?month=2026-09"
    )
    assert again.status_code == 200
    assert 'PVC Pipe 2"' in again.text


def test_put_after_export_is_conflict_and_leaves_row_exported(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline(_parsed(invoice_date=date(2026, 9, 12)))
    client_id = _create_client(client)
    receipt_id = _upload_one(client, client_id)

    base = f"/api/v1/clients/{client_id}/receipts"
    mark = client.post(f"/api/v1/clients/{client_id}/exports/mark?month=2026-09")
    assert mark.status_code == 200
    assert mark.json() == {"updated": 1}
    assert client.get(base, params={"status": "EXPORTED"}).json()["total"] == 1

    put = client.put(f"{base}/{receipt_id}", json={"grand_total": "99.00"})
    assert put.status_code == 409

    with SessionLocal() as db:
        rec = db.get(Receipt, uuid.UUID(receipt_id))
        assert rec is not None
        assert rec.status == ReceiptStatus.STATUS_EXPORTED
        assert rec.grand_total == Decimal("105.47")
        assert rec.grand_total != Decimal("99.00")
        assert rec.exported_at is not None


def test_reject_after_export_is_conflict(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline(_parsed(invoice_date=date(2026, 9, 12)))
    client_id = _create_client(client)
    receipt_id = _upload_one(client, client_id)

    base = f"/api/v1/clients/{client_id}/receipts"
    mark = client.post(f"/api/v1/clients/{client_id}/exports/mark?month=2026-09")
    assert mark.status_code == 200
    assert mark.json() == {"updated": 1}
    assert client.get(base, params={"status": "EXPORTED"}).json()["total"] == 1

    reject = client.post(f"{base}/{receipt_id}/reject")
    assert reject.status_code == 409

    with SessionLocal() as db:
        rec = db.get(Receipt, uuid.UUID(receipt_id))
        assert rec is not None
        assert rec.status == ReceiptStatus.STATUS_EXPORTED
        assert rec.exported_at is not None

    assert client.get(base, params={"status": "REJECTED"}).json()["total"] == 0
    assert client.get(base, params={"status": "EXPORTED"}).json()["total"] == 1
