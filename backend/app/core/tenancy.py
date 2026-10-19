"""Route-level tenant guard (docs/06_schema_api.md §6.3.5, REQ-106).

Every client-scoped route resolves its workspace through here so the isolation
rule lives in exactly one place: a client row is only visible to the accountant
that owns it, and anything else is a 404 (never a 403 -- a foreign workspace must
not even be confirmed to exist).
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.client import Client


def get_owned_client(
    db: Session, client_id: uuid.UUID, accountant_id: uuid.UUID
) -> Client:
    """Fetch a client workspace, enforcing ``clients.accountant_id == accountant_id``."""
    client = db.execute(
        select(Client).where(
            Client.id == client_id, Client.accountant_id == accountant_id
        )
    ).scalar_one_or_none()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Client not found"
        )
    return client


def get_active_owned_client(
    db: Session, client_id: uuid.UUID, accountant_id: uuid.UUID
) -> Client:
    """Like :func:`get_owned_client`, but soft-deleted workspaces are 404.

    Client management keeps using the plain guard so a workspace can be
    reactivated; every receipt/export/dashboard route uses this one, so a
    deletion actually revokes data access.
    """
    client = get_owned_client(db, client_id, accountant_id)
    if not client.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Client not found"
        )
    return client


__all__ = ["get_active_owned_client", "get_owned_client"]
