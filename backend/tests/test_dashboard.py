"""Dashboard summary (docs/06_schema_api.md §6.3.6, REQ-107).

The aggregates are hand-computed against seeded rows: the point of these tests is
that ``NEEDS_REVIEW``/``REJECTED`` receipts never inflate spend, the top-supplier
list is ordered and capped at five, every expense category is present, and the
month filter is strict rather than permissive.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.auth import ACCOUNTANT_HEADER
from app.core.database import SessionLocal
from app.models.client import Client
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_line_item import ReceiptLineItem
from app.services.classifier import classify_expense

SUMMARY_URL = "/api/v1/clients/{client_id}/dashboard/summary"
CATEGORY_NAMES = ("F&B", "HARDWARE", "WORKSHOP", "RETAIL", "OTHER")


# --------------------------------------------------------------------------- #
# Seeding helpers
# --------------------------------------------------------------------------- #


def _seed_client(
    accountant_id: uuid.UUID, name: str = "Kim Guan Hardware"
) -> uuid.UUID:
    with SessionLocal() as db:
        workspace = Client(accountant_id=accountant_id, business_name=name)
        db.add(workspace)
        db.commit()
        return workspace.id


def _seed_receipt(
    client_id: uuid.UUID,
    *,
    merchant_name: str | None = "Kedai Hardware",
    invoice_date: date | None = date(2026, 9, 12),
    status: ReceiptStatus = ReceiptStatus.STATUS_VERIFIED,
    grand_total: str = "10.00",
    lines: tuple[tuple[str, str], ...] = (),
) -> uuid.UUID:
    """Insert one receipt plus optional ``(description, line_total)`` rows."""
    with SessionLocal() as db:
        receipt = Receipt(
            client_id=client_id,
            original_filename="receipt.jpg",
            storage_path=f"receipts/{uuid.uuid4()}.jpg",
            mime_type="image/jpeg",
            file_size_bytes=128,
            status=status,
            merchant_name=merchant_name,
            invoice_date=invoice_date,
            invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
            subtotal=Decimal(grand_total),
            tax_amount=Decimal("0.00"),
            grand_total=Decimal(grand_total),
        )
        for index, (description, line_total) in enumerate(lines):
            receipt.line_items.append(
                ReceiptLineItem(
                    line_index=index,
                    description=description,
                    quantity=Decimal("1.000"),
                    unit_price=Decimal(line_total),
                    line_total=Decimal(line_total),
                    expense_category=classify_expense(description),
                    confidence=Decimal("0.95"),
                )
            )
        db.add(receipt)
        db.commit()
        return receipt.id


def _summary(client: TestClient, client_id: uuid.UUID, month: str | None = None):
    params = {"month": month} if month is not None else None
    return client.get(SUMMARY_URL.format(client_id=client_id), params=params)


def _category_totals(payload: dict) -> dict[str, str]:
    return {
        row["category"]: row["total_spend"] for row in payload["category_breakdown"]
    }


# --------------------------------------------------------------------------- #
# Classifier keywords
# --------------------------------------------------------------------------- #


def test_classify_expense_reads_malay_item_names() -> None:
    """A Kuching hardware receipt is printed in Malay, not English.

    Every line of the demo receipt ("PAKU 2 INCI", "CAT JOTUN (KECIL)",
    "ROLLER BRUSH 7\"", "AMPELAS") fell through to OTHER, so the dashboard
    reported RM 0.00 across HARDWARE/WORKSHOP/RETAIL for a hardware shop.
    """
    assert classify_expense("PAKU 2 INCI") == "HARDWARE"
    assert classify_expense("CAT JOTUN (KECIL)") == "HARDWARE"
    assert classify_expense('ROLLER BRUSH 7"') == "HARDWARE"
    assert classify_expense("AMPELAS") == "HARDWARE"
    assert classify_expense("Minyak Enjin") == "WORKSHOP"


def test_classify_expense_keeps_english_meaning_where_malay_overlaps() -> None:
    """"cat" is paint, but F&B is checked first, so pet food stays food."""
    assert classify_expense("CAT FOOD") == "F&B"


def test_classify_expense_matches_spark_and_gear_keywords() -> None:
    assert classify_expense("Spark Plug") == "HARDWARE"
    assert classify_expense("Minyak Gear") == "WORKSHOP"
    assert classify_expense("Upah Pasang") == "WORKSHOP"


# --------------------------------------------------------------------------- #
# Inclusion rules
# --------------------------------------------------------------------------- #


def test_total_excludes_unreviewed_receipts(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    client_id = _seed_client(accountant_id)
    _seed_receipt(
        client_id, merchant_name="Alpha", grand_total="10.00", lines=(("PVC pipe", "10.00"),)
    )
    _seed_receipt(
        client_id, merchant_name="Beta", grand_total="20.00", lines=(("Nasi lemak", "20.00"),)
    )
    _seed_receipt(
        client_id,
        merchant_name="Gamma",
        status=ReceiptStatus.STATUS_NEEDS_REVIEW,
        grand_total="99.00",
        lines=(("Nasi lemak", "99.00"),),
    )
    _seed_receipt(
        client_id,
        merchant_name="Delta",
        status=ReceiptStatus.STATUS_REJECTED,
        grand_total="55.00",
    )

    response = _summary(client, client_id, "2026-09")
    assert response.status_code == 200
    body = response.json()

    assert body["total_spend"] == "30.00"
    assert body["month"] == "2026-09"
    assert [row["supplier_name"] for row in body["top_suppliers"]] == ["Beta", "Alpha"]
    assert _category_totals(body)["HARDWARE"] == "10.00"
    assert _category_totals(body)["F&B"] == "20.00"


def test_auto_verified_and_exported_receipts_are_included(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    client_id = _seed_client(accountant_id)
    _seed_receipt(
        client_id,
        merchant_name="Auto",
        status=ReceiptStatus.STATUS_AUTO_VERIFIED,
        grand_total="11.11",
    )
    _seed_receipt(
        client_id,
        merchant_name="Exported",
        status=ReceiptStatus.STATUS_EXPORTED,
        grand_total="22.22",
    )
    _seed_receipt(
        client_id,
        merchant_name="Reviewed",
        status=ReceiptStatus.STATUS_VERIFIED,
        grand_total="33.33",
    )

    body = _summary(client, client_id, "2026-09").json()
    assert body["total_spend"] == "66.66"
    assert {row["supplier_name"] for row in body["top_suppliers"]} == {
        "Auto",
        "Exported",
        "Reviewed",
    }


def test_every_expense_category_is_present_with_zeros(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    client_id = _seed_client(accountant_id)
    _seed_receipt(
        client_id,
        grand_total="5.00",
        lines=(("PVC pipe 2in", "5.00"),),
    )

    body = _summary(client, client_id, "2026-09").json()
    totals = _category_totals(body)

    assert tuple(totals) == CATEGORY_NAMES
    assert totals["HARDWARE"] == "5.00"
    assert totals["F&B"] == "0.00"
    assert totals["WORKSHOP"] == "0.00"
    assert totals["RETAIL"] == "0.00"
    assert totals["OTHER"] == "0.00"


# --------------------------------------------------------------------------- #
# Ordering, cap, and month filter
# --------------------------------------------------------------------------- #


def test_top_suppliers_are_spend_descending_and_capped_at_five(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    client_id = _seed_client(accountant_id)
    for amount, name in [
        ("10.00", "Supplier 1"),
        ("60.00", "Supplier 6"),
        ("30.00", "Supplier 3"),
        ("50.00", "Supplier 5"),
        ("20.00", "Supplier 2"),
        ("40.00", "Supplier 4"),
    ]:
        _seed_receipt(client_id, merchant_name=name, grand_total=amount)

    rows = _summary(client, client_id, "2026-09").json()["top_suppliers"]

    assert [row["supplier_name"] for row in rows] == [
        "Supplier 6",
        "Supplier 5",
        "Supplier 4",
        "Supplier 3",
        "Supplier 2",
    ]
    assert rows[0]["total_spend"] == "60.00"
    assert "Supplier 1" not in {row["supplier_name"] for row in rows}


def test_top_suppliers_count_receipts_per_supplier(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    client_id = _seed_client(accountant_id)
    _seed_receipt(client_id, merchant_name="Repeat", grand_total="5.00")
    _seed_receipt(client_id, merchant_name="Repeat", grand_total="7.00")

    rows = _summary(client, client_id, "2026-09").json()["top_suppliers"]

    assert len(rows) == 1
    assert rows[0]["supplier_name"] == "Repeat"
    assert rows[0]["receipt_count"] == 2
    assert rows[0]["total_spend"] == "12.00"


def test_blank_merchant_names_are_omitted(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    client_id = _seed_client(accountant_id)
    _seed_receipt(client_id, merchant_name=None, grand_total="4.00")
    _seed_receipt(client_id, merchant_name="", grand_total="6.00")
    _seed_receipt(client_id, merchant_name="Named", grand_total="8.00")

    body = _summary(client, client_id, "2026-09").json()

    assert body["total_spend"] == "18.00"
    assert [row["supplier_name"] for row in body["top_suppliers"]] == ["Named"]


def test_month_filter_excludes_other_months(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    client_id = _seed_client(accountant_id)
    _seed_receipt(
        client_id, merchant_name="August", invoice_date=date(2026, 8, 31), grand_total="9.00"
    )
    _seed_receipt(
        client_id,
        merchant_name="September",
        invoice_date=date(2026, 9, 1),
        grand_total="12.00",
    )
    _seed_receipt(
        client_id,
        merchant_name="October",
        invoice_date=date(2026, 10, 1),
        grand_total="15.00",
    )

    september = _summary(client, client_id, "2026-09").json()
    assert september["total_spend"] == "12.00"
    assert [row["supplier_name"] for row in september["top_suppliers"]] == [
        "September"
    ]

    august = _summary(client, client_id, "2026-08").json()
    assert august["total_spend"] == "9.00"


# --------------------------------------------------------------------------- #
# Validation and tenancy
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "foo", "2026-00"])
def test_invalid_month_is_422(
    client: TestClient, accountant_id: uuid.UUID, month: str
) -> None:
    client_id = _seed_client(accountant_id)
    assert _summary(client, client_id, month).status_code == 422


def test_omitted_month_defaults_to_current_month(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    client_id = _seed_client(accountant_id)
    today = date.today()

    body = _summary(client, client_id).json()

    assert body["month"] == f"{today.year:04d}-{today.month:02d}"


def test_latest_month_reports_where_the_data_actually_is(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    """The console must be able to tell an empty month from an empty workspace.

    Opening on the current month is only correct when the books are current; for
    a workspace whose receipts are older, ``latest_month`` is what stops the page
    from presenting a screen of RM 0.00 as the truth.
    """
    client_id = _seed_client(accountant_id)
    _seed_receipt(client_id, invoice_date=date(2026, 5, 14), grand_total="75.75")
    _seed_receipt(client_id, invoice_date=date(2026, 4, 2), grand_total="10.00")

    body = _summary(client, client_id, "2026-10").json()

    assert body["month"] == "2026-10"
    assert body["total_spend"] == "0.00"
    assert body["latest_month"] == "2026-05"


def test_omitted_month_follows_the_data_when_the_books_are_stale(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    """A workspace with no receipt this month opens on the month that has one.

    Defaulting to the current month regardless would open the console on a full
    screen of RM 0.00 for a client whose books simply are not current.
    """
    client_id = _seed_client(accountant_id)
    _seed_receipt(client_id, invoice_date=date(2026, 5, 14), grand_total="75.75")

    body = _summary(client, client_id).json()

    assert body["month"] == "2026-05"
    assert body["total_spend"] == "75.75"
    assert body["latest_month"] == "2026-05"


def test_omitted_month_stays_current_when_the_current_month_has_data(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    """Following the data must never move a current workspace off today."""
    client_id = _seed_client(accountant_id)
    today = date.today()
    _seed_receipt(client_id, invoice_date=date(2026, 5, 14), grand_total="10.00")
    _seed_receipt(
        client_id,
        invoice_date=today.replace(day=1),
        merchant_name="Current",
        grand_total="20.00",
    )

    body = _summary(client, client_id).json()

    assert body["month"] == f"{today.year:04d}-{today.month:02d}"
    assert body["total_spend"] == "20.00"


def test_latest_month_is_null_for_an_empty_workspace(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    """No receipts means no month to point at; null, not the current month."""
    client_id = _seed_client(accountant_id)

    body = _summary(client, client_id).json()

    assert body["latest_month"] is None


def test_latest_month_ignores_receipts_without_a_date(
    client: TestClient, accountant_id: uuid.UUID
) -> None:
    """A dateless receipt still counts by upload date, so it cannot be invisible."""
    client_id = _seed_client(accountant_id)
    _seed_receipt(client_id, invoice_date=None, grand_total="10.00")

    body = _summary(client, client_id).json()

    today = date.today()
    assert body["latest_month"] == f"{today.year:04d}-{today.month:02d}"


def test_cross_tenant_summary_is_not_found(
    client: TestClient,
    accountant_id: uuid.UUID,
    other_accountant_id: uuid.UUID,
) -> None:
    client_id = _seed_client(accountant_id)
    _seed_receipt(client_id, grand_total="10.00")

    response = client.get(
        SUMMARY_URL.format(client_id=client_id),
        params={"month": "2026-09"},
        headers={ACCOUNTANT_HEADER: str(other_accountant_id)},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Client not found"


def test_money_is_a_two_decimal_string(client: TestClient, accountant_id: uuid.UUID) -> None:
    client_id = _seed_client(accountant_id)
    _seed_receipt(client_id, merchant_name="Rounding", grand_total="3")
    _seed_receipt(client_id, merchant_name="Rounding", grand_total="0.10")

    body = _summary(client, client_id, "2026-09").json()

    assert body["total_spend"] == "3.10"
    assert body["top_suppliers"][0]["total_spend"] == "3.10"
    assert all(row["total_spend"].count(".") == 1 for row in body["category_breakdown"])
