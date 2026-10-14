"""Audit trail for manual overrides (compliance) — docs/06_schema_api.md §6.1.4."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, GUID, UTCDateTime, utcnow, uuid_pk

if TYPE_CHECKING:
    from app.models.receipt import Receipt


class ReceiptAuditLog(Base):
    __tablename__ = "receipt_audit_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    receipt_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    field_name: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # e.g. 'grand_total'
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow
    )

    receipt: Mapped["Receipt"] = relationship(back_populates="audit_logs")

    __table_args__ = (Index("idx_audit_logs_receipt", "receipt_id"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ReceiptAuditLog {self.field_name} {self.old_value!r}->{self.new_value!r}>"


__all__ = ["ReceiptAuditLog"]
