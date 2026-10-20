"""Focused unit and HTTP tests for the dual-format export engine (§6.4).

Receipts are seeded straight through ``SessionLocal``: these cases exercise the
CSV/MyInvois shaping, the largest-remainder tax allocator and the read-vs-mark
contract, none of which depend on the upload pipeline.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.client import Client
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_line_item import ReceiptLineItem
from app.services.export_engine import (
    allocate_tax_cents,
    generate_accounting_csv,
    generate_myinvois_json,
    parse_month_range,
)

EXPORTS_URL = "/api/v1/clients/{client_id}/exports"
INJECTION_MERCHANT = "=cmd|' /C calc'!A0"
INJECTION_DESCRIPTION = "+cmd|' /C calc'!A0"


# --------------------------------------------------------------------------- #
# Seeding helpers
# --------------------------------------------------------------------------- #


def _seed_client(accountant_id: uuid.UUID, name: str = "Test Trading") -> uuid.UUID:
    with SessionLocal() as db:
        client = Client(accountant_id=accountant_id, business_name=name)
        db.add(client)
        db.commit()
        return client.id


def _seed_receipt(
    client_id: uuid.UUID,
    *,
    merchant_name: str = "Kedai Hardware",
    merchant_brn: str | None = None,
    merchant_sst: str | None = None,
    invoice_number: str = "INV-001",
    invoice_date: date | None = date(2026, 9, 12),
    status: ReceiptStatus = ReceiptStatus.STATUS_VERIFIED,
    subtotal: str = "99.99",
    tax: str = "0.07",
    grand_total: str = "100.06",
    lines: tuple[tuple[int, str, str, str], ...] = (
        (0, "Item A", "1.00", "33.33"),
        (1, "Item B", "1.00", "33.33"),
        (2, "Item C", "1.00", "33.33"),
    ),
) -> uuid.UUID:
    """Insert one receipt (plus line items) and return its id."""
    with SessionLocal() as db:
        receipt = Receipt(
            client_id=client_id,
            original_filename="receipt.jpg",
            storage_path=f"receipts/{uuid.uuid4()}.jpg",
            mime_type="image/jpeg",
            file_size_bytes=128,
            status=status,
            merchant_name=merchant_name,
            merchant_brn=merchant_brn,
            merchant_sst=merchant_sst,
            invoice_date=invoice_date,
            invoice_number=invoice_number,
            subtotal=Decimal(subtotal),
            tax_amount=Decimal(tax),
            grand_total=Decimal(grand_total),
        )
        for index, description, unit_price, line_total in lines:
            receipt.line_items.append(
                ReceiptLineItem(
                    line_index=index,
                    description=description,
                    quantity=Decimal("1.000"),
                    unit_price=Decimal(unit_price),
                    line_total=Decimal(line_total),
                    confidence=Decimal("0.95"),
                )
            )
        db.add(receipt)
        db.commit()
        return receipt.id


def _reload(receipt_id: uuid.UUID) -> Receipt:
    with SessionLocal() as db:
        return db.execute(
            select(Receipt).where(Receipt.id == receipt_id)
        ).scalar_one()


def _parse_csv(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


# --------------------------------------------------------------------------- #
# CSV formula injection
# --------------------------------------------------------------------------- #


def test_csv_neutralises_formula_injection(accountant_id: uuid.UUID) -> None:
    """Cells starting with a formula trigger are apostrophe-prefixed, not dropped."""
    client_id = _seed_client(accountant_id)
    _seed_receipt(
        client_id,
        merchant_name=INJECTION_MERCHANT,
        invoice_number="INV-INJECT",
        lines=((0, INJECTION_DESCRIPTION, "1.00", "99.99"),),
        subtotal="99.99",
        tax="0.07",
        grand_total="100.06",
    )

    with SessionLocal() as db:
        csv_text = generate_accounting_csv(client_id, month="2026-09", db=db)

    assert f"'{INJECTION_MERCHANT}" in csv_text
    assert f"'{INJECTION_DESCRIPTION}" in csv_text

    rows = _parse_csv(csv_text)
    assert rows[0][0] == "DocDate"
    row = next(row for row in rows[1:] if "INV-INJECT" in row)
    assert row[3] == f"'{INJECTION_MERCHANT}"
    assert row[4] == f"'{INJECTION_DESCRIPTION}"
    # The raw formula must never survive as a leading character in a cell.
    assert not any(cell.startswith("=") for cell in row)
    assert not any(cell.startswith("+") for cell in row)


# --------------------------------------------------------------------------- #
# Largest-remainder allocation
# --------------------------------------------------------------------------- #


def test_allocate_tax_cents_largest_remainder() -> None:
    result = allocate_tax_cents(9999, 7, [3333, 3333, 3333])

    assert result == [3, 2, 2]
    assert sum(result) == 7


@pytest.mark.parametrize(
    ("subtotal", "tax", "lines"),
    [
        (10_000, 700, [5_000, 3_000, 2_000]),
        (1_234, 99, [1, 1_233]),
        (1_000, 7, [1_000, 0]),
        (777, 31, [111, 222, 444]),
    ],
)
def test_allocate_tax_cents_sums_exactly(
    subtotal: int, tax: int, lines: list[int]
) -> None:
    result = allocate_tax_cents(subtotal, tax, lines)

    assert sum(result) == tax
    assert len(result) == len(lines)
    assert all(value >= 0 for value in result)


@pytest.mark.parametrize("lines", [[], [0, 0]])
def test_allocate_tax_cents_degenerate_lines_return_zeros(lines: list[int]) -> None:
    assert allocate_tax_cents(0, 70, lines) == [0] * len(lines)


# --------------------------------------------------------------------------- #
# MyInvois line taxes
# --------------------------------------------------------------------------- #


def test_myinvois_line_taxes_sum_to_document_total(accountant_id: uuid.UUID) -> None:
    """0.07 across three equal 33.33 lines becomes 3/2/2 cents, totalling 7."""
    client_id = _seed_client(accountant_id)
    _seed_receipt(client_id, invoice_number="INV-TAX")

    with SessionLocal() as db:
        payload = generate_myinvois_json(client_id, month="2026-09", db=db)

    invoice = payload["Invoice"][0]
    line_taxes = [
        line["TaxTotal"][0]["TaxAmount"][0]["_"] for line in invoice["InvoiceLine"]
    ]
    document_tax = invoice["TaxTotal"][0]["TaxAmount"][0]["_"]

    assert line_taxes == [0.03, 0.02, 0.02]
    assert document_tax == 0.07

    line_cents = sum(round(amount * 100) for amount in line_taxes)
    assert line_cents == round(document_tax * 100) == 7


def test_myinvois_sst_party_id_is_the_registration_token_only(
    accountant_id: uuid.UUID,
) -> None:
    """A stored SST field that also carries the BRN must not leak into the party ID.

    Extraction on the demo receipt produced ``"200401032489 / Y24-1808-31015655"``;
    exporting that verbatim ships a malformed ``schemeID: "SST"`` value to MyInvois.
    """
    client_id = _seed_client(accountant_id)
    _seed_receipt(
        client_id,
        invoice_number="INV-SST",
        merchant_brn="200401032489",
        merchant_sst="200401032489 / Y24-1808-31015655",
    )

    with SessionLocal() as db:
        payload = generate_myinvois_json(client_id, month="2026-09", db=db)

    party = payload["Invoice"][0]["AccountingSupplierParty"][0]["Party"][0]
    ids = {pid["ID"][0]["schemeID"]: pid["ID"][0]["_"] for pid in party["PartyIdentification"]}

    assert ids["SST"] == "Y24-1808-31015655"
    assert ids["BRN"] == "200401032489"


def test_myinvois_omits_unparseable_sst_instead_of_exporting_it(
    accountant_id: uuid.UUID,
) -> None:
    client_id = _seed_client(accountant_id)
    _seed_receipt(
        client_id,
        invoice_number="INV-SST-BAD",
        merchant_brn="200401032489",
        merchant_sst="not-a-number",
    )

    with SessionLocal() as db:
        payload = generate_myinvois_json(client_id, month="2026-09", db=db)

    party = payload["Invoice"][0]["AccountingSupplierParty"][0]["Party"][0]
    schemes = [pid["ID"][0]["schemeID"] for pid in party["PartyIdentification"]]

    assert "SST" not in schemes
    assert schemes == ["BRN"]


# --------------------------------------------------------------------------- #
# Month parsing
# --------------------------------------------------------------------------- #


def test_parse_month_range_valid_month() -> None:
    assert parse_month_range("2026-09") == (date(2026, 9, 1), date(2026, 9, 30))


def test_parse_month_range_none_and_empty_are_unbounded() -> None:
    assert parse_month_range(None) is None
    assert parse_month_range("") is None
    assert parse_month_range("   ") is None


@pytest.mark.parametrize(
    "month", ["2026-13", "2026-1", "2026-00", "2026-9", "foo", "202609", "2026-09-01"]
)
def test_parse_month_range_rejects_invalid(month: str) -> None:
    with pytest.raises(ValueError):
        parse_month_range(month)


# --------------------------------------------------------------------------- #
# HTTP: downloads are pure reads
# --------------------------------------------------------------------------- #


def test_export_downloads_do_not_mutate_receipts(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    client_id = _seed_client(accountant_id)
    receipt_id = _seed_receipt(client_id, invoice_number="INV-PURE")

    base = EXPORTS_URL.format(client_id=client_id)
    csv_response = client.get(f"{base}/accounting-csv", params={"month": "2026-09"})
    json_response = client.get(f"{base}/myinvois-json", params={"month": "2026-09"})

    assert csv_response.status_code == 200
    assert json_response.status_code == 200
    assert "INV-PURE" in csv_response.text

    reloaded = _reload(receipt_id)
    assert reloaded.status == ReceiptStatus.STATUS_VERIFIED
    assert reloaded.exported_at is None


# --------------------------------------------------------------------------- #
# HTTP: explicit mark
# --------------------------------------------------------------------------- #


def test_mark_endpoint_is_idempotent_and_exports_stay_visible(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    client_id = _seed_client(accountant_id)
    receipt_id = _seed_receipt(client_id, invoice_number="INV-MARK")

    base = EXPORTS_URL.format(client_id=client_id)
    first = client.post(f"{base}/mark", params={"month": "2026-09"})
    second = client.post(f"{base}/mark", params={"month": "2026-09"})

    assert first.status_code == 200
    assert first.json() == {"updated": 1}
    assert second.status_code == 200
    assert second.json() == {"updated": 0}

    reloaded = _reload(receipt_id)
    assert reloaded.status == ReceiptStatus.STATUS_EXPORTED
    assert reloaded.exported_at is not None

    # EXPORTED is still an exportable status, so the batch keeps the row.
    csv_response = client.get(f"{base}/accounting-csv", params={"month": "2026-09"})
    assert csv_response.status_code == 200
    assert "INV-MARK" in csv_response.text


def test_mark_without_month_covers_all_time(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    client_id = _seed_client(accountant_id)
    september = _seed_receipt(
        client_id, invoice_number="INV-SEP", invoice_date=date(2026, 9, 3)
    )
    august = _seed_receipt(
        client_id, invoice_number="INV-AUG", invoice_date=date(2026, 8, 20)
    )

    base = EXPORTS_URL.format(client_id=client_id)
    response = client.post(f"{base}/mark")

    assert response.status_code == 200
    assert response.json() == {"updated": 2}

    assert _reload(september).status == ReceiptStatus.STATUS_EXPORTED
    assert _reload(august).status == ReceiptStatus.STATUS_EXPORTED


# --------------------------------------------------------------------------- #
# HTTP: invalid months are validation errors, never 500s
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "foo", "2026-00"])
def test_invalid_month_is_422_on_every_export_route(
    client: TestClient, accountant_id: uuid.UUID, month: str
) -> None:
    client_id = _seed_client(accountant_id)
    base = EXPORTS_URL.format(client_id=client_id)

    csv_response = client.get(f"{base}/accounting-csv", params={"month": month})
    json_response = client.get(f"{base}/myinvois-json", params={"month": month})
    mark_response = client.post(f"{base}/mark", params={"month": month})

    assert csv_response.status_code == 422
    assert json_response.status_code == 422
    assert mark_response.status_code == 422
