"""Engine construction, session management and schema bootstrap.

Implements the DDL in docs/06_schema_api.md §6.1 for PostgreSQL 15 (production
multi-tenant) and SQLite (standalone single-tenant development, per docs/05_trd.md
§5.1). The dialect is selected from ``DATABASE_URL``:

* ``postgresql://...`` -> PostgreSQL with ``pgcrypto`` for ``gen_random_uuid()``
* unset, empty or any other scheme -> in-memory/local SQLite fallback
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import DateTime, Numeric, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import JSON, TypeDecorator, Uuid

DEFAULT_SQLITE_URL = "sqlite:///./kenyalang.db"
POSTGRES_SCHEMES = (
    "postgresql",
    "postgres",
    "postgresql+psycopg2",
    "postgresql+psycop",
)


def get_database_url() -> str:
    """Resolve the active database URL, falling back to SQLite when unset."""
    url = os.getenv("DATABASE_URL", "").strip()
    return url or DEFAULT_SQLITE_URL


class JSONBType(TypeDecorator):
    """``JSONB`` on PostgreSQL, plain ``JSON`` elsewhere (SQLite has no JSONB)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class GUID(TypeDecorator):
    """Portable UUID column: native ``UUID`` on PostgreSQL, ``CHAR(36)`` elsewhere."""

    impl = Uuid
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(Uuid(as_uuid=True))


class UTCDateTime(TypeDecorator):
    """Timezone-aware ``TIMESTAMPTZ`` on PostgreSQL; stores naive UTC on SQLite."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(DateTime(timezone=True))
        return dialect.type_descriptor(DateTime())

    def process_result_value(self, value, dialect):
        # SQLite has no TIMESTAMPTZ and drops the offset on write, so restore UTC
        # on read: the DDL promises TIMESTAMPTZ and the API contract emits "Z".
        if value is not None and dialect.name != "postgresql" and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


def create_db_engine(url: str | None = None) -> Engine:
    """Build an engine sized for the dialect: pooled for Postgres, shared for SQLite."""
    url = get_database_url() if url is None else url
    if url.startswith("sqlite"):
        # Local dev/test fallback. No pooling so an in-memory DB survives across
        # the threadpool connections FastAPI uses.
        engine = create_engine(url, future=True)
    else:
        engine = create_engine(
            url,
            future=True,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_recycle=1800,
        )

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(
            dbapi_connection, _record
        ):
            # SQLite ignores FK constraints unless asked; the tenant CASCADE in §6.1 needs them.
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine: Engine = create_db_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def utcnow() -> datetime:
    """Timezone-aware UTC now; default for every ``created_at``/``updated_at`` column."""
    return datetime.now(UTC)


# Portable column types shared across models.
Money = Numeric(12, 2)  # exact Ringgit precision (grand_total, tax_amount, ...)
Quantity = Numeric(10, 3)  # line item quantity, e.g. 1.000
Confidence = Numeric(3, 2)  # 0.00 to 1.00


def new_uuid() -> uuid.UUID:
    """Primary-key generator (UUID4 client-side, mirroring ``gen_random_uuid()``)."""
    return uuid.uuid4()


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(GUID(), primary_key=True, default=new_uuid)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts and background workers."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()



