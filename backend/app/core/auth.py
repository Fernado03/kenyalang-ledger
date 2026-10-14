"""Request authentication and the multi-tenant accountant guard.

The session guard from docs/05_trd.md §5.1 is a hard requirement: every client
query is scoped to ``clients.accountant_id == <current accountant>``. Auth
provider selection is a later step (no IdP is specified in the docs), so the
current dependency reads the accountant UUID from the ``X-Accountant-Id`` header
and rejects malformed or missing credentials with 401.
"""

from __future__ import annotations

import uuid

from fastapi import Header, HTTPException, status

ACCOUNTANT_HEADER = "X-Accountant-Id"


def get_current_accountant_id(
    x_accountant_id: str
    | None = Header(
        None, alias=ACCOUNTANT_HEADER, description="Authenticated accountant UUID."
    ),
) -> uuid.UUID:
    """Resolve the acting accountant, or raise 401."""
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


__all__ = ["ACCOUNTANT_HEADER", "get_current_accountant_id"]
