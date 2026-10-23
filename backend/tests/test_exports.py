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
    amount_basis: str | None = None,
    rounding: str | None = None,
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
            amount_basis=amount_basis,
            rounding=None if rounding is None else Decimal(rounding),
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


# --------------------------------------------------------------------------- #
# H3: control characters cannot break out of a CSV cell
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "payload",
    [
        "\r=cmd|' /C calc'!A0",
        "\n=cmd|' /C calc'!A0",
        "Vendor\r\nName",
        "\x00Vendor",
        "Vendor\x1b[31m",
    ],
)
def test_csv_strips_control_characters_before_the_prefix_guard(
    accountant_id: uuid.UUID, payload: str
) -> None:
    """A leading CR bypassed the prefix blocklist and split the record.

    The payload ``"\\r=cmd|..."`` did not *start* with ``=``, so the guard let
    it through and the CR then started a new line inside the cell — which is
    exactly what Excel and RFC-4180 readers treat as a record boundary.
    """
    client_id = _seed_client(accountant_id)
    _seed_receipt(
        client_id,
        merchant_name=payload,
        invoice_number="INV-CR",
        lines=((0, payload, "1.00", "10.00"),),
        subtotal="10.00",
        tax="0.60",
        grand_total="10.60",
    )

    with SessionLocal() as db:
        csv_text = generate_accounting_csv(client_id, month="2026-09", db=db)

    # The record count is unchanged: no payload can create an extra row.
    rows = _parse_csv(csv_text)
    assert len(rows) == 2  # header + one line item

    # No control character survives into any cell.
    for row in rows:
        for cell in row:
            assert "\r" not in cell
            assert "\n" not in cell
            assert not any(ord(char) < 0x20 for char in cell)

    row = next(row for row in rows[1:] if "INV-CR" in row)
    # Whatever is left is neutralised, so a spreadsheet cannot execute it.
    assert row[3].startswith("'") or not row[3].startswith(("=", "+", "-", "@"))
    assert row[4].startswith("'") or not row[4].startswith(("=", "+", "-", "@"))


def test_csv_quotes_every_field(accountant_id: uuid.UUID) -> None:
    """QUOTE_ALL keeps a separator inside a value from shifting the columns."""
    client_id = _seed_client(accountant_id)
    _seed_receipt(
        client_id,
        merchant_name='Vendor, Inc. "The Best"',
        invoice_number="INV-QUOTE",
        lines=((0, "Item, with comma", "1.00", "10.00"),),
        subtotal="10.00",
        tax="0.60",
        grand_total="10.60",
    )

    with SessionLocal() as db:
        csv_text = generate_accounting_csv(client_id, month="2026-09", db=db)

    first_line = csv_text.splitlines()[0]
    assert first_line.startswith('"DocDate"')
    rows = _parse_csv(csv_text)
    row = next(row for row in rows[1:] if "INV-QUOTE" in row)
    assert len(row) == 11
    assert row[3] == 'Vendor, Inc. "The Best"'
    assert row[4] == "Item, with comma"


# --------------------------------------------------------------------------- #
# H1: exports must not double-count GST on an inclusive receipt
# --------------------------------------------------------------------------- #


def _seed_inclusive_receipt(client_id: uuid.UUID) -> None:
    """The audit's 100.jpg: lines 7.42, GST 0.42, total 7.42 (GST inclusive)."""
    _seed_receipt(
        client_id,
        merchant_name="Kedai ABC",
        invoice_number="CS00011955",
        lines=((0, "BEG GUNI", "7.42", "7.42"),),
        subtotal="7.00",
        tax="0.42",
        grand_total="7.42",
        amount_basis="INCLUSIVE",
    )


def test_csv_total_amount_does_not_double_count_inclusive_gst(
    accountant_id: uuid.UUID,
) -> None:
    """A RM 7.42 receipt used to be exported as RM 7.84 (line + tax again)."""
    client_id = _seed_client(accountant_id)
    _seed_inclusive_receipt(client_id)

    with SessionLocal() as db:
        csv_text = generate_accounting_csv(client_id, month="2026-09", db=db)

    rows = _parse_csv(csv_text)
    row = next(row for row in rows[1:] if "CS00011955" in row)
    # UnitPrice and TotalAmount are the net figure and what was actually paid.
    assert row[7] == "7.00"  # UnitPrice, tax-exclusive
    assert row[9] == "0.42"  # TaxAmount
    assert row[10] == "7.42"  # TotalAmount, NOT 7.84


def test_ubL_header_equals_the_sum_of_its_lines(
    accountant_id: uuid.UUID,
) -> None:
    """The header used to carry the printed subtotal while the lines were gross.

    LHDN validators reject a document whose ``LegalMonetaryTotal`` disagrees
    with the sum of ``InvoiceLine/LineExtensionAmount``.
    """
    client_id = _seed_client(accountant_id)
    _seed_inclusive_receipt(client_id)

    payload = generate_myinvois_json(client_id, month="2026-09")
    invoice = payload["Invoice"][0]
    totals = invoice["LegalMonetaryTotal"][0]
    lines = invoice["InvoiceLine"]

    line_sum = round(sum(line["LineExtensionAmount"][0]["_"] for line in lines), 2)
    assert totals["LineExtensionAmount"][0]["_"] == line_sum
    assert totals["TaxExclusiveAmount"][0]["_"] == line_sum
    # TaxExclusive + tax must land on the printed payable amount.
    assert round(
        totals["TaxExclusiveAmount"][0]["_"]
        + invoice["TaxTotal"][0]["TaxAmount"][0]["_"],
        2,
    ) == totals["PayableAmount"][0]["_"]
    assert totals["PayableAmount"][0]["_"] == 7.42


def test_exclusive_export_is_unchanged(accountant_id: uuid.UUID) -> None:
    """Trade invoices still export their printed net line totals verbatim."""
    client_id = _seed_client(accountant_id)
    _seed_receipt(
        client_id,
        invoice_number="INV-EXC",
        lines=((0, "PVC Pipe", "14.50", "14.50"), (1, "Minyak", "85.00", "85.00")),
        subtotal="99.50",
        tax="5.97",
        grand_total="105.47",
        amount_basis="EXCLUSIVE",
    )

    payload = generate_myinvois_json(client_id, month="2026-09")
    invoice = payload["Invoice"][0]
    totals = invoice["LegalMonetaryTotal"][0]

    assert [line["LineExtensionAmount"][0]["_"] for line in invoice["InvoiceLine"]] == [
        14.50,
        85.00,
    ]
    assert totals["TaxExclusiveAmount"][0]["_"] == 99.50
    assert totals["TaxInclusiveAmount"][0]["_"] == 105.47


# --------------------------------------------------------------------------- #
# Printed rounding line in the exports
# --------------------------------------------------------------------------- #


def test_csv_posts_the_printed_rounding_line(accountant_id: uuid.UUID) -> None:
    """71.50 + 4.29 - 0.04 = 75.75, so the batch must net to 75.75.

    Without a rounding row the journal sums to 75.79 while the receipt says
    75.75: the accountant books four sen more than was paid, and the export
    disagrees with the audit that approved it.
    """
    client_id = _seed_client(accountant_id)
    _seed_receipt(
        client_id,
        merchant_sst="W10-1808-32000123",
        subtotal="71.50",
        tax="4.29",
        grand_total="75.75",
        rounding="-0.04",
        amount_basis="EXCLUSIVE",
        lines=(
            (0, "PAKU 2 INCI", "4.50", "4.50"),
            (1, "CAT JOTUN (KECIL)", "38.00", "38.00"),
            (2, "ROLLER BRUSH", "12.00", "24.00"),
            (3, "AMPELAS", "1.00", "5.00"),
        ),
    )

    with SessionLocal() as db:
        csv_text = generate_accounting_csv(client_id, month="2026-09", db=db)

    rows = _parse_csv(csv_text)
    data_rows = [row for row in rows[1:] if row[1] == "INV-001"]

    rounding_rows = [row for row in data_rows if row[5] == "ITEM-RND"]
    assert len(rounding_rows) == 1
    assert rounding_rows[0][10] == "-0.04"
    assert rounding_rows[0][6] == "0"

    # The journal now agrees with the receipt.
    posted = sum(Decimal(row[10]) for row in data_rows)
    assert posted == Decimal("75.75")


def test_csv_omits_the_rounding_row_when_nothing_was_rounded(
    accountant_id: uuid.UUID,
) -> None:
    client_id = _seed_client(accountant_id)
    _seed_receipt(client_id, rounding=None)

    with SessionLocal() as db:
        csv_text = generate_accounting_csv(client_id, month="2026-09", db=db)

    rows = _parse_csv(csv_text)
    assert not [row for row in rows[1:] if row[5] == "ITEM-RND"]


def test_ubl_reports_the_printed_rounding_amount(accountant_id: uuid.UUID) -> None:
    """PayableRoundingAmount was hardcoded 0.00, so the document could not add up."""
    client_id = _seed_client(accountant_id)
    _seed_receipt(
        client_id,
        subtotal="71.50",
        tax="4.29",
        grand_total="75.75",
        rounding="-0.04",
        amount_basis="EXCLUSIVE",
        lines=(
            (0, "PAKU 2 INCI", "4.50", "4.50"),
            (1, "CAT JOTUN (KECIL)", "38.00", "38.00"),
            (2, "ROLLER BRUSH", "12.00", "24.00"),
            (3, "AMPELAS", "1.00", "5.00"),
        ),
    )

    payload = generate_myinvois_json(client_id, month="2026-09")
    totals = payload["Invoice"][0]["LegalMonetaryTotal"][0]

    assert totals["PayableRoundingAmount"][0]["_"] == -0.04
    assert totals["PayableAmount"][0]["_"] == 75.75
