"""SQLAlchemy ORM models mirroring the DDL in docs/06_schema_api.md §6.1.

This package is also the mapper-registration boundary: importing it imports every
model module, so schema bootstrap lives here rather than importing back into
``app.core.database``.
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.database import Base, engine
from app.models.client import Client
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_audit_log import ReceiptAuditLog
from app.models.receipt_line_item import ReceiptLineItem

__all__ = [
    "Client",
    "Receipt",
    "ReceiptStatus",
    "ReceiptAuditLog",
    "ReceiptLineItem",
    "init_db",
]


def init_db(target_engine: Engine | None = None) -> None:
    """Create the ``pgcrypto`` extension and all tables if they do not exist."""
    target_engine = engine if target_engine is None else target_engine

    if target_engine.dialect.name == "postgresql":
        with target_engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

    Base.metadata.create_all(target_engine)
