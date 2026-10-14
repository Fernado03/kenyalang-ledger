"""Client workspace (tenant partition for accountants) — docs/06_schema_api.md §6.1.1."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, GUID, UTCDateTime, utcnow, uuid_pk

if TYPE_CHECKING:
    from app.models.receipt import Receipt

# Industry categories documented in §6.1.1.
INDUSTRY_CATEGORIES = ("F&B", "HARDWARE", "WORKSHOP", "RETAIL")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = uuid_pk()
    accountant_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    registration_number: Mapped[str | None] = mapped_column(String(64))  # SSM / BRN
    sst_number: Mapped[str | None] = mapped_column(String(64))  # SST registration no.
    industry_category: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow
    )

    receipts: Mapped[list["Receipt"]] = relationship(
        back_populates="client", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (Index("idx_clients_accountant", "accountant_id"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Client {self.id} {self.business_name!r}>"


__all__ = ["Client", "INDUSTRY_CATEGORIES"]
