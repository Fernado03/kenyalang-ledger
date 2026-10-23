"""End-to-end integration and smoke tests for export engine and endpoints.

Covers:
- Ingesting a sample receipt through upload pipeline.
- Marking it as STATUS_VERIFIED.
- Calling generate_myinvois_json() and asserting all mandatory LHDN fields
  (ID, IssueDate, AccountingSupplierParty, LegalMonetaryTotal, InvoiceLine).
- Calling generate_accounting_csv() and verifying AutoCount / SQL Account headers.
- Calling GET /api/v1/clients/{client_id}/exports/accounting-csv and /myinvois-json.
- Verifying tenant isolation and month filters.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.auth import ACCOUNTANT_HEADER
from app.core.database import SessionLocal
from app.models.receipt import Receipt, ReceiptStatus
from app.pipeline.ocr_engine import OCRToken
from app.schemas.receipt import (
    ExtractedField,
    LineItemSchema,
    ParsedReceiptSchema,
)
from app.services.export_engine import (
    generate_accounting_csv,
    generate_myinvois_json,
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
            confidence=0.95,
            bbox=[0.05, 0.05 * i, 0.9, 0.05 * i + 0.03],
            line_num=i,
        )
        for i, text in enumerate(
            [
                "KIM GUAN HARDWARE",
                "INV-99120",
                'PVC PIPE 2"',
                "14.50",
                "TOTAL 14.50",
            ]
        )
    ]


def _parsed(invoice_date: date | None = None) -> ParsedReceiptSchema:
    inv_date = invoice_date or (date.today() - timedelta(days=2))
    return ParsedReceiptSchema(
        merchant_name="Kim Guan Hardware",
        merchant_brn="202001012345",
        merchant_sst="W10-1808-32000018",
        invoice_date=inv_date,
        invoice_number="INV-99120",
        subtotal=Decimal("99.50"),
        tax_amount=Decimal("5.97"),
        grand_total=Decimal("105.47"),
        line_items=[
            LineItemSchema(
                line_index=0,
                description='PVC Pipe 2"',
                quantity=Decimal("1.00"),
                unit_price=Decimal("14.50"),
                line_total=Decimal("14.50"),
                confidence=0.93,
                bbox=[0.05, 0.15, 0.9, 0.18],
            ),
            LineItemSchema(
                line_index=1,
                description="Minyak Hitam 4L",
                quantity=Decimal("1.00"),
                unit_price=Decimal("85.00"),
                line_total=Decimal("85.00"),
                confidence=0.95,
                bbox=[0.05, 0.20, 0.9, 0.23],
            ),
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


@pytest.fixture(autouse=True)
def _storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("KENYALANG_STORAGE_ROOT", str(tmp_path / "storage"))
    return tmp_path / "storage"


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


def _create_client(client: TestClient) -> str:
    response = client.post("/api/clients", json=ACCOUNTANT_BODY)
    assert response.status_code == 201
    return response.json()["id"]


def test_e2e_export_flow(
    client: TestClient,
    stub_pipeline,
) -> None:
    """Ingest a sample receipt, mark as STATUS_VERIFIED, and assert LHDN & CSV exports."""
    target_date = date(2026, 9, 12)
    stub_pipeline(_parsed(invoice_date=target_date))

    # 1. Ingest receipt
    client_id = _create_client(client)
    upload_res = client.post(
        UPLOAD_URL.format(client_id=client_id),
        files=[("files", ("receipt.jpg", JPEG_BYTES, "image/jpeg"))],
    )
    assert upload_res.status_code == 202
    receipts_list = upload_res.json()["receipts"]
    assert len(receipts_list) == 1
    receipt_id = uuid.UUID(receipts_list[0]["id"])

    # 2. Mark as STATUS_VERIFIED
    with SessionLocal() as db:
        rec = db.execute(
            select(Receipt).where(Receipt.id == receipt_id)
        ).scalar_one()
        rec.status = ReceiptStatus.STATUS_VERIFIED
        db.commit()

    # 3. Call generate_myinvois_json() and assert all mandatory LHDN fields
    lhdn_payload = generate_myinvois_json(client_id, month="2026-09")

    # Assert root namespaces
    assert "_D" in lhdn_payload
    assert "_A" in lhdn_payload
    assert "_B" in lhdn_payload
    assert "Invoice" in lhdn_payload
    assert len(lhdn_payload["Invoice"]) == 1

    inv = lhdn_payload["Invoice"][0]

    # Mandatory LHDN fields requirement from task prompt:
    # (ID, IssueDate, AccountingSupplierParty, LegalMonetaryTotal, InvoiceLine)
    assert "ID" in inv
    assert inv["ID"][0]["_"] == "INV-99120"

    assert "IssueDate" in inv
    assert inv["IssueDate"][0]["_"] == "2026-09-12"

    assert "AccountingSupplierParty" in inv
    party = inv["AccountingSupplierParty"][0]["Party"][0]
    assert party["PartyName"][0]["Name"][0]["_"] == "Kim Guan Hardware"
    assert any(
        pid["ID"][0]["_"] == "202001012345" for pid in party["PartyIdentification"]
    )

    assert "LegalMonetaryTotal" in inv
    totals = inv["LegalMonetaryTotal"][0]
    assert totals["LineExtensionAmount"][0]["_"] == 99.50
    assert totals["TaxInclusiveAmount"][0]["_"] == 105.47
    assert totals["PayableAmount"][0]["_"] == 105.47

    assert "InvoiceLine" in inv
    lines = inv["InvoiceLine"]
    assert len(lines) == 2
    assert lines[0]["ID"][0]["_"] == "1"
    assert lines[0]["Item"][0]["Description"][0]["_"] == 'PVC Pipe 2"'
    assert lines[0]["LineExtensionAmount"][0]["_"] == 14.50
    assert lines[1]["ID"][0]["_"] == "2"
    assert lines[1]["Item"][0]["Description"][0]["_"] == "Minyak Hitam 4L"
    assert lines[1]["LineExtensionAmount"][0]["_"] == 85.00

    # Also test proxy access on MyInvoisPayload: payload["ID"] or "ID" in payload
    assert "ID" in lhdn_payload
    assert lhdn_payload["ID"][0]["_"] == "INV-99120"
    assert "IssueDate" in lhdn_payload
    assert "AccountingSupplierParty" in lhdn_payload
    assert "LegalMonetaryTotal" in lhdn_payload
    assert "InvoiceLine" in lhdn_payload

    # 4. Call generate_accounting_csv() and assert AutoCount / SQL Account columns
    csv_str = generate_accounting_csv(client_id, month="2026-09")
    # Parsed with the csv module rather than split(","): every field is quoted
    # (QUOTE_ALL, H3), so the raw text is not comma-delimited in the naive sense.
    csv_rows = list(csv.reader(io.StringIO(csv_str)))
    csv_rows = [row for row in csv_rows if any(cell.strip() for cell in row)]
    expected_header = [
        "DocDate",
        "DocNo",
        "SupplierCode",
        "SupplierName",
        "Description",
        "ItemCode",
        "Qty",
        "UnitPrice",
        "TaxCode",
        "TaxAmount",
        "TotalAmount",
    ]
    assert csv_rows[0] == expected_header
    assert len(csv_rows) == 3  # header + 2 line items
    assert csv_rows[1][0] == "12/09/2026"
    assert csv_rows[1][1] == "INV-99120"
    assert 'PVC Pipe 2"' in csv_rows[1][4]
    assert "Minyak Hitam 4L" in csv_rows[2][4]
    # Exclusive receipt: line totals are already net, so the printed values
    # survive unchanged and TotalAmount still reconciles to the grand total.
    assert sum(float(row[10]) for row in csv_rows[1:]) == pytest.approx(105.47, abs=0.01)


def test_export_api_endpoints_and_tenancy(
    client: TestClient,
    test_app: TestClient,
    other_accountant_id: uuid.UUID,
    stub_pipeline,
) -> None:
    """Test HTTP endpoints, month filtering, and tenancy boundary."""
    stub_pipeline(_parsed(invoice_date=date(2026, 9, 15)))
    client_id = _create_client(client)

    # Ingest and verify
    upload_res = client.post(
        UPLOAD_URL.format(client_id=client_id),
        files=[("files", ("receipt.jpg", JPEG_BYTES, "image/jpeg"))],
    )
    receipt_id = uuid.UUID(upload_res.json()["receipts"][0]["id"])

    with SessionLocal() as db:
        rec = db.execute(
            select(Receipt).where(Receipt.id == receipt_id)
        ).scalar_one()
        rec.status = ReceiptStatus.STATUS_VERIFIED
        db.commit()

    # 1. GET accounting-csv
    csv_res = client.get(
        f"/api/v1/clients/{client_id}/exports/accounting-csv?month=2026-09"
    )
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers.get("Content-Type", "")
    assert "Kenyalang_PurJournal_202609.csv" in csv_res.headers.get(
        "Content-Disposition", ""
    )
    assert "INV-99120" in csv_res.text

    # 2. GET myinvois-json
    json_res = client.get(
        f"/api/v1/clients/{client_id}/exports/myinvois-json?month=2026-09"
    )
    assert json_res.status_code == 200
    assert "Kenyalang_MyInvois_202609.json" in json_res.headers.get(
        "Content-Disposition", ""
    )
    data = json_res.json()
    assert len(data["Invoice"]) == 1
    assert data["Invoice"][0]["ID"][0]["_"] == "INV-99120"

    # 3. Month filter non-matching returns empty batch
    nomatch_csv = client.get(
        f"/api/v1/clients/{client_id}/exports/accounting-csv?month=2025-01"
    )
    assert nomatch_csv.status_code == 200
    lines = nomatch_csv.text.strip().split("\n")
    assert len(lines) == 1  # only header row

    nomatch_json = client.get(
        f"/api/v1/clients/{client_id}/exports/myinvois-json?month=2025-01"
    )
    assert nomatch_json.status_code == 200
    assert len(nomatch_json.json()["Invoice"]) == 0

    # 4. Tenancy guard: other accountant cannot export
    other_client = TestClient(test_app.app)
    other_client.headers.update({ACCOUNTANT_HEADER: str(other_accountant_id)})

    other_csv = other_client.get(
        f"/api/v1/clients/{client_id}/exports/accounting-csv"
    )
    assert other_csv.status_code == 404

    other_json = other_client.get(
        f"/api/v1/clients/{client_id}/exports/myinvois-json"
    )
    assert other_json.status_code == 404
