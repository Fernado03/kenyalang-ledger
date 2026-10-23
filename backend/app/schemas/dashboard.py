"""Dashboard summary schemas (docs/06_schema_api.md §6.3.6)."""

from __future__ import annotations

from pydantic import BaseModel


class TopSupplier(BaseModel):
    supplier_name: str
    total_spend: str
    receipt_count: int


class CategoryBreakdown(BaseModel):
    category: str
    total_spend: str


class DashboardSummary(BaseModel):
    month: str
    # Newest month this client has any receipt in (YYYY-MM), or None when the
    # workspace is empty. The console opens on the current month, which is the
    # wrong place to land when all the data is older — this lets it say so, or
    # follow the data, instead of presenting a page of RM 0.00 as the truth.
    latest_month: str | None
    total_spend: str
    top_suppliers: list[TopSupplier]
    category_breakdown: list[CategoryBreakdown]


__all__ = [
    "CategoryBreakdown",
    "DashboardSummary",
    "TopSupplier",
]
