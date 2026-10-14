"""Dual-format export engine for accounting systems and LHDN compliance.

Implements docs/05_trd.md §5.5 and docs/06_schema_api.md §6.4:
1. AutoCount / SQL Account purchase journal CSV.
2. Official LHDN MyInvois v1.1 JSON payload matching
   dataset/official_lhdn_sample/1.1-Invoice-MultiLineItem-Sample.json.
"""

from __future__ import annotations

import calendar
import csv
import io
import re
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.database import session_scope
from app.models.receipt import Receipt, ReceiptStatus

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

def _parse_month_range(month: str | None) -> tuple[date, date] | None:
    """Parse 'YYYY-MM' into inclusive (start_date, end_date), or None if unset."""
    if not month:
        return None
    cleaned = month.strip()
    if not cleaned:
        return None
    year_str, month_str = cleaned.split("-")
    year, month_num = int(year_str), int(month_str)
    _, last_day = calendar.monthrange(year, month_num)
    return date(year, month_num, 1), date(year, month_num, last_day)


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

    date_range = _parse_month_range(month)
    if date_range is not None:
        start_date, end_date = date_range
        stmt = stmt.where(
            or_(
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
        )

    return list(db.execute(stmt).unique().scalars().all())


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
        writer = csv.writer(output, lineterminator="\n")
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
                subtotal = receipt.subtotal or sum(
                    (it.line_total for it in receipt.line_items), Decimal("0.00")
                )
                for item in receipt.line_items:
                    desc = item.description or "General Item"
                    item_code = f"ITEM-{item.line_index + 1:02d}"
                    qty_str = _format_qty(item.quantity)
                    unit_price_str = f"{item.unit_price:.2f}"

                    if has_tax and subtotal > Decimal("0.00") and receipt.tax_amount:
                        item_tax = (
                            item.line_total / subtotal * receipt.tax_amount
                        ).quantize(Decimal("0.01"))
                    else:
                        item_tax = Decimal("0.00")

                    item_total = (item.line_total + item_tax).quantize(Decimal("0.01"))

                    writer.writerow(
                        [
                            doc_date,
                            doc_no,
                            supplier_code,
                            supplier_name,
                            desc,
                            item_code,
                            qty_str,
                            unit_price_str,
                            tax_code,
                            f"{item_tax:.2f}",
                            f"{item_total:.2f}",
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
                        doc_date,
                        doc_no,
                        supplier_code,
                        supplier_name,
                        desc,
                        item_code,
                        qty_str,
                        f"{subtotal_val:.2f}",
                        tax_code,
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
    """Generate LHDN MyInvois v1.1 JSON payload.

    Conforms to official SDK document envelope (1.1-Invoice-MultiLineItem-Sample.json)
    and docs/06_schema_api.md §6.4.2.
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
            if receipt.merchant_sst:
                party_ids.append(
                    {"ID": [{"_": receipt.merchant_sst, "schemeID": "SST"}]}
                )
            if not party_ids:
                party_ids.append({"ID": [{"_": "NA", "schemeID": "BRN"}]})

            subtotal_dec = (
                receipt.subtotal
                if receipt.subtotal is not None
                else (receipt.grand_total or Decimal("0.00"))
            )
            tax_dec = receipt.tax_amount or Decimal("0.00")
            grand_total_dec = (
                receipt.grand_total
                if receipt.grand_total is not None
                else (subtotal_dec + tax_dec)
            )

            subtotal_num = round(float(subtotal_dec), 2)
            tax_num = round(float(tax_dec), 2)
            grand_total_num = round(float(grand_total_dec), 2)

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
                    "PayableRoundingAmount": [{"_": 0.0, "currencyID": "MYR"}],
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
                for idx, item in enumerate(receipt.line_items):
                    qty_num = (
                        float(item.quantity)
                        if item.quantity is not None
                        else 1.0
                    )
                    unit_p_num = (
                        float(item.unit_price)
                        if item.unit_price is not None
                        else 0.0
                    )
                    line_tot_num = (
                        float(item.line_total)
                        if item.line_total is not None
                        else round(qty_num * unit_p_num, 2)
                    )

                    if subtotal_num > 0 and tax_num > 0:
                        item_tax_num = round((line_tot_num / subtotal_num) * tax_num, 2)
                    else:
                        item_tax_num = 0.0

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
    "MyInvoisPayload",
    "generate_accounting_csv",
    "generate_myinvois_json",
]
