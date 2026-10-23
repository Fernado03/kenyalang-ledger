"""Dual-format export engine for accounting systems and MyInvois-shaped JSON.

Implements docs/05_trd.md §5.5 and docs/06_schema_api.md §6.4:
1. AutoCount / SQL Account purchase journal CSV.
2. LHDN MyInvois v1.1-shaped JSON envelope matching
   dataset/official_lhdn_sample/1.1-Invoice-MultiLineItem-Sample.json.

The MyInvois output is a draft document shape. It is not validated against the
official LHDN schema and is never submitted. Downloads are pure reads; the
explicit :func:`mark_exported` action is the only state transition.
"""

from __future__ import annotations

import calendar
import csv
import io
import re
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.database import session_scope, utcnow
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_audit_log import ReceiptAuditLog
from app.schemas.receipt import AMOUNT_BASIS_EXCLUSIVE, AMOUNT_BASIS_INCLUSIVE
from app.services.reconciler import MATH_TOLERANCE, extract_sst_number

MONTH_RE = re.compile(r"^([1-9]\d{3})-(0[1-9]|1[0-2])$")
MONTH_PATTERN = r"^[1-9]\d{3}-(0[1-9]|1[0-2])$"
MONTH_ERROR = "month must be YYYY-MM"

# Spreadsheet applications execute a cell whose text starts with one of these
# characters. Prefixing a single quote forces the cell to stay text.
CSV_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")

# C0 controls and DEL. Tab, CR and LF are included: after a CR the cell text
# continues as a new logical line, which is how a formula smuggles itself into
# the first column of the next row.
CSV_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")

EXPORTABLE_STATUSES: tuple[ReceiptStatus, ...] = (
    ReceiptStatus.STATUS_VERIFIED,
    ReceiptStatus.STATUS_AUTO_VERIFIED,
    ReceiptStatus.STATUS_EXPORTED,
)

CSV_COLUMNS: tuple[str, ...] = (
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
)


class MyInvoisPayload(dict):
    """LHDN MyInvois document payload with proxy fallback for invoice-level fields.

    Matches the official SDK envelope with root namespaces (_D, _A, _B, Invoice)
    while also delegating top-level field lookups to the first Invoice record if
    accessed directly (e.g. payload["ID"] or "ID" in payload).
    """

    def __getitem__(self, key: str) -> Any:
        if super().__contains__(key):
            return super().__getitem__(key)
        invoices = self.get("Invoice", [])
        if (
            isinstance(invoices, list)
            and len(invoices) > 0
            and isinstance(invoices[0], dict)
            and key in invoices[0]
        ):
            return invoices[0][key]
        raise KeyError(key)
    def __contains__(self, key: object) -> bool:
        if super().__contains__(key):
            return True
        invoices = self.get("Invoice", [])
        return bool(
            invoices
            and isinstance(invoices, list)
            and len(invoices) > 0
            and isinstance(invoices[0], dict)
            and key in invoices[0]
        )

def parse_month_range(month: str | None) -> tuple[date, date] | None:
    """Parse ``YYYY-MM`` into inclusive ``(start_date, end_date)``.

    Returns ``None`` when no month is supplied. Raises :class:`ValueError` for
    anything that is not a real calendar month, so callers never reach
    ``calendar.monthrange`` with an impossible month number.
    """
    if month is None:
        return None
    cleaned = month.strip()
    if not cleaned:
        return None
    match = MONTH_RE.match(cleaned)
    if match is None:
        raise ValueError(MONTH_ERROR)
    year, month_num = int(match.group(1)), int(match.group(2))
    _, last_day = calendar.monthrange(year, month_num)
    return date(year, month_num, 1), date(year, month_num, last_day)


def month_clause(month: str | None):
    """SQL predicate bounding receipts to ``month``, or ``None`` when unset."""
    date_range = parse_month_range(month)
    if date_range is None:
        return None
    start_date, end_date = date_range
    return or_(
        and_(
            Receipt.invoice_date >= start_date,
            Receipt.invoice_date <= end_date,
        ),
        and_(
            Receipt.invoice_date.is_(None),
            func.date(Receipt.created_at) >= start_date,
            func.date(Receipt.created_at) <= end_date,
        ),
    )


def _parse_month_range(month: str | None) -> tuple[date, date] | None:
    """Backwards-compatible alias for :func:`parse_month_range`."""
    return parse_month_range(month)


def _csv_text(value: str | None) -> str:
    """Neutralise spreadsheet formula injection in a text cell.

    A cell is dangerous when its *first* character is one of
    ``=``, ``+``, ``-``, ``@``, tab, CR or LF. Stripping control characters
    first is what closes the demonstrated bypass: ``"\\r=cmd|..."`` did not
    start with ``=``, so the prefix guard let it through, and the embedded CR
    then broke the row apart on the receiving side. Control characters can
    never appear in a legitimate merchant name or description, and a carriage
    return inside a quoted field is exactly how a CSV row gets injected, so they
    are replaced with a space rather than escaped. A space (not deletion) keeps
    ``"A\rB"`` from silently becoming the different name ``"AB"``.
    """
    text = "" if value is None else str(value)
    text = CSV_CONTROL_CHARS_RE.sub(" ", text).strip()
    if text.startswith(CSV_DANGEROUS_PREFIXES):
        return "'" + text
    return text


def _to_cents(value: Decimal | float | None) -> int:
    """Convert a Ringgit amount to integer cents using half-up rounding."""
    if value is None:
        return 0
    amount = Decimal(str(value))
    return int((amount * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def allocate_tax_cents(
    subtotal_cents: int,
    tax_cents: int,
    line_totals_cents: list[int],
) -> list[int]:
    """Split ``tax_cents`` across lines by largest remainder.

    Each line receives its proportional floor; leftover cents go one at a time
    to the largest fractional remainders, ties broken by line order. The result
    always sums exactly to ``tax_cents`` when the tax is distributable.

    The divisor is the sum of the line totals, not the header subtotal. Lines
    that do not reconcile with the header (a partial read, a dropped row) would
    otherwise leave part of the tax unallocated, because the floors are computed
    against a base larger than the amount actually being split and the leftover
    loop hands out at most one cent per line. Dividing by the line base keeps
    the invariant that the line taxes add up to the header tax.
    """
    count = len(line_totals_cents)
    line_sum = sum(line_totals_cents)
    if count == 0 or subtotal_cents <= 0 or tax_cents <= 0 or line_sum <= 0:
        return [0] * count

    basis = line_sum

    floors: list[int] = []
    remainders: list[tuple[int, int]] = []
    for index, line_cents in enumerate(line_totals_cents):
        numerator = line_cents * tax_cents
        floor_cents, remainder = divmod(numerator, basis)
        floors.append(floor_cents)
        remainders.append((remainder, index))

    leftover = tax_cents - sum(floors)
    for _, index in sorted(remainders, key=lambda pair: (-pair[0], pair[1])):
        if leftover <= 0:
            break
        floors[index] += 1
        leftover -= 1
    return floors


def receipt_line_amounts(receipt: Receipt) -> tuple[list[int], list[int], int]:
    """Split a receipt's lines into tax-exclusive amounts and allocated tax.

    Returns ``(line_net_cents, line_tax_cents, header_net_cents)``.

    UBL requires every ``InvoiceLine/LineExtensionAmount`` to be tax-*exclusive*
    and the header ``LineExtensionAmount`` to equal their sum. Malaysian retail
    receipts print inclusive line totals, so the printed figures cannot be
    copied straight through: the tax is allocated back out of each line and the
    header is rebuilt from the resulting net amounts. Copying the printed
    subtotal into the header while emitting inclusive line amounts produced a
    document whose header disagreed with its own lines — rejected by LHDN
    validators — and a CSV whose ``TotalAmount`` double-counted GST.
    """
    if not receipt.line_items:
        return [], [], 0

    tax_cents = _to_cents(receipt.tax_amount)
    if tax_cents < 0:
        tax_cents = 0
    printed_cents = [_to_cents(item.line_total) for item in receipt.line_items]

    basis = receipt.amount_basis or _infer_basis_cents(
        printed_cents, tax_cents, _to_cents(receipt.grand_total)
    )
    if basis == AMOUNT_BASIS_INCLUSIVE:
        # The printed totals already contain the tax: take it back out.
        allocated = allocate_tax_cents(sum(printed_cents), tax_cents, printed_cents)
        net = [max(line - tax, 0) for line, tax in zip(printed_cents, allocated)]
        return net, allocated, sum(net)

    # Exclusive: printed line totals are already net.
    allocated = allocate_tax_cents(sum(printed_cents), tax_cents, printed_cents)
    return printed_cents, allocated, sum(printed_cents)


def _infer_basis_cents(
    line_cents: list[int], tax_cents: int, total_cents: int
) -> str:
    """Infer the basis from cents when a row predates the recorded field."""
    if not line_cents:
        return AMOUNT_BASIS_EXCLUSIVE
    line_sum = sum(line_cents)
    tolerance = int(MATH_TOLERANCE * 100)
    if abs(line_sum + tax_cents - total_cents) <= tolerance:
        return AMOUNT_BASIS_EXCLUSIVE
    if abs(line_sum - total_cents) <= tolerance:
        return AMOUNT_BASIS_INCLUSIVE
    return AMOUNT_BASIS_EXCLUSIVE


def _fetch_export_receipts(
    db: Session,
    client_id: uuid.UUID | str,
    month: str | None = None,
) -> list[Receipt]:
    """Query verified receipts for client_id optionally bounded by month."""
    client_uuid = (
        client_id if isinstance(client_id, uuid.UUID) else uuid.UUID(str(client_id))
    )

    stmt = (
        select(Receipt)
        .where(
            Receipt.client_id == client_uuid,
            Receipt.status.in_(EXPORTABLE_STATUSES),
        )
        .options(joinedload(Receipt.line_items))
        .order_by(Receipt.invoice_date.asc().nulls_last(), Receipt.created_at.asc())
    )

    clause = month_clause(month)
    if clause is not None:
        stmt = stmt.where(clause)

    return list(db.execute(stmt).unique().scalars().all())


def mark_exported(
    db: Session,
    client_id: uuid.UUID | str,
    month: str | None = None,
    actor_id: uuid.UUID | None = None,
) -> int:
    """Move verified receipts in the period to ``STATUS_EXPORTED``.

    Only ``VERIFIED`` and ``AUTO_VERIFIED`` rows transition; already-exported
    receipts are left untouched, so repeating the call returns ``0``. One audit
    row per receipt records the status transition.
    """
    client_uuid = (
        client_id if isinstance(client_id, uuid.UUID) else uuid.UUID(str(client_id))
    )
    stmt = (
        select(Receipt)
        .where(
            Receipt.client_id == client_uuid,
            Receipt.status.in_(
                (ReceiptStatus.STATUS_VERIFIED, ReceiptStatus.STATUS_AUTO_VERIFIED)
            ),
        )
        .order_by(Receipt.created_at.asc())
    )
    clause = month_clause(month)
    if clause is not None:
        stmt = stmt.where(clause)

    receipts = list(db.execute(stmt).scalars().all())
    if not receipts:
        return 0

    actor = actor_id or uuid.UUID(int=0)
    now = utcnow()
    for receipt in receipts:
        previous = receipt.status.value
        receipt.status = ReceiptStatus.STATUS_EXPORTED
        receipt.exported_at = now
        db.add(
            ReceiptAuditLog(
                receipt_id=receipt.id,
                user_id=actor,
                field_name="status",
                old_value=previous,
                new_value=ReceiptStatus.STATUS_EXPORTED.value,
            )
        )
    db.commit()
    return len(receipts)

def _format_qty(qty: Decimal | float | None) -> str:
    """Format quantity cleanly (e.g. '1', '2.5')."""
    if qty is None:
        return "1"
    val = Decimal(str(qty))
    formatted = f"{val:.3f}".rstrip("0").rstrip(".")
    return formatted if formatted else "1"


def generate_accounting_csv(
    client_id: uuid.UUID | str,
    month: str | None = None,
    db: Session | None = None,
) -> str:
    """Generate AutoCount / SQL Account purchase journal batch CSV.

    Columns: DocDate, DocNo, SupplierCode, SupplierName, Description, ItemCode,
             Qty, UnitPrice, TaxCode, TaxAmount, TotalAmount
    """

    def _execute(session: Session) -> str:
        receipts = _fetch_export_receipts(session, client_id, month=month)
        output = io.StringIO()
        # QUOTE_ALL: every field is quoted, so a value that still contains a
        # separator or quote cannot shift the columns of a neighbouring row.
        writer = csv.writer(
            output, lineterminator="\n", quoting=csv.QUOTE_ALL
        )
        writer.writerow(CSV_COLUMNS)

        for receipt in receipts:
            # DocDate format: DD/MM/YYYY (docs/06_schema_api.md §6.4.1)
            if receipt.invoice_date is not None:
                doc_date = receipt.invoice_date.strftime("%d/%m/%Y")
            elif receipt.created_at is not None:
                doc_date = receipt.created_at.strftime("%d/%m/%Y")
            else:
                doc_date = date.today().strftime("%d/%m/%Y")

            doc_no = receipt.invoice_number or f"REC-{str(receipt.id)[:8].upper()}"

            # SupplierCode generation
            if receipt.merchant_brn:
                cleaned_brn = re.sub(r"[^A-Z0-9]", "", receipt.merchant_brn.upper())
                supplier_code = f"SUPP-{cleaned_brn[:10]}"
            elif receipt.merchant_name:
                cleaned_name = re.sub(r"[^A-Z0-9]", "", receipt.merchant_name.upper())
                supplier_code = f"SUPP-{cleaned_name[:10]}"
            else:
                supplier_code = "SUPP-CASH"

            supplier_name = receipt.merchant_name or "Cash Supplier"
            has_tax = (
                receipt.tax_amount is not None
                and receipt.tax_amount > Decimal("0.00")
            )
            tax_code = "SST-6" if has_tax else "NONE"

            if receipt.line_items:
                net_cents, tax_by_line, _ = receipt_line_amounts(receipt)
                for item, net, allocated in zip(
                    receipt.line_items, net_cents, tax_by_line
                ):
                    desc = item.description or "General Item"
                    item_code = f"ITEM-{item.line_index + 1:02d}"
                    qty_str = _format_qty(item.quantity)

                    # UnitPrice is the tax-exclusive price, matching the net
                    # line amount; TotalAmount is what the line actually cost
                    # the buyer, so the invoice header still reconciles.
                    item_net = Decimal(net) / 100
                    item_tax = Decimal(allocated) / 100
                    item_total = item_net + item_tax
                    unit_price_str = f"{item_net:.2f}"
                    if item.quantity:
                        try:
                            unit_price_str = f"{item_net / Decimal(item.quantity):.2f}"
                        except (ArithmeticError, ValueError):  # pragma: no cover
                            unit_price_str = f"{item_net:.2f}"

                    writer.writerow(
                        [
                            _csv_text(doc_date),
                            _csv_text(doc_no),
                            _csv_text(supplier_code),
                            _csv_text(supplier_name),
                            _csv_text(desc),
                            _csv_text(item_code),
                            qty_str,
                            unit_price_str,
                            _csv_text(tax_code),
                            f"{item_tax:.2f}",
                            f"{item_total:.2f}",
                        ]
                    )

                # The till's printed rounding line is part of what the buyer
                # actually paid, so it needs a journal line of its own: without
                # one the batch posts RM 0.04 more than the receipt. Posted as a
                # zero-quantity adjustment so it cannot be mistaken for goods.
                rounding = receipt.rounding or Decimal("0.00")
                if rounding != Decimal("0.00"):
                    writer.writerow(
                        [
                            _csv_text(doc_date),
                            _csv_text(doc_no),
                            _csv_text(supplier_code),
                            _csv_text(supplier_name),
                            _csv_text("Rounding adjustment"),
                            _csv_text("ITEM-RND"),
                            "0",
                            f"{rounding:.2f}",
                            _csv_text("NONE"),
                            "0.00",
                            f"{rounding:.2f}",
                        ]
                    )
            else:
                # Receipt without line items -> single summary row
                desc = "General Purchase"
                item_code = "ITEM-01"
                qty_str = "1"
                subtotal_val = (
                    receipt.subtotal
                    or receipt.grand_total
                    or Decimal("0.00")
                )
                tax_val = receipt.tax_amount or Decimal("0.00")
                total_val = receipt.grand_total or (subtotal_val + tax_val)

                writer.writerow(
                    [
                        _csv_text(doc_date),
                        _csv_text(doc_no),
                        _csv_text(supplier_code),
                        _csv_text(supplier_name),
                        _csv_text(desc),
                        _csv_text(item_code),
                        qty_str,
                        f"{subtotal_val:.2f}",
                        _csv_text(tax_code),
                        f"{tax_val:.2f}",
                        f"{total_val:.2f}",
                    ]
                )
        return output.getvalue()

    if db is not None:
        return _execute(db)
    with session_scope() as session:
        return _execute(session)


def generate_myinvois_json(
    client_id: uuid.UUID | str,
    month: str | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """Generate the LHDN MyInvois v1.1-shaped JSON envelope.

    Mirrors the official SDK sample layout
    (1.1-Invoice-MultiLineItem-Sample.json) and docs/06_schema_api.md §6.4.2.
    The output is a draft: it is not validated against the LHDN schema and is
    never submitted. Generating it does not change any receipt status.
    """

    def _execute(session: Session) -> dict[str, Any]:
        receipts = _fetch_export_receipts(session, client_id, month=month)
        invoices: list[dict[str, Any]] = []

        for receipt in receipts:
            doc_id = receipt.invoice_number or f"REC-{str(receipt.id)[:8].upper()}"

            if receipt.invoice_date is not None:
                issue_date = receipt.invoice_date.isoformat()
            elif receipt.created_at is not None:
                issue_date = receipt.created_at.date().isoformat()
            else:
                issue_date = date.today().isoformat()

            if receipt.created_at is not None:
                issue_time = receipt.created_at.strftime("%H:%M:%SZ")
            else:
                issue_time = "00:00:00Z"

            merchant_name = receipt.merchant_name or "Unknown Supplier"
            party_ids: list[dict[str, Any]] = []
            if receipt.merchant_brn:
                party_ids.append(
                    {"ID": [{"_": receipt.merchant_brn, "schemeID": "BRN"}]}
                )
            # The SST scheme ID admits only the registration token itself. Stored
            # values can carry a BRN alongside it ("200401032489 / Y24-..."), so
            # canonicalise before shipping; an unparseable value is omitted rather
            # than exported as a malformed party ID.
            sst_number = extract_sst_number(receipt.merchant_sst)
            if sst_number:
                party_ids.append({"ID": [{"_": sst_number, "schemeID": "SST"}]})
            if not party_ids:
                party_ids.append({"ID": [{"_": "NA", "schemeID": "BRN"}]})

            tax_dec = receipt.tax_amount or Decimal("0.00")
            # UBL demands a tax-exclusive header that equals the sum of the
            # tax-exclusive line amounts. On an inclusive receipt the printed
            # subtotal is *not* that number — the printed line totals include
            # GST — so the header is rebuilt from the lines and the tax is
            # allocated back out of them. Deriving it from ``grand_total - tax``
            # keeps a receipt with no readable lines internally consistent too.
            net_cents, tax_by_line_cents, header_net_cents = receipt_line_amounts(
                receipt
            )
            if receipt.line_items:
                subtotal_dec = Decimal(header_net_cents) / 100
            elif receipt.subtotal is not None:
                subtotal_dec = receipt.subtotal
            else:
                subtotal_dec = max(
                    (receipt.grand_total or Decimal("0.00")) - tax_dec,
                    Decimal("0.00"),
                )
            grand_total_dec = (
                receipt.grand_total
                if receipt.grand_total is not None
                else (subtotal_dec + tax_dec)
            )

            subtotal_num = round(float(subtotal_dec), 2)
            tax_num = round(float(tax_dec), 2)
            grand_total_num = round(float(grand_total_dec), 2)
            rounding_num = round(float(receipt.rounding or Decimal("0.00")), 2)

            supplier_party = [
                {
                    "Party": [
                        {
                            "PartyName": [{"Name": [{"_": merchant_name}]}],
                            "PartyLegalEntity": [
                                {"RegistrationName": [{"_": merchant_name}]}
                            ],
                            "PartyIdentification": party_ids,
                        }
                    ]
                }
            ]

            legal_monetary_total = [
                {
                    "LineExtensionAmount": [
                        {"_": subtotal_num, "currencyID": "MYR"}
                    ],
                    "TaxExclusiveAmount": [
                        {"_": subtotal_num, "currencyID": "MYR"}
                    ],
                    "TaxInclusiveAmount": [
                        {"_": grand_total_num, "currencyID": "MYR"}
                    ],
                    "AllowanceTotalAmount": [{"_": 0.0, "currencyID": "MYR"}],
                    "ChargeTotalAmount": [{"_": 0.0, "currencyID": "MYR"}],
                    # The receipt's own printed rounding line, signed. Emitting a
                    # hardcoded 0.00 left the UBL block unable to explain why
                    # TaxInclusiveAmount + tax differs from PayableAmount on a
                    # receipt whose till rounded to 5 sen.
                    "PayableRoundingAmount": [
                        {"_": rounding_num, "currencyID": "MYR"}
                    ],
                    "PayableAmount": [{"_": grand_total_num, "currencyID": "MYR"}],
                }
            ]

            tax_total = [
                {
                    "TaxAmount": [{"_": tax_num, "currencyID": "MYR"}],
                    "TaxSubtotal": [
                        {
                            "TaxableAmount": [
                                {"_": subtotal_num, "currencyID": "MYR"}
                            ],
                            "TaxAmount": [{"_": tax_num, "currencyID": "MYR"}],
                            "TaxCategory": [
                                {
                                    "ID": [{"_": "01"}],
                                    "TaxScheme": [
                                        {
                                            "ID": [
                                                {
                                                    "_": "OTH",
                                                    "schemeID": "UN/ECE 5153",
                                                    "schemeAgencyID": "6",
                                                }
                                            ]
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]

            invoice_lines: list[dict[str, Any]] = []
            if receipt.line_items:
                for idx, (item, net_cents, allocated) in enumerate(
                    zip(receipt.line_items, net_cents, tax_by_line_cents)
                ):
                    qty_num = (
                        float(item.quantity)
                        if item.quantity is not None
                        else 1.0
                    )
                    # LineExtensionAmount is tax-exclusive by definition, and
                    # PriceAmount must agree with it so qty x price == line.
                    line_tot_num = round(net_cents / 100, 2)
                    unit_p_num = (
                        round(line_tot_num / qty_num, 2) if qty_num else line_tot_num
                    )

                    item_tax_num = round(allocated / 100, 2)

                    line_id = str(
                        item.line_index + 1
                        if item.line_index is not None
                        else idx + 1
                    )
                    invoice_lines.append(
                        {
                            "ID": [{"_": line_id}],
                            "InvoicedQuantity": [
                                {"_": qty_num, "unitCode": "C62"}
                            ],
                            "LineExtensionAmount": [
                                {"_": line_tot_num, "currencyID": "MYR"}
                            ],
                            "TaxTotal": [
                                {"TaxAmount": [{"_": item_tax_num, "currencyID": "MYR"}]}
                            ],
                            "Item": [
                                {"Description": [{"_": item.description or "Item"}]}
                            ],
                            "Price": [
                                {"PriceAmount": [{"_": unit_p_num, "currencyID": "MYR"}]}
                            ],
                            "ItemPriceExtension": [
                                {"Amount": [{"_": line_tot_num, "currencyID": "MYR"}]}
                            ],
                        }
                    )
            else:
                invoice_lines.append(
                    {
                        "ID": [{"_": "1"}],
                        "InvoicedQuantity": [{"_": 1.0, "unitCode": "C62"}],
                        "LineExtensionAmount": [
                            {"_": subtotal_num, "currencyID": "MYR"}
                        ],
                        "TaxTotal": [
                            {"TaxAmount": [{"_": tax_num, "currencyID": "MYR"}]}
                        ],
                        "Item": [{"Description": [{"_": merchant_name}]}],
                        "Price": [
                            {"PriceAmount": [{"_": subtotal_num, "currencyID": "MYR"}]}
                        ],
                        "ItemPriceExtension": [
                            {"Amount": [{"_": subtotal_num, "currencyID": "MYR"}]}
                        ],
                    }
                )

            inv_obj: dict[str, Any] = {
                "ID": [{"_": doc_id}],
                "IssueDate": [{"_": issue_date}],
                "IssueTime": [{"_": issue_time}],
                "InvoiceTypeCode": [{"_": "01", "listVersionID": "1.1"}],
                "DocumentCurrencyCode": [{"_": "MYR"}],
                "TaxCurrencyCode": [{"_": "MYR"}],
                "AccountingSupplierParty": supplier_party,
                "LegalMonetaryTotal": legal_monetary_total,
                "TaxTotal": tax_total,
                "InvoiceLine": invoice_lines,
            }
            invoices.append(inv_obj)

        payload = MyInvoisPayload(
            {
                "_D": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
                "_A": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
                "_B": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
                "Invoice": invoices,
            }
        )
        return payload

    if db is not None:
        return _execute(db)
    with session_scope() as session:
        return _execute(session)


__all__ = [
    "CSV_COLUMNS",
    "EXPORTABLE_STATUSES",
    "MONTH_PATTERN",
    "MyInvoisPayload",
    "allocate_tax_cents",
    "generate_accounting_csv",
    "generate_myinvois_json",
    "mark_exported",
    "month_clause",
    "parse_month_range",
]
