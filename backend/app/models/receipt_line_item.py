"""Receipt line items with spatial bounding boxes — docs/06_schema_api.md §6.1.3."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import (
    GUID,
    Base,
    Confidence,
    JSONBType,
    Money,
    Quantity,
    UTCDateTime,
    utcnow,
    uuid_pk,
)

if TYPE_CHECKING:
    from app.models.receipt import Receipt


class ReceiptLineItem(Base):
    __tablename__ = "receipt_line_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    receipt_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False
    )
    line_index: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # 0-indexed on receipt
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(
        Quantity, nullable=False, default=Decimal("1.000")
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0.00")
    )
    line_total: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0.00")
    )
    # Fixed taxonomy: F&B, HARDWARE, WORKSHOP, RETAIL, OTHER (docs/06 §6.1.3).
    expense_category: Mapped[str] = mapped_column(
        String(16), nullable=False, default="OTHER", server_default="OTHER"
    )

    # Spatial bounding box & confidence for GUI highlighting
    confidence: Mapped[Decimal] = mapped_column(
        Confidence, nullable=False, default=Decimal("1.00")
    )
    # [x_min, y_min, x_max, y_max] normalized to 0.0-1.0 (docs/05_trd.md §5.2.2)
    bbox: Mapped[list[float] | None] = mapped_column(JSONBType(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow
    )

    receipt: Mapped[Receipt] = relationship(back_populates="line_items")

    __table_args__ = (Index("idx_line_items_receipt", "receipt_id", "line_index"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ReceiptLineItem {self.line_index} {self.description!r} {self.line_total}>"


__all__ = ["ReceiptLineItem"]
