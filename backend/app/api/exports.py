"""Export endpoints for AutoCount / SQL Account CSV and LHDN MyInvois v1.1 JSON.

Implements docs/06_schema_api.md §6.4 (REQ-108):
- GET /api/v1/clients/{client_id}/exports/accounting-csv
- GET /api/v1/clients/{client_id}/exports/myinvois-json
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_accountant_id
from app.core.database import get_db
from app.core.tenancy import get_owned_client
from app.services.export_engine import (
    generate_accounting_csv,
    generate_myinvois_json,
)

router = APIRouter(prefix="/clients/{client_id}/exports", tags=["exports"])


def _file_suffix(month: str | None) -> str:
    """Format safe filename month suffix (e.g. '202609' or 'all')."""
    if not month:
        return "all"
    cleaned = month.strip().replace("-", "")
    return cleaned if cleaned else "all"


@router.get("/accounting-csv")
def export_accounting_csv(
    client_id: UUID,
    month: str | None = Query(
        None,
        description="Billing month in YYYY-MM format (e.g. 2026-09)",
        pattern=r"^\d{4}-\d{2}$",
    ),
    accountant_id: UUID = Depends(get_current_accountant_id),
    db: Session = Depends(get_db),
) -> Response:
    """Export AutoCount / SQL Account purchase journal batch CSV (docs/06 §6.4.1)."""
    get_owned_client(db, client_id, accountant_id)
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
    month: str | None = Query(
        None,
        description="Billing month in YYYY-MM format (e.g. 2026-09)",
        pattern=r"^\d{4}-\d{2}$",
    ),
    accountant_id: UUID = Depends(get_current_accountant_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Export official LHDN MyInvois v1.1 document JSON (docs/06 §6.4.2)."""
    get_owned_client(db, client_id, accountant_id)
    payload = generate_myinvois_json(client_id, month=month, db=db)
    suffix = _file_suffix(month)
    filename = f"Kenyalang_MyInvois_{suffix}.json"

    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


__all__ = ["router"]
