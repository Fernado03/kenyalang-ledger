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
    selected = month or _current_month()
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
