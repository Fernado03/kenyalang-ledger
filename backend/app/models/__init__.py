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
    "ReceiptAuditLog",
    "ReceiptLineItem",
    "ReceiptStatus",
    "init_db",
]


CATEGORY_DDL = "VARCHAR(16) NOT NULL DEFAULT 'OTHER'"


def init_db(target_engine: Engine | None = None) -> None:
    """Create tables if needed, then apply the additive demo schema guards.

    There is no migration framework in this demo. ``create_all`` covers fresh
    databases; the guards below widen databases created by an older build
    without destroying rows.
    """
    target_engine = engine if target_engine is None else target_engine

    if target_engine.dialect.name == "postgresql":
        with target_engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

    Base.metadata.create_all(target_engine)
    _apply_additive_guards(target_engine)


def _apply_additive_guards(target_engine: Engine) -> None:
    """Add enum values/columns introduced after the first demo schema."""
    if target_engine.dialect.name == "postgresql":
        with target_engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TYPE receipt_status ADD VALUE IF NOT EXISTS 'ERR_EXTRACTION'"
                )
            )
        with target_engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE receipt_line_items "
                    f"ADD COLUMN IF NOT EXISTS expense_category {CATEGORY_DDL}"
                )
            )
        return

    with target_engine.begin() as conn:
        columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(receipt_line_items)"))
        }
        if "expense_category" not in columns:
            conn.execute(
                text(
                    "ALTER TABLE receipt_line_items "
                    f"ADD COLUMN expense_category {CATEGORY_DDL}"
                )
            )
