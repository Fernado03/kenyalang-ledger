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
    total_spend: str
    top_suppliers: list[TopSupplier]
    category_breakdown: list[CategoryBreakdown]


__all__ = [
    "CategoryBreakdown",
    "DashboardSummary",
    "TopSupplier",
]
