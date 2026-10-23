"""Dashboard summary endpoint (docs/06_schema_api.md §6.3.6, REQ-110).

Read-only aggregates over receipts that count as spend: ``AUTO_VERIFIED``,
``VERIFIED``, and ``EXPORTED``. Draft, rejected, and failed receipts are
excluded. Category totals are pre-tax line totals, so they will not add up to
``total_spend`` whenever the receipts carry tax.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_accountant_id
from app.core.database import get_db
from app.core.tenancy import get_active_owned_client
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_line_item import ReceiptLineItem
from app.schemas.dashboard import (
    CategoryBreakdown,
    DashboardSummary,
    TopSupplier,
)
from app.services.classifier import EXPENSE_CATEGORIES
from app.services.export_engine import MONTH_PATTERN, month_clause, parse_month_range

router = APIRouter(tags=["dashboard"])

SPEND_STATUSES = (
    ReceiptStatus.STATUS_AUTO_VERIFIED,
    ReceiptStatus.STATUS_VERIFIED,
    ReceiptStatus.STATUS_EXPORTED,
)

TOP_SUPPLIER_LIMIT = 5
CENT = Decimal("0.01")


def _money(value: Decimal | None) -> str:
    """Fixed 2-decimal Ringgit string (never scientific notation)."""
    amount = Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
    return f"{amount:.2f}"


def _current_month() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def _default_month(client_id: uuid.UUID, db: Session, latest_month: str | None) -> str:
    """The month to show when the caller did not name one.

    The current month wins while it holds anything; otherwise follow the newest
    month that does. An empty workspace stays on the current month, where the
    zero is the truth rather than a hint that the data is elsewhere.
    """
    current = _current_month()
    if latest_month is None or latest_month == current:
        return current
    has_current = db.execute(
        select(func.count(Receipt.id)).where(
            Receipt.client_id == client_id, month_clause(current)
        )
    ).scalar_one()
    return current if has_current else latest_month


@router.get(
    "/clients/{client_id}/dashboard/summary",
    response_model=DashboardSummary,
)
def dashboard_summary(
    client_id: uuid.UUID,
    accountant_id: Annotated[uuid.UUID, Depends(get_current_accountant_id)],
    db: Annotated[Session, Depends(get_db)],
    month: Annotated[
        str | None,
        Query(
            description="Billing month in YYYY-MM format; defaults to the current UTC month",
            pattern=MONTH_PATTERN,
        ),
    ] = None,
) -> DashboardSummary:
    """Total spend, top suppliers, and category split for one client-month."""
    get_active_owned_client(db, client_id, accountant_id)

    # Newest month that actually holds a receipt for this client. A receipt
    # without an invoice_date falls back to its upload date, matching the
    # month_clause fallback below so "has data" and "counts in this month"
    # can never disagree.
    latest_row = db.execute(
        select(
            func.max(func.coalesce(Receipt.invoice_date, func.date(Receipt.created_at)))
        ).where(Receipt.client_id == client_id)
    ).scalar_one()
    latest_month = (
        f"{latest_row.year:04d}-{latest_row.month:02d}"
        if latest_row is not None
        else None
    )

    # "This month" is the right default for current books and the wrong one for
    # a workspace whose receipts are older: the console would open on a full
    # screen of RM 0.00 while the data sits one month back. Answer with the
    # month the caller should show instead of making every client re-derive it.
    selected = month or _default_month(client_id, db, latest_month)
    # Validate the trimmed form too, not just the raw query string.
    parse_month_range(selected)
    clause = month_clause(selected)

    spend_filters = [Receipt.client_id == client_id, Receipt.status.in_(SPEND_STATUSES)]
    if clause is not None:
        spend_filters.append(clause)

    total = db.execute(
        select(func.coalesce(func.sum(Receipt.grand_total), 0)).where(*spend_filters)
    ).scalar_one()

    supplier_rows = db.execute(
        select(
            Receipt.merchant_name,
            func.coalesce(func.sum(Receipt.grand_total), 0).label("spend"),
            func.count(Receipt.id).label("receipt_count"),
        )
        .where(
            *spend_filters,
            Receipt.merchant_name.is_not(None),
            Receipt.merchant_name != "",
        )
        .group_by(Receipt.merchant_name)
        .order_by(func.sum(Receipt.grand_total).desc(), Receipt.merchant_name.asc())
        .limit(TOP_SUPPLIER_LIMIT)
    ).all()

    category_rows = db.execute(
        select(
            ReceiptLineItem.expense_category,
            func.coalesce(func.sum(ReceiptLineItem.line_total), 0).label("spend"),
        )
        .join(Receipt, Receipt.id == ReceiptLineItem.receipt_id)
        .where(*spend_filters)
        .group_by(ReceiptLineItem.expense_category)
    ).all()
    category_totals = {row[0]: row[1] for row in category_rows}

    return DashboardSummary(
        month=selected,
        latest_month=latest_month,
        total_spend=_money(total),
        top_suppliers=[
            TopSupplier(
                supplier_name=row[0],
                total_spend=_money(row[1]),
                receipt_count=int(row[2]),
            )
            for row in supplier_rows
        ],
        category_breakdown=[
            CategoryBreakdown(
                category=category,
                total_spend=_money(category_totals.get(category)),
            )
            for category in EXPENSE_CATEGORIES
        ],
    )


__all__ = ["router"]
