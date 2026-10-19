"""Pydantic schemas for the export endpoints (docs/06_schema_api.md §6.4)."""

from __future__ import annotations

from pydantic import BaseModel


class MarkExportsResponse(BaseModel):
    """Number of receipts moved from verified to exported by an explicit mark."""

    updated: int


__all__ = ["MarkExportsResponse"]
