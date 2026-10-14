"""Receipt ingestion endpoint (docs/06_schema_api.md §6.3.1, REQ-101/103/104).

``POST /api/v1/clients/{client_id}/receipts/upload`` accepts a batch of images,
stores each blob in tenant-scoped storage, runs the full pipeline inline
(OpenCV normalize -> EasyOCR -> LLM extraction -> deterministic audit) and
persists a ``Receipt`` plus its ``ReceiptLineItem`` rows.

Processing is synchronous rather than queued: the docs describe async dispatch
(§5.1) but specify no broker, and the review console's contract only needs the
receipt rows to exist when the 202 returns. The response therefore reports each
file's *terminal* status instead of the doc's placeholder ``PROCESSING_OCR``.

A receipt that fails the pipeline is still persisted, with an ``ERR_*`` status and
``processing_error`` set, so failures are auditable rather than lost.

The batch is atomic: every file is read and validated before anything is written,
and a rejected file rolls back the whole batch (no partial receipts, no orphan
blobs). ``ERR_TIMEOUT`` is reserved for a genuine SDK timeout; an infrastructure
failure (missing credentials, provider outage) is not attributable to the receipt
and is surfaced as ``503`` with the batch rolled back.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_accountant_id
from app.core.database import get_db
from app.core.storage import (
    delete_receipt_file,
    safe_filename,
    save_receipt_file,
    storage_root,
)
from app.core.tenancy import get_owned_client
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_audit_log import ReceiptAuditLog
from app.models.receipt_line_item import ReceiptLineItem
from app.pipeline.extractor import ExtractionError, ExtractionTimeout, extract_receipt
from app.pipeline.ocr_engine import OCRToken, process_receipt_image, tokens_to_dicts
from app.pipeline.preprocessor import ImageDecodeError
from app.services.reconciler import MATH_TOLERANCE, AuditResult, ReconcilerService
from app.schemas.receipt import (
    ParsedReceiptSchema,
    ReceiptDetailLineItem,
    ReceiptDetailResponse,
    ReceiptField,
    ReceiptListItem,
    ReceiptListResponse,
    ReceiptOcrToken,
    ReceiptUploadItem,
    ReceiptUploadResponse,
    ReceiptUpdateRequest,
    ReceiptUpdateResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["receipts"])

DbSession = Annotated[Session, Depends(get_db)]
AccountantId = Annotated[uuid.UUID, Depends(get_current_accountant_id)]

# docs/06_schema_api.md §6.3.1: max 50 files per batch.
MAX_BATCH_FILES: Final = 50
# docs/05_trd.md §5.6.2: 15MB ceiling per file.
MAX_FILE_BYTES: Final = 15 * 1024 * 1024
# docs/03_appflow.md: below this the image is noise, not a receipt.
MIN_OCR_TOKENS: Final = 5

# docs/06_schema_api.md §6.3.2: Inbox status filter. "VERIFIED" spans both the
# auto-verified and the accountant-confirmed state (docs/03_appflow.md §3.2).
INBOX_STATUS_FILTERS: Final = {
    "ALL": None,
    "NEEDS_REVIEW": (ReceiptStatus.STATUS_NEEDS_REVIEW,),
    "VERIFIED": (ReceiptStatus.STATUS_AUTO_VERIFIED, ReceiptStatus.STATUS_VERIFIED),
    "EXPORTED": (ReceiptStatus.STATUS_EXPORTED,),
}
# Docs/06_schema_api.md §6.3.2: default page size, and a hard ceiling so a
# misconfigured console cannot pull the whole ledger in one request.
DEFAULT_LIST_LIMIT: Final = 50
MAX_LIST_LIMIT: Final = 200

MATH_FLAG_PREFIX: Final = "MATH_MISMATCH_DELTA_"

# docs/05_trd.md §5.6.2: magic bytes decide, never the file extension.
ALLOWED_MIME_TYPES: Final = ("image/jpeg", "image/png", "image/heic", "application/pdf")

_MAGIC_SIGNATURES: Final = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"%PDF-", "application/pdf"),
)


def detect_mime_type(payload: bytes) -> str | None:
    """Sniff the container signature, returning None when unrecognized.

    HEIC/HEIF is detected structurally (ISO-BMFF ``ftyp`` box with a HEIC brand)
    since its brands vary by encoder and python-magic would drag in libmagic.
    """
    for signature, mime_type in _MAGIC_SIGNATURES:
        if payload.startswith(signature):
            return mime_type
    if (
        len(payload) >= 12
        and payload[4:8] == b"ftyp"
        and payload[8:12].startswith(b"hei")
    ):
        return "image/heic"
    return None


class PipelineOutcome:
    """Terminal state of one file's pipeline run, ready to persist."""

    def __init__(
        self,
        status: ReceiptStatus,
        parsed: ParsedReceiptSchema | None = None,
        audit: AuditResult | None = None,
        tokens: list[OCRToken] | None = None,
        error: str | None = None,
    ) -> None:
        self.status = status
        self.parsed = parsed
        self.audit = audit
        self.tokens = tokens or []
        self.error = error


def run_pipeline(payload: bytes) -> PipelineOutcome:
    """Bytes -> normalized image -> OCR tokens -> structured parse -> audit.

    Raises ``HTTPException(503)`` when the LLM stage is unavailable for reasons
    that have nothing to do with this receipt (missing credentials, provider
    outage). Those are not receipt defects, so they must not be recorded as an
    ``ERR_*`` row; the batch rolls back instead.
    """
    try:
        tokens = process_receipt_image(payload)
    except ImageDecodeError as exc:
        return PipelineOutcome(ReceiptStatus.ERR_FILE_CORRUPT, error=str(exc)[:255])

    if len(tokens) < MIN_OCR_TOKENS:
        return PipelineOutcome(
            ReceiptStatus.ERR_UNREADABLE,
            tokens=tokens,
            error=f"only {len(tokens)} OCR tokens detected",
        )

    try:
        parsed = extract_receipt(tokens)
    except ExtractionTimeout as exc:
        logger.warning("LLM extraction timed out: %s", exc)
        return PipelineOutcome(
            ReceiptStatus.ERR_TIMEOUT, tokens=tokens, error=str(exc)[:255]
        )
    except ExtractionError as exc:
        logger.error("LLM stage unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Extraction service unavailable; try again later",
        ) from exc

    audit = ReconcilerService.audit_receipt(parsed)
    return PipelineOutcome(audit.status, parsed=parsed, audit=audit, tokens=tokens)


def _persist_receipt(
    db: Session,
    *,
    receipt_id: UUID,
    client_id: UUID,
    filename: str,
    mime_type: str,
    file_size: int,
    storage_path: str,
    outcome: PipelineOutcome,
) -> Receipt:
    """Write the header row and, when extraction succeeded, its line items."""
    receipt = Receipt(
        id=receipt_id,
        client_id=client_id,
        original_filename=safe_filename(filename),
        storage_path=storage_path,
        mime_type=mime_type,
        file_size_bytes=file_size,
        status=outcome.status,
        processing_error=outcome.error,
        ocr_raw_tokens=tokens_to_dicts(outcome.tokens),
    )

    if outcome.parsed is not None and outcome.audit is not None:
        parsed = outcome.parsed
        audit = outcome.audit
        receipt.merchant_name = parsed.merchant_name
        receipt.merchant_brn = parsed.merchant_brn
        receipt.merchant_sst = parsed.merchant_sst
        receipt.invoice_date = parsed.invoice_date
        receipt.invoice_number = parsed.invoice_number
        receipt.subtotal = parsed.subtotal
        receipt.tax_amount = parsed.tax_amount
        receipt.grand_total = parsed.grand_total
        receipt.overall_confidence = audit.overall_confidence
        receipt.math_discrepancy = audit.math_discrepancy
        receipt.validation_flags = audit.flags
        receipt.field_provenance = [
            {
                "name": field.name,
                "confidence": field.confidence,
                "bbox": field.bbox,
            }
            for field in parsed.fields
        ]
        receipt.line_items = [
            ReceiptLineItem(
                line_index=item.line_index,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=item.line_total,
                confidence=item.confidence,
                bbox=item.bbox,
            )
            for item in parsed.line_items
        ]

    db.add(receipt)
    return receipt


@router.post(
    "/clients/{client_id}/receipts/upload",
    response_model=ReceiptUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_receipts(
    client_id: uuid.UUID,
    db: DbSession,
    accountant_id: AccountantId,
    files: Annotated[list[UploadFile], File(description="Receipt images or PDFs")],
) -> ReceiptUploadResponse:
    """Ingest a batch of receipts and return each file's resulting status.

    The batch is validated and collected before anything is persisted, so a
    rejected file leaves no partial batch behind. Blobs written by this request
    are removed if the transaction fails.
    """
    get_owned_client(db, client_id, accountant_id)

    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No files uploaded"
        )
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Batch exceeds {MAX_BATCH_FILES} files",
        )

    # Preflight: read and validate every file before touching storage or the DB.
    staged: list[tuple[uuid.UUID, str, str, bytes]] = []
    for upload in files:
        filename = upload.filename or "receipt"
        payload = upload.file.read(MAX_FILE_BYTES + 1)

        if not payload:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{filename}: empty upload",
            )
        if len(payload) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"{filename}: exceeds {MAX_FILE_BYTES // (1024 * 1024)}MB limit",
            )

        mime_type = detect_mime_type(payload)
        if mime_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"{filename}: unsupported file type",
            )

        staged.append((uuid.uuid4(), filename, mime_type, payload))

    written_paths: list[str] = []
    accepted: list[ReceiptUploadItem] = []
    try:
        for receipt_id, filename, mime_type, payload in staged:
            storage_path = save_receipt_file(client_id, receipt_id, filename, payload)
            written_paths.append(storage_path)

            outcome = run_pipeline(payload)
            receipt = _persist_receipt(
                db,
                receipt_id=receipt_id,
                client_id=client_id,
                filename=filename,
                mime_type=mime_type,
                file_size=len(payload),
                storage_path=storage_path,
                outcome=outcome,
            )
            accepted.append(
                ReceiptUploadItem(
                    id=receipt_id, filename=filename, status=receipt.status
                )
            )

        db.commit()
    except Exception:
        db.rollback()
        for path in written_paths:
            delete_receipt_file(path)
        raise

    return ReceiptUploadResponse(
        batch_id=uuid.uuid4(),
        total_received=len(accepted),
        receipts=accepted,
    )


def _money_text(value: Decimal | None) -> str | None:
    """Serialize a Money column as a decimal string, preserving scale.

    FastAPI renders ``Decimal`` as a JSON number, which loses the exact decimal
    representation the review console's BigInt cents parser depends on
    (docs/06_schema_api.md §6.3.2).
    """
    return None if value is None else str(value)


def _receipt_or_404(db: Session, client_id: UUID, receipt_id: UUID) -> Receipt:
    """Fetch a receipt that belongs to ``client_id``, or 404.

    The tenant check is part of the lookup, so a receipt that exists under
    another workspace is indistinguishable from a missing one (docs/06_schema_api.md §6.3.5).
    """
    receipt = db.execute(
        select(Receipt).where(Receipt.id == receipt_id, Receipt.client_id == client_id)
    ).scalar_one_or_none()
    if receipt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    return receipt


def _build_provenance(rows: list) -> list[ReceiptField]:
    """Map the persisted JSONB provenance rows onto response entries."""
    fields: list[ReceiptField] = []
    for row in rows:
        name = row.get("name")
        if not isinstance(name, str) or not name:
            continue
        bbox = row.get("bbox")
        fields.append(
            ReceiptField(
                name=name,
                confidence=float(row.get("confidence", 0.0)),
                bbox=list(bbox) if isinstance(bbox, list) else None,
            )
        )
    return fields


def _build_ocr_tokens(rows: list) -> list[ReceiptOcrToken]:
    """Map the persisted OCR token dump onto response entries, skipping malformed rows."""
    tokens: list[ReceiptOcrToken] = []
    for row in rows:
        text = row.get("text")
        bbox = row.get("bbox")
        if not isinstance(text, str) or not isinstance(bbox, list) or len(bbox) != 4:
            continue
        tokens.append(
            ReceiptOcrToken(
                text=text,
                confidence=float(row.get("confidence", 0.0)),
                bbox=[float(value) for value in bbox],
                line_num=int(row.get("line_num", 0)),
            )
        )
    return tokens


def _build_line_items(receipt: Receipt) -> list[ReceiptDetailLineItem]:
    """Map persisted line-item rows, ordered by their printed position."""
    return [
        ReceiptDetailLineItem(
            id=item.id,
            line_index=item.line_index,
            description=item.description,
            quantity=str(item.quantity.quantize(Decimal("0.01"))),
            unit_price=_money_text(item.unit_price) or "0.00",
            line_total=_money_text(item.line_total) or "0.00",
            confidence=float(item.confidence),
            bbox=item.bbox,
        )
        for item in sorted(receipt.line_items, key=lambda row: row.line_index)
    ]


def _build_list_item(client_id: UUID, receipt: Receipt) -> ReceiptListItem:
    """Map a receipt row onto one Inbox row (§6.3.2)."""
    return ReceiptListItem(
        id=receipt.id,
        filename=receipt.original_filename,
        merchant_name=receipt.merchant_name,
        invoice_date=receipt.invoice_date,
        subtotal=_money_text(receipt.subtotal),
        tax_amount=_money_text(receipt.tax_amount),
        grand_total=_money_text(receipt.grand_total),
        status=receipt.status,
        validation_flags=list(receipt.validation_flags or []),
        overall_confidence=float(receipt.overall_confidence or 0.0),
        math_discrepancy=_money_text(receipt.math_discrepancy) or "0.00",
        line_item_count=len(receipt.line_items),
        image_url=f"/api/v1/clients/{client_id}/receipts/{receipt.id}/image",
    )


def _build_detail(client_id: UUID, receipt: Receipt) -> ReceiptDetailResponse:
    """Map a receipt row onto the full review-console payload (§6.3.3)."""
    return ReceiptDetailResponse(
        id=receipt.id,
        client_id=receipt.client_id,
        filename=receipt.original_filename,
        status=receipt.status,
        processing_error=receipt.processing_error,
        image_url=f"/api/v1/clients/{client_id}/receipts/{receipt.id}/image",
        merchant_name=receipt.merchant_name,
        merchant_brn=receipt.merchant_brn,
        merchant_sst=receipt.merchant_sst,
        invoice_date=receipt.invoice_date,
        invoice_number=receipt.invoice_number,
        subtotal=_money_text(receipt.subtotal),
        tax_amount=_money_text(receipt.tax_amount),
        grand_total=_money_text(receipt.grand_total),
        math_discrepancy=_money_text(receipt.math_discrepancy) or "0.00",
        overall_confidence=float(receipt.overall_confidence or 0.0),
        validation_flags=list(receipt.validation_flags or []),
        fields=_build_provenance(receipt.field_provenance or []),
        line_items=_build_line_items(receipt),
        ocr_tokens=_build_ocr_tokens(receipt.ocr_raw_tokens or []),
        created_at=receipt.created_at,
        updated_at=receipt.updated_at,
        verified_at=receipt.verified_at,
    )


@router.get(
    "/clients/{client_id}/receipts",
    response_model=ReceiptListResponse,
)
def list_client_receipts(
    client_id: uuid.UUID,
    db: DbSession,
    accountant_id: AccountantId,
    status: str = Query("ALL", pattern="^(ALL|NEEDS_REVIEW|VERIFIED|EXPORTED)$"),
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
) -> ReceiptListResponse:
    """List a client's receipts for the SCR-02 inbox (§6.3.2)."""
    get_owned_client(db, client_id, accountant_id)

    base = select(Receipt).where(Receipt.client_id == client_id)
    count_query = (
        select(func.count()).select_from(Receipt).where(Receipt.client_id == client_id)
    )
    allowed = INBOX_STATUS_FILTERS.get(status)
    if allowed is not None:
        base = base.where(Receipt.status.in_(allowed))
        count_query = count_query.where(Receipt.status.in_(allowed))

    total = db.execute(count_query).scalar_one()
    rows = (
        db.execute(base.order_by(Receipt.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return ReceiptListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[_build_list_item(client_id, receipt) for receipt in rows],
    )


@router.get(
    "/clients/{client_id}/receipts/{receipt_id}",
    response_model=ReceiptDetailResponse,
)
def get_client_receipt(
    client_id: uuid.UUID,
    receipt_id: uuid.UUID,
    db: DbSession,
    accountant_id: AccountantId,
) -> ReceiptDetailResponse:
    """Full receipt payload for the SCR-03 review console (§6.3.3)."""
    get_owned_client(db, client_id, accountant_id)
    return _build_detail(client_id, _receipt_or_404(db, client_id, receipt_id))


@router.get("/clients/{client_id}/receipts/{receipt_id}/image")
def get_client_receipt_image(
    client_id: uuid.UUID,
    receipt_id: uuid.UUID,
    db: DbSession,
    accountant_id: AccountantId,
) -> FileResponse:
    """Stream the stored receipt image for the review console viewport (§6.3.3)."""
    get_owned_client(db, client_id, accountant_id)
    receipt = _receipt_or_404(db, client_id, receipt_id)

    path = storage_root() / receipt.storage_path
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Receipt image not found")
    return FileResponse(path, media_type=receipt.mime_type)


@router.put(
    "/clients/{client_id}/receipts/{receipt_id}",
    response_model=ReceiptUpdateResponse,
)
def update_client_receipt(
    client_id: uuid.UUID,
    receipt_id: uuid.UUID,
    payload: ReceiptUpdateRequest,
    db: DbSession,
    accountant_id: AccountantId,
) -> ReceiptUpdateResponse:
    """Apply the accountant's corrections and verify the receipt (§6.3.4).

    Header keys absent from the payload are left alone; an explicit ``null``
    clears the stored value. Line items are replaced wholesale, every change is
    recorded in ``receipt_audit_logs``, and the math discrepancy plus any
    ``MATH_MISMATCH_DELTA_*`` flag are recomputed from the submitted values.
    """
    get_owned_client(db, client_id, accountant_id)
    receipt = _receipt_or_404(db, client_id, receipt_id)

    changed: list[tuple[str, str | None, str | None]] = []

    def apply_field(name: str, value, current) -> None:
        if name not in payload.model_fields_set:
            return
        if value == current:
            return
        changed.append(
            (
                name,
                None if current is None else str(current),
                None if value is None else str(value),
            )
        )
        setattr(receipt, name, value)

    apply_field("merchant_name", payload.merchant_name, receipt.merchant_name)
    apply_field("merchant_brn", payload.merchant_brn, receipt.merchant_brn)
    apply_field("merchant_sst", payload.merchant_sst, receipt.merchant_sst)
    if "invoice_date" in payload.model_fields_set:
        apply_field("invoice_date", payload.invoice_date, receipt.invoice_date)
    apply_field("invoice_number", payload.invoice_number, receipt.invoice_number)
    apply_field("subtotal", payload.subtotal, receipt.subtotal)
    apply_field("tax_amount", payload.tax_amount, receipt.tax_amount)
    apply_field("grand_total", payload.grand_total, receipt.grand_total)

    if "line_items" in payload.model_fields_set:
        previous = [
            (row.description, str(row.line_total)) for row in receipt.line_items
        ]
        incoming = [(item.description, item.line_total) for item in payload.line_items]
        if previous != incoming:
            changed.append(
                ("line_items", f"{len(previous)} rows", f"{len(incoming)} rows")
            )
        for row in list(receipt.line_items):
            db.delete(row)
        db.flush()
        receipt.line_items = [
            ReceiptLineItem(
                line_index=index,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=item.line_total,
            )
            for index, item in enumerate(payload.line_items)
        ]

    tax = receipt.tax_amount if receipt.tax_amount is not None else Decimal("0.00")
    line_sum = sum(
        (item.line_total for item in payload.line_items), start=Decimal("0.00")
    )
    discrepancy = (
        abs(line_sum + tax - receipt.grand_total)
        if receipt.grand_total is not None
        else Decimal("0.00")
    )
    receipt.math_discrepancy = discrepancy

    flags = [
        flag
        for flag in receipt.validation_flags or []
        if not flag.startswith(MATH_FLAG_PREFIX)
    ]
    if discrepancy > MATH_TOLERANCE:
        flags.append(f"{MATH_FLAG_PREFIX}{discrepancy:.2f}")
    receipt.validation_flags = flags

    receipt.status = ReceiptStatus.STATUS_VERIFIED
    receipt.verified_by = accountant_id
    receipt.verified_at = datetime.utcnow()

    for field_name, old_value, new_value in changed:
        db.add(
            ReceiptAuditLog(
                receipt_id=receipt.id,
                user_id=accountant_id,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
            )
        )

    db.commit()
    db.refresh(receipt)

    return ReceiptUpdateResponse(
        id=receipt.id,
        status=receipt.status,
        updated_at=receipt.updated_at,
        verified_by=receipt.verified_by,
        math_discrepancy=_money_text(receipt.math_discrepancy) or "0.00",
    )


__all__ = [
    "MAX_BATCH_FILES",
    "MAX_FILE_BYTES",
    "detect_mime_type",
    "router",
    "run_pipeline",
]
