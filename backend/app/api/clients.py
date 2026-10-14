"""Health probe and client-workspace CRUD endpoints.

Routes follow docs/06_schema_api.md §6.3.5. The client routes are mounted at
``/api/clients`` (the doc's ``/api/v1`` prefix is reserved for the ingestion and
export endpoints defined in later steps).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_accountant_id
from app.core.database import get_db
from app.core.tenancy import get_owned_client
from app.models.client import Client
from app.schemas.client import (
    ClientCreate,
    ClientListResponse,
    ClientRead,
    ClientUpdate,
    HealthResponse,
)

router = APIRouter(tags=["clients"])

DbSession = Annotated[Session, Depends(get_db)]
AccountantId = Annotated[uuid.UUID, Depends(get_current_accountant_id)]

API_VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse)
def health(db: DbSession) -> HealthResponse:
    """Liveness/readiness probe: reports database reachability and active dialect."""
    dialect = db.bind.dialect.name if db.bind is not None else "unknown"
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:  # pragma: no cover - only on a broken database
        db_status = "unavailable"
    return HealthResponse(
        status="ok", database=db_status, dialect=dialect, version=API_VERSION
    )


@router.get("/clients", response_model=ClientListResponse)
def list_clients(db: DbSession, accountant_id: AccountantId) -> ClientListResponse:
    """All workspaces owned by the authenticated accountant."""
    clients = (
        db.execute(
            select(Client)
            .where(Client.accountant_id == accountant_id)
            .order_by(Client.created_at.desc(), Client.id)
        )
        .scalars()
        .all()
    )
    return ClientListResponse(items=[ClientRead.model_validate(c) for c in clients])


@router.post("/clients", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate, db: DbSession, accountant_id: AccountantId
) -> ClientRead:
    """Create a workspace; ``accountant_id`` is always taken from the session."""
    client = Client(accountant_id=accountant_id, **payload.model_dump())
    db.add(client)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Client could not be created"
        ) from exc
    db.refresh(client)
    return ClientRead.model_validate(client)


@router.get("/clients/{client_id}", response_model=ClientRead)
def get_client(
    client_id: uuid.UUID, db: DbSession, accountant_id: AccountantId
) -> ClientRead:
    return ClientRead.model_validate(get_owned_client(db, client_id, accountant_id))


@router.put("/clients/{client_id}", response_model=ClientRead)
def update_client(
    client_id: uuid.UUID,
    payload: ClientUpdate,
    db: DbSession,
    accountant_id: AccountantId,
) -> ClientRead:
    client = get_owned_client(db, client_id, accountant_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    db.commit()
    db.refresh(client)
    return ClientRead.model_validate(client)


@router.delete("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: uuid.UUID, db: DbSession, accountant_id: AccountantId
) -> Response:
    """Soft delete: flips ``is_active`` so receipt history survives the cascade."""
    client = get_owned_client(db, client_id, accountant_id)
    client.is_active = False
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
