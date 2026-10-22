"""Receipt extraction, reconciliation and upload contracts (docs/06_schema_api.md §6.2).

``ExtractedReceiptData`` is the schema handed to the LLM through ``instructor``:
flat scalars only. Per-field confidence and bounding boxes are attached afterwards by the
extractor as ``ExtractedField`` provenance entries, which is what the reconciler
audits (docs/05_trd.md §5.4) and what the review console highlights.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.receipt import ReceiptStatus


def _finite_money(value: Decimal | None) -> Decimal | None:
    """Reject NaN/Infinity at the LLM trust boundary (docs/05_trd.md §5.4)."""
    if value is not None and not value.is_finite():
        raise ValueError("monetary value must be finite")
    return value


def _validate_bbox(bbox: list[float] | None) -> list[float] | None:
    """``[x_min, y_min, x_max, y_max]``: four ordered, normalized corners."""
    if bbox is None:
        return None
    if len(bbox) != 4:
        raise ValueError(
            "bbox must have exactly four coordinates [x_min, y_min, x_max, y_max]"
        )
    if not all(0.0 <= coordinate <= 1.0 for coordinate in bbox):
        raise ValueError("bbox coordinates must be normalized to 0.0-1.0")
    if bbox[0] > bbox[2] or bbox[1] > bbox[3]:
        raise ValueError(
            "bbox corners must be ordered: x_min <= x_max and y_min <= y_max"
        )
    return bbox


class LineItemSchema(BaseModel):
    """A single parsed receipt line (docs/06_schema_api.md §6.2)."""

    line_index: int = Field(..., ge=0)
    description: str
    quantity: Decimal = Decimal("1.00")
    unit_price: Decimal = Decimal("0.00")
    line_total: Decimal = Decimal("0.00")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    # [x_min, y_min, x_max, y_max] normalized to 0.0-1.0 (docs/05_trd.md §5.2.2)
    bbox: list[float] | None = None

    _validate_bbox = field_validator("bbox")(_validate_bbox)
    _finite_money = field_validator("quantity", "unit_price", "line_total")(
        _finite_money
    )


class ExtractedReceiptData(BaseModel):
    """Structured extraction schema passed directly to the LLM (§6.2)."""

    merchant_name: str | None = Field(
        None, description="Trade name of supplier/shop"
    )
    merchant_brn: str | None = Field(
        None, description="Malaysian Business Registration Number"
    )
    merchant_sst: str | None = Field(
        None, description="SST registration number if visible"
    )
    invoice_date: date | None = Field(
        None, description="Transaction date on the receipt"
    )
    invoice_number: str | None = Field(
        None, description="Receipt or Invoice sequence number"
    )
    subtotal: Decimal | None = Field(None, description="Subtotal before tax")
    tax_amount: Decimal | None = Field(
        Decimal("0.00"), description="Total SST or service tax"
    )
    # Nullable so a missing total reaches the audit instead of aborting extraction;
    # the reconciler flags it INVALID_GRAND_TOTAL (docs/05_trd.md §5.4).
    grand_total: Decimal | None = Field(
        None, description="Final payable amount in MYR"
    )
    line_items: list[LineItemSchema] = Field(default_factory=list)

    _finite_money = field_validator("subtotal", "tax_amount", "grand_total")(
        _finite_money
    )


class ExtractedField(BaseModel):
    """Per-field provenance: the §6.2 ``ExtractedField<T>`` envelope minus ``value``.

    The value itself stays on the parent schema so there is exactly one source of
    truth per field; this entry only records where the value came from and how
    much the OCR engine trusted it.
    """

    name: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    # [x_min, y_min, x_max, y_max] normalized to 0.0-1.0 (docs/05_trd.md §5.2.2)
    bbox: list[float] | None = None

    _validate_bbox = field_validator("bbox")(_validate_bbox)


class ParsedReceiptSchema(ExtractedReceiptData):
    """Reconciler input (docs/05_trd.md §5.4): extraction payload + field provenance."""

    fields: list[ExtractedField] = Field(default_factory=list)

    def get_fields(self) -> list[ExtractedField]:
        """Every audited field: header provenance followed by the line items."""
        items = [
            ExtractedField(
                name=f"line_items[{i}]", confidence=item.confidence, bbox=item.bbox
            )
            for i, item in enumerate(self.line_items)
        ]
        return [*self.fields, *items]


class ReceiptUploadItem(BaseModel):
    """One accepted file in the batch response (docs/06_schema_api.md §6.3.1)."""

    id: UUID
    filename: str
    status: ReceiptStatus


class ReceiptUploadResponse(BaseModel):
    """``202 Accepted`` envelope for a receipt batch upload (§6.3.1)."""

    batch_id: UUID
    total_received: int
    receipts: list[ReceiptUploadItem]


class ReceiptField(BaseModel):
    """Per-field provenance entry returned by the review console (§6.3.3)."""

    name: str
    confidence: float
    # [x_min, y_min, x_max, y_max] normalized to 0.0-1.0, or null when unsupported.
    bbox: list[float] | None = None


class ReceiptOcrToken(BaseModel):
    """One raw OCR token with its position in the source image (§6.3.3)."""

    text: str
    confidence: float
    bbox: list[float]
    line_num: int


class ReceiptListItem(BaseModel):
    """One row of the Inbox list (docs/06_schema_api.md §6.3.2)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    merchant_name: str | None
    invoice_date: date | None
    subtotal: Decimal | None
    tax_amount: Decimal | None
    grand_total: Decimal | None
    status: ReceiptStatus
    validation_flags: list[str]
    overall_confidence: float | None
    math_discrepancy: Decimal | None
    line_item_count: int
    image_url: str


class ReceiptListResponse(BaseModel):
    """``200 OK`` envelope for the Inbox list (§6.3.2)."""

    total: int
    limit: int
    offset: int
    items: list[ReceiptListItem]
    # Every filter bucket for this client, ignoring the active filter, so the
    # inbox tabs can show counts without five more round-trips.
    status_counts: dict[str, int]


class ReceiptDetailLineItem(BaseModel):
    """A persisted line item with its provenance (§6.3.3)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    line_index: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal
    expense_category: str = "OTHER"
    confidence: float
    # [x_min, y_min, x_max, y_max] normalized to 0.0-1.0, or null when unsupported.
    bbox: list[float] | None = None


class ReceiptDetailResponse(BaseModel):
    """Full receipt payload for the review console (docs/06_schema_api.md §6.3.3)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID
    filename: str
    status: ReceiptStatus
    processing_error: str | None
    image_url: str
    merchant_name: str | None
    merchant_brn: str | None
    merchant_sst: str | None
    invoice_date: date | None
    invoice_number: str | None
    subtotal: Decimal | None
    tax_amount: Decimal | None
    grand_total: Decimal | None
    math_discrepancy: Decimal | None
    overall_confidence: float | None
    validation_flags: list[str]
    fields: list[ReceiptField]
    line_items: list[ReceiptDetailLineItem]
    ocr_tokens: list[ReceiptOcrToken]
    created_at: datetime
    updated_at: datetime
    verified_at: datetime | None


class ReceiptUpdateLineItem(BaseModel):
    """A line item submitted by the review console (§6.3.4)."""

    description: str
    quantity: Decimal = Decimal("1.000")
    unit_price: Decimal = Decimal("0.00")
    line_total: Decimal = Decimal("0.00")

    _finite_money = field_validator("quantity", "unit_price", "line_total")(
        _finite_money
    )


class ReceiptUpdateRequest(BaseModel):
    """``PUT`` body: every header field nullable, line items replaced wholesale.

    A missing header key means "leave it alone"; an explicit ``null`` clears it
    (docs/06_schema_api.md §6.3.4). ``line_items`` is optional: when the key is
    absent the stored rows are kept, so a header-only save cannot silently
    delete a receipt's lines. An explicit empty list clears them, which is the
    legitimate state for a receipt the accountant re-keyed by hand.
    """

    merchant_name: str | None = None
    merchant_brn: str | None = None
    merchant_sst: str | None = None
    invoice_date: date | None = None
    invoice_number: str | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    grand_total: Decimal | None = None
    line_items: list[ReceiptUpdateLineItem] | None = None

    _finite_money = field_validator("subtotal", "tax_amount", "grand_total")(
        _finite_money
    )


class ReceiptUpdateResponse(BaseModel):
    """``200 OK`` envelope for the verify flow (§6.3.4)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: ReceiptStatus
    updated_at: datetime
    verified_by: UUID | None
    math_discrepancy: Decimal | None


class ReceiptAuditRead(BaseModel):
    """One manual-override audit entry (docs/06_schema_api.md §6.1.4)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    field_name: str
    old_value: str | None
    new_value: str | None
    created_at: datetime


class ReceiptAuditResponse(BaseModel):
    """``200 OK`` envelope for the receipt audit trail (§6.3.7)."""

    items: list[ReceiptAuditRead]


__all__ = [
    "ExtractedField",
    "ExtractedReceiptData",
    "LineItemSchema",
    "ParsedReceiptSchema",
    "ReceiptAuditRead",
    "ReceiptAuditResponse",
    "ReceiptDetailLineItem",
    "ReceiptDetailResponse",
    "ReceiptField",
    "ReceiptListItem",
    "ReceiptListResponse",
    "ReceiptOcrToken",
    "ReceiptUpdateLineItem",
    "ReceiptUpdateRequest",
    "ReceiptUpdateResponse",
    "ReceiptUploadItem",
    "ReceiptUploadResponse",
]
