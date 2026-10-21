"""Health probe and client-workspace CRUD endpoints.

Routes follow docs/06_schema_api.md §6.3.5. The client routes are mounted at
``/api/clients`` (the doc's ``/api/v1`` prefix is reserved for the ingestion and
export endpoints defined in later steps).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import case, func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.auth import get_current_accountant_id
from app.core.database import get_db
from app.core.tenancy import get_owned_client
from app.models.client import Client
from app.models.receipt import Receipt, ReceiptStatus
from app.schemas.client import (
    ClientCreate,
    ClientListResponse,
    ClientRead,
    ClientSummary,
    ClientUpdate,
    HealthLiveResponse,
    HealthResponse,
)

router = APIRouter(tags=["clients"])

DbSession = Annotated[Session, Depends(get_db)]
AccountantId = Annotated[uuid.UUID, Depends(get_current_accountant_id)]

API_VERSION = "0.1.0"


@router.get("/health/live", response_model=HealthLiveResponse)
def health_live() -> HealthLiveResponse:
    """Liveness: the process is up. Deliberately does not touch the database."""
    return HealthLiveResponse(status="ok", version=API_VERSION)


@router.get("/health/ready", response_model=HealthResponse)
def health_ready(db: DbSession) -> HealthResponse:
    """Readiness: return 200 only when the database answers a trivial query."""
    dialect = db.bind.dialect.name if db.bind is not None else "unknown"
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from exc
    return HealthResponse(
        status="ok", database="connected", dialect=dialect, version=API_VERSION
    )


@router.get("/clients", response_model=ClientListResponse)
def list_clients(db: DbSession, accountant_id: AccountantId) -> ClientListResponse:
    """All workspaces owned by the authenticated accountant, with receipt counts."""
    clients = (
        db.execute(
            select(Client)
            .where(Client.accountant_id == accountant_id)
            .order_by(Client.created_at.desc(), Client.id)
        )
        .scalars()
        .all()
    )
    if not clients:
        return ClientListResponse(items=[])

    unreviewed = func.coalesce(
        func.sum(
            case((Receipt.status == ReceiptStatus.STATUS_NEEDS_REVIEW, 1), else_=0)
        ),
        0,
    )
    verified = func.coalesce(
        func.sum(
            case(
                (
                    Receipt.status.in_(
                        (
                            ReceiptStatus.STATUS_AUTO_VERIFIED,
                            ReceiptStatus.STATUS_VERIFIED,
                            # Exporting is a step after verification, so an
                            # exported receipt is still a verified one; without
                            # this a client whose whole month was exported shows
                            # a misleading "0 verified".
                            ReceiptStatus.STATUS_EXPORTED,
                        )
                    ),
                    1,
                ),
                else_=0,
            )
        ),
        0,
    )
    total = func.count(Receipt.id)
    rows = db.execute(
        select(Receipt.client_id, unreviewed, verified, total)
        .where(Receipt.client_id.in_([c.id for c in clients]))
        .group_by(Receipt.client_id)
    ).all()
    counts = {row[0]: (int(row[1]), int(row[2]), int(row[3])) for row in rows}

    return ClientListResponse(
        items=[
            ClientSummary(
                **ClientRead.model_validate(c).model_dump(),
                unreviewed_count=counts.get(c.id, (0, 0, 0))[0],
                verified_count=counts.get(c.id, (0, 0, 0))[1],
                total_count=counts.get(c.id, (0, 0, 0))[2],
            )
            for c in clients
        ]
    )


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
