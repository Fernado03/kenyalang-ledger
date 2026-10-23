"""Receipt/invoice header entity — docs/06_schema_api.md §6.1.2."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import (
    GUID,
    Base,
    Confidence,
    JSONBType,
    Money,
    UTCDateTime,
    utcnow,
    uuid_pk,
)

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.receipt_audit_log import ReceiptAuditLog
    from app.models.receipt_line_item import ReceiptLineItem


class ReceiptStatus(str, enum.Enum):
    """Pipeline execution and verification lifecycle states (§6.1.2)."""

    PENDING_UPLOAD = "PENDING_UPLOAD"
    UPLOADED = "UPLOADED"
    PROCESSING_OCR = "PROCESSING_OCR"
    PROCESSING_LLM = "PROCESSING_LLM"
    VALIDATING_MATH = "VALIDATING_MATH"
    STATUS_NEEDS_REVIEW = "STATUS_NEEDS_REVIEW"
    STATUS_AUTO_VERIFIED = "STATUS_AUTO_VERIFIED"
    STATUS_VERIFIED = "STATUS_VERIFIED"
    STATUS_EXPORTED = "STATUS_EXPORTED"
    STATUS_REJECTED = "STATUS_REJECTED"
    ERR_UNREADABLE = "ERR_UNREADABLE"
    ERR_TIMEOUT = "ERR_TIMEOUT"
    ERR_FILE_CORRUPT = "ERR_FILE_CORRUPT"
    # The extraction provider was unavailable or refused the request. The
    # failure is terminal for this receipt but is not a defect in the file.
    ERR_EXTRACTION = "ERR_EXTRACTION"

    @property
    def is_error(self) -> bool:
        return self.value.startswith("ERR_")


# Persist the value strings ("PENDING_UPLOAD") rather than the Python member names so
# the column stays wire-compatible with the documented enum.
RECEIPT_STATUS_ENUM = SAEnum(
    ReceiptStatus,
    name="receipt_status",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    validate_strings=True,
)


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[uuid.UUID] = uuid_pk()
    client_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )

    # Ingestion & storage metadata
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    # Pipeline execution state
    status: Mapped[ReceiptStatus] = mapped_column(
        RECEIPT_STATUS_ENUM, nullable=False, default=ReceiptStatus.PENDING_UPLOAD
    )
    processing_error: Mapped[str | None] = mapped_column(String(255))

    # Extracted header entities
    merchant_name: Mapped[str | None] = mapped_column(String(255))
    merchant_brn: Mapped[str | None] = mapped_column(String(64))
    merchant_sst: Mapped[str | None] = mapped_column(String(64))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    invoice_number: Mapped[str | None] = mapped_column(String(128))

    # Financial totals — NUMERIC for absolute precision in Ringgit
    subtotal: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(
        Money, nullable=True, default=Decimal("0.00")
    )
    grand_total: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    # Printed till-rounding line ("ROUNDING -0.04"), signed. Separate from
    # grand_total so the arithmetic identity can balance without either widening
    # the tolerance or pretending the receipt was wrong.
    rounding: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    # Whether the printed line totals already include the tax (docs/05_trd.md
    # §5.4). Malaysian retail receipts print GST-inclusive line amounts, but
    # trade invoices print them exclusive, so the basis has to travel with the
    # data instead of being assumed by the reconciler. NULL means "not
    # recorded" — older rows — and the reconciler then infers from the numbers.
    amount_basis: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Validation & confidence telemetry
    overall_confidence: Mapped[Decimal | None] = mapped_column(
        Confidence, nullable=True
    )
    math_discrepancy: Mapped[Decimal | None] = mapped_column(
        Money, nullable=True, default=Decimal("0.00")
    )
    validation_flags: Mapped[list] = mapped_column(
        JSONBType(), nullable=False, default=list
    )
    # Per-field provenance for the review console (docs/06_schema_api.md §6.3.3):
    # [{'name': 'grand_total', 'confidence': 0.97, 'bbox': [x, y, x, y]}, ...].
    field_provenance: Mapped[list] = mapped_column(
        JSONBType(), nullable=False, default=list
    )
    ocr_raw_tokens: Mapped[list] = mapped_column(
        JSONBType(), nullable=False, default=list
    )

    # Timestamps & verification audit
    verified_by: Mapped[uuid.UUID | None] = mapped_column(GUID, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    exported_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow
    )

    client: Mapped[Client] = relationship(back_populates="receipts")
    line_items: Mapped[list[ReceiptLineItem]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
        order_by="ReceiptLineItem.line_index",
        passive_deletes=True,
    )
    audit_logs: Mapped[list[ReceiptAuditLog]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("idx_receipts_client_status", "client_id", "status"),
        Index("idx_receipts_client_date", "client_id", "invoice_date"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Receipt {self.id} {self.original_filename!r} {self.status.value}>"


__all__ = ["RECEIPT_STATUS_ENUM", "Receipt", "ReceiptStatus"]
