"""Export endpoints for AutoCount / SQL Account CSV and MyInvois-shaped JSON.

Implements docs/06_schema_api.md §6.4 (REQ-108):
- GET  /api/v1/clients/{client_id}/exports/accounting-csv
- GET  /api/v1/clients/{client_id}/exports/myinvois-json
- POST /api/v1/clients/{client_id}/exports/mark

Downloads are pure reads. Only the explicit mark action advances a receipt from
``VERIFIED``/``AUTO_VERIFIED`` to ``EXPORTED``.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_accountant_id
from app.core.database import get_db
from app.core.tenancy import get_active_owned_client
from app.schemas.export import MarkExportsResponse
from app.services.export_engine import (
    MONTH_PATTERN,
    generate_accounting_csv,
    generate_myinvois_json,
    mark_exported,
)

router = APIRouter(prefix="/clients/{client_id}/exports", tags=["exports"])

DbSession = Annotated[Session, Depends(get_db)]
AccountantId = Annotated[UUID, Depends(get_current_accountant_id)]

MONTH_QUERY = Query(
    None,
    description="Billing month in YYYY-MM format (e.g. 2026-09)",
    pattern=MONTH_PATTERN,
)


def _file_suffix(month: str | None) -> str:
    """Format safe filename month suffix (e.g. '202609' or 'all')."""
    if not month:
        return "all"
    cleaned = month.strip().replace("-", "")
    return cleaned if cleaned else "all"


@router.get("/accounting-csv")
def export_accounting_csv(
    client_id: UUID,
    accountant_id: AccountantId,
    db: DbSession,
    month: str | None = MONTH_QUERY,
) -> Response:
    """Export AutoCount / SQL Account purchase journal batch CSV (docs/06 §6.4.1)."""
    get_active_owned_client(db, client_id, accountant_id)
    csv_content = generate_accounting_csv(client_id, month=month, db=db)
    suffix = _file_suffix(month)
    filename = f"Kenyalang_PurJournal_{suffix}.csv"

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/csv; charset=utf-8",
        },
    )


@router.get("/myinvois-json")
def export_myinvois_json(
    client_id: UUID,
    accountant_id: AccountantId,
    db: DbSession,
    month: str | None = MONTH_QUERY,
) -> JSONResponse:
    """Export the draft MyInvois v1.1-shaped JSON envelope (docs/06 §6.4.2)."""
    get_active_owned_client(db, client_id, accountant_id)
    payload = generate_myinvois_json(client_id, month=month, db=db)
    suffix = _file_suffix(month)
    filename = f"Kenyalang_MyInvois_{suffix}.json"

    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post("/mark", response_model=MarkExportsResponse)
def mark_exports(
    client_id: UUID,
    accountant_id: AccountantId,
    db: DbSession,
    month: str | None = MONTH_QUERY,
) -> MarkExportsResponse:
    """Mark verified receipts in the period as exported; repeat calls are no-ops."""
    get_active_owned_client(db, client_id, accountant_id)
    updated = mark_exported(db, client_id, month=month, actor_id=accountant_id)
    return MarkExportsResponse(updated=updated)


__all__ = ["router"]
