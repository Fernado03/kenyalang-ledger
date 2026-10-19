"""Request authentication and the multi-tenant accountant guard.

The session guard from docs/05_trd.md §5.1 is a hard requirement: every client
query is scoped to ``clients.accountant_id == <current accountant>``. This demo
has no identity provider: ``X-Accountant-Id`` is a forgeable demo identity, not
authentication. It is accepted only when ``KENYALANG_ENV`` is ``local`` or
``test``; any other (or missing) environment disables it.
"""

from __future__ import annotations

import os
import uuid
from typing import Annotated

from fastapi import Header, HTTPException, status

ACCOUNTANT_HEADER = "X-Accountant-Id"
DEMO_ENVS = {"local", "test"}


def get_current_accountant_id(
    x_accountant_id: Annotated[
        str | None,
        Header(
            alias=ACCOUNTANT_HEADER,
            description="Demo accountant UUID (not authentication).",
        ),
    ] = None,
) -> uuid.UUID:
    """Resolve the acting accountant, or raise 401."""
    if os.getenv("KENYALANG_ENV", "").strip().lower() not in DEMO_ENVS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Demo authentication is disabled",
        )
    if not x_accountant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing {ACCOUNTANT_HEADER} header",
        )
    try:
        return uuid.UUID(x_accountant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed accountant id"
        ) from exc


__all__ = ["ACCOUNTANT_HEADER", "DEMO_ENVS", "get_current_accountant_id"]
