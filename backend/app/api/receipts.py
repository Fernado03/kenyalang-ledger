"""Receipt ingestion and review-console endpoints (docs/06_schema_api.md §6.3).

``POST /api/v1/clients/{client_id}/receipts/upload`` accepts a batch of images,
stores each blob in tenant-scoped storage, writes a ``PROCESSING_OCR``
placeholder row and returns ``202 Accepted``. The OCR/extraction pipeline runs
afterwards in a FastAPI ``BackgroundTask`` (docs/05_trd.md §5.1): the demo has no
broker or worker, so a task lost to a restart leaves the receipt in a
``PROCESSING_*`` state and the accountant can re-upload it.

Batch preflight is atomic: every file's size and magic bytes are validated
before anything is written, so a rejected batch leaves no receipts and no
blobs. A duplicate (same workspace, sanitized filename and byte size) returns
the existing receipt instead of writing a second copy.

Failures inside the worker are terminal per receipt: the row is updated to an
``ERR_*`` status with ``processing_error`` so a bad file is auditable rather
than silently stuck. An extraction provider outage is recorded as
``ERR_EXTRACTION``; it is not the accountant's file, but the demo has no retry
queue, so the receipt must still leave the processing state.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Annotated, Final
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.auth import get_current_accountant_id
from app.core.database import get_db, session_scope, utcnow
from app.core.storage import (
    delete_receipt_file,
    load_receipt_file,
    safe_filename,
    save_receipt_file,
)
from app.core.tenancy import get_active_owned_client
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_audit_log import ReceiptAuditLog
from app.models.receipt_line_item import ReceiptLineItem
from app.pipeline.extractor import (
    ExtractionError,
    ExtractionTimeout,
    extract_receipt,
)
from app.pipeline.ocr_engine import OCRToken, process_receipt_image, tokens_to_dicts
from app.pipeline.preprocessor import ImageDecodeError
from app.schemas.receipt import (
    ParsedReceiptSchema,
    ReceiptAuditRead,
    ReceiptAuditResponse,
    ReceiptDetailLineItem,
    ReceiptDetailResponse,
    ReceiptField,
    ReceiptListItem,
    ReceiptListResponse,
    ReceiptOcrToken,
    ReceiptUpdateRequest,
    ReceiptUpdateResponse,
    ReceiptUploadItem,
    ReceiptUploadResponse,
)
from app.services.classifier import classify_expense
from app.services.reconciler import MATH_TOLERANCE, AuditResult, ReconcilerService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["receipts"])

DbSession = Annotated[Session, Depends(get_db)]
AccountantId = Annotated[uuid.UUID, Depends(get_current_accountant_id)]

# docs/06_schema_api.md §6.3.1: max 50 files per batch.
MAX_BATCH_FILES: Final = 50
# docs/05_trd.md §5.6.2: 15MB ceiling per file.
MAX_FILE_BYTES: Final = 15 * 1024 * 1024
# docs/05_trd.md §5.6.2: 50MB ceiling for the whole upload request.
MAX_BATCH_BYTES: Final = 50 * 1024 * 1024
# docs/03_appflow.md: below this the image is noise, not a receipt.
MIN_OCR_TOKENS: Final = 5
# docs/06_schema_api.md §6.3.2: Inbox status filter. "VERIFIED" spans both the
# auto-verified and the accountant-confirmed state (docs/03_appflow.md §3.2).
INBOX_STATUS_FILTERS: Final = {
    "ALL": None,
    "NEEDS_REVIEW": (ReceiptStatus.STATUS_NEEDS_REVIEW,),
    "VERIFIED": (ReceiptStatus.STATUS_AUTO_VERIFIED, ReceiptStatus.STATUS_VERIFIED),
    "EXPORTED": (ReceiptStatus.STATUS_EXPORTED,),
    "REJECTED": (ReceiptStatus.STATUS_REJECTED,),
}
# Docs/06_schema_api.md §6.3.2: default page size, and a hard ceiling so a
# misconfigured console cannot pull the whole ledger in one request.
DEFAULT_LIST_LIMIT: Final = 50
MAX_LIST_LIMIT: Final = 200

# A worker may only act while the receipt is still processing. Anything else
# (a verified receipt, a terminal error) means a retry or a duplicate task must
# not overwrite the accountant's work.
PROCESSING_STATUSES: Final = frozenset(
    {
        ReceiptStatus.PROCESSING_OCR,
        ReceiptStatus.PROCESSING_LLM,
        ReceiptStatus.VALIDATING_MATH,
    }
)

# Terminal pipeline failures. A row in one of these states is dead: the worker
# will never touch it again, so an upload that matches one must not be treated
# as a duplicate (that would hand back the dead row and block any retry).
ERROR_STATUSES: Final = frozenset(
    member for member in ReceiptStatus if member.is_error
)

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


def _ocr_stage(payload: bytes, mime_type: str | None = None) -> list[OCRToken]:
    """Bytes -> normalized image -> OCR tokens.

    Kept separate from extraction so the worker can commit the
    ``PROCESSING_LLM`` transition between the two expensive stages.
    """
    if mime_type is None:
        return process_receipt_image(payload)
    return process_receipt_image(payload, mime_type)


def _extract_stage(tokens: list[OCRToken]) -> ParsedReceiptSchema:
    """OCR tokens -> validated LLM extraction with provenance attached."""
    return extract_receipt(tokens)


def run_pipeline(payload: bytes, mime_type: str | None = None) -> PipelineOutcome:
    """Compose the whole pipeline for callers that do not need stage commits.

    The async worker uses :func:`_ocr_stage`/:func:`_extract_stage` directly so
    each status transition is durable; this helper stays for scripts and unit
    tests and never raises: a provider outage becomes ``ERR_EXTRACTION``.
    """
    try:
        tokens = _ocr_stage(payload, mime_type)
    except ImageDecodeError as exc:
        return PipelineOutcome(ReceiptStatus.ERR_FILE_CORRUPT, error=str(exc)[:255])

    if len(tokens) < MIN_OCR_TOKENS:
        return PipelineOutcome(
            ReceiptStatus.ERR_UNREADABLE,
            tokens=tokens,
            error=f"only {len(tokens)} OCR tokens detected",
        )

    try:
        parsed = _extract_stage(tokens)
    except ExtractionTimeout as exc:
        logger.warning("LLM extraction timed out: %s", exc)
        return PipelineOutcome(
            ReceiptStatus.ERR_TIMEOUT, tokens=tokens, error=str(exc)[:255]
        )
    except ExtractionError as exc:
        logger.warning("LLM extraction failed: %s", exc)
        return PipelineOutcome(
            ReceiptStatus.ERR_EXTRACTION,
            tokens=tokens,
            error="extraction provider unavailable",
        )

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
) -> Receipt:
    """Insert the processing placeholder that the background task fills in."""
    receipt = Receipt(
        id=receipt_id,
        client_id=client_id,
        original_filename=safe_filename(filename),
        storage_path=storage_path,
        mime_type=mime_type,
        file_size_bytes=file_size,
        status=ReceiptStatus.PROCESSING_OCR,
    )
    db.add(receipt)
    db.flush()
    return receipt


def _apply_outcome(receipt: Receipt, outcome: PipelineOutcome) -> None:
    """Write a terminal pipeline result onto an existing receipt row."""
    receipt.status = outcome.status
    receipt.processing_error = outcome.error
    if outcome.tokens:
        receipt.ocr_raw_tokens = tokens_to_dicts(outcome.tokens)
    if outcome.parsed is None or outcome.audit is None:
        return

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
            expense_category=classify_expense(item.description),
            confidence=item.confidence,
            bbox=item.bbox,
        )
        for item in parsed.line_items
    ]


def _finish(receipt_id: UUID, outcome: PipelineOutcome) -> None:
    """Persist a terminal outcome in its own transaction, never overwriting review work."""
    with session_scope() as db:
        receipt = db.get(Receipt, receipt_id)
        if receipt is None or receipt.status not in PROCESSING_STATUSES:
            return
        _apply_outcome(receipt, outcome)


def _advance(receipt_id: UUID, expected: ReceiptStatus, new: ReceiptStatus) -> bool:
    """Commit a pipeline stage transition, returning False if the row moved on."""
    with session_scope() as db:
        receipt = db.get(Receipt, receipt_id)
        if receipt is None or receipt.status != expected:
            return False
        receipt.status = new
    return True


def process_receipt_background(receipt_id: UUID) -> None:
    """Run OCR -> extraction -> audit for one uploaded receipt.

    Each stage uses a short-lived session: a worker crash can lose the task but
    can never hold a transaction open or clobber a receipt the accountant has
    already reviewed.
    """
    try:
        with session_scope() as db:
            receipt = db.get(Receipt, receipt_id)
            if receipt is None or receipt.status not in PROCESSING_STATUSES:
                return
            storage_path = receipt.storage_path
            mime_type = receipt.mime_type

        try:
            payload = load_receipt_file(storage_path)
        except (FileNotFoundError, ValueError):
            _finish(
                receipt_id,
                PipelineOutcome(
                    ReceiptStatus.ERR_FILE_CORRUPT,
                    error="stored file could not be read",
                ),
            )
            return

        try:
            tokens = _ocr_stage(payload, mime_type)
        except ImageDecodeError as exc:
            _finish(
                receipt_id,
                PipelineOutcome(ReceiptStatus.ERR_FILE_CORRUPT, error=str(exc)[:255]),
            )
            return

        if len(tokens) < MIN_OCR_TOKENS:
            _finish(
                receipt_id,
                PipelineOutcome(
                    ReceiptStatus.ERR_UNREADABLE,
                    tokens=tokens,
                    error=f"only {len(tokens)} OCR tokens detected",
                ),
            )
            return

        if not _advance(
            receipt_id, ReceiptStatus.PROCESSING_OCR, ReceiptStatus.PROCESSING_LLM
        ):
            return

        try:
            parsed = _extract_stage(tokens)
        except ExtractionTimeout as exc:
            logger.warning("LLM extraction timed out for %s: %s", receipt_id, exc)
            _finish(
                receipt_id,
                PipelineOutcome(
                    ReceiptStatus.ERR_TIMEOUT,
                    tokens=tokens,
                    error=str(exc)[:255],
                ),
            )
            return
        except ExtractionError as exc:
            logger.warning("LLM extraction failed for %s: %s", receipt_id, exc)
            _finish(
                receipt_id,
                PipelineOutcome(
                    ReceiptStatus.ERR_EXTRACTION,
                    tokens=tokens,
                    error="extraction provider unavailable",
                ),
            )
            return

        if not _advance(
            receipt_id, ReceiptStatus.PROCESSING_LLM, ReceiptStatus.VALIDATING_MATH
        ):
            return

        audit = ReconcilerService.audit_receipt(parsed)
        _finish(
            receipt_id,
            PipelineOutcome(audit.status, parsed=parsed, audit=audit, tokens=tokens),
        )
    except Exception:  # pragma: no cover - last-resort guard for the worker
        logger.exception("unexpected failure while processing receipt %s", receipt_id)
        try:
            _finish(
                receipt_id,
                PipelineOutcome(
                    ReceiptStatus.ERR_UNREADABLE,
                    error="processing failed unexpectedly",
                ),
            )
        except Exception:
            logger.exception("could not record failure for receipt %s", receipt_id)


@router.post(
    "/clients/{client_id}/receipts/upload",
    response_model=ReceiptUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_receipts(
    client_id: uuid.UUID,
    db: DbSession,
    accountant_id: AccountantId,
    background_tasks: BackgroundTasks,
    files: Annotated[list[UploadFile], File(description="Receipt images or PDFs")],
) -> ReceiptUploadResponse:
    """Accept a batch, persist processing placeholders and queue the pipeline.

    The batch is validated and collected before anything is persisted, so a
    rejected file leaves no partial batch behind. Blobs written by this request
    are removed if the transaction fails.
    """
    get_active_owned_client(db, client_id, accountant_id)

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
    staged: list[tuple[str, str, bytes]] = []
    total_bytes = 0
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

        total_bytes += len(payload)
        if total_bytes > MAX_BATCH_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"Batch exceeds {MAX_BATCH_BYTES // (1024 * 1024)}MB total limit"
                ),
            )

        mime_type = detect_mime_type(payload)
        if mime_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"{filename}: unsupported file type",
            )

        staged.append((filename, mime_type, payload))

    written_paths: list[str] = []
    accepted: list[ReceiptUploadItem] = []
    queued: list[UUID] = []
    seen: dict[tuple[str, int], Receipt] = {}
    try:
        for filename, mime_type, payload in staged:
            safe_name = safe_filename(filename)
            identity = (safe_name, len(payload))
            existing = seen.get(identity)
            if existing is None:
                existing = db.execute(
                    select(Receipt)
                    .where(
                        Receipt.client_id == client_id,
                        Receipt.original_filename == safe_name,
                        Receipt.file_size_bytes == len(payload),
                        # A row that ended in an ERR_* state is dead: the worker
                        # never returns to it. Matching it here would hand the
                        # accountant the failure forever and make a retry of the
                        # same file impossible. PROCESSING_* rows still dedupe,
                        # because that run is genuinely in flight.
                        Receipt.status.not_in(ERROR_STATUSES),
                    )
                    .order_by(Receipt.created_at.desc(), Receipt.id.desc())
                ).scalars().first()

            if existing is not None:
                seen[identity] = existing
                accepted.append(
                    ReceiptUploadItem(
                        id=existing.id,
                        filename=safe_name,
                        status=existing.status,
                    )
                )
                continue

            receipt_id = uuid.uuid4()
            storage_path = save_receipt_file(client_id, receipt_id, filename, payload)
            written_paths.append(storage_path)

            receipt = _persist_receipt(
                db,
                receipt_id=receipt_id,
                client_id=client_id,
                filename=filename,
                mime_type=mime_type,
                file_size=len(payload),
                storage_path=storage_path,
            )
            seen[identity] = receipt
            queued.append(receipt_id)
            accepted.append(
                ReceiptUploadItem(
                    id=receipt_id,
                    filename=safe_name,
                    status=receipt.status,
                )
            )

        db.commit()
    except Exception:
        db.rollback()
        for path in written_paths:
            delete_receipt_file(path)
        raise

    # Only after the placeholders are durable: a task that reads a row the
    # transaction rolled back would silently do nothing.
    for receipt_id in queued:
        background_tasks.add_task(process_receipt_background, receipt_id)

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


def _reject_if_exported(receipt: Receipt) -> None:
    """Exported receipts are frozen: a marked month has left the ledger.

    ``STATUS_EXPORTED`` means the receipt was included in a batch the accountant
    marked as filed. Re-verifying or rejecting it would rewrite history for a
    period that has already been exported (and leave ``exported_at`` behind on a
    :class:`ReceiptStatus.STATUS_VERIFIED` row). The accountant must undo the
    export out-of-band rather than silently regress the row.
    """
    if receipt.status == ReceiptStatus.STATUS_EXPORTED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Receipt has already been exported and can no longer be edited",
        )


def _reject_if_processing(receipt: Receipt) -> None:
    """A receipt mid-flight cannot be verified or rejected by hand.

    The worker owns the row until it writes a terminal status. Accepting an
    edit now would be overwritten when the worker records its outcome (or, if
    the worker's no-op guard fires, would leave a ``STATUS_VERIFIED`` row with
    null fields and no audit trail). The accountant retries once processing
    settles.
    """
    if receipt.status in PROCESSING_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Receipt is still processing"
        )


def _receipt_or_404(db: Session, client_id: UUID, receipt_id: UUID) -> Receipt:
    """Fetch a receipt that belongs to ``client_id``, or 404.

    The tenant check is part of the lookup, so a receipt that exists under
    another workspace is indistinguishable from a missing one (docs/06_schema_api.md §6.3.5).
    Line items are eager-loaded: the detail and list envelopes both count and
    render them, and lazy loading would issue one query per receipt.
    """
    receipt = db.execute(
        select(Receipt)
        .where(Receipt.id == receipt_id, Receipt.client_id == client_id)
        .options(selectinload(Receipt.line_items))
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
            expense_category=item.expense_category or "OTHER",
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
        overall_confidence=(
            None
            if receipt.overall_confidence is None
            else float(receipt.overall_confidence)
        ),
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
        overall_confidence=(
            None
            if receipt.overall_confidence is None
            else float(receipt.overall_confidence)
        ),
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
    status: str = Query("ALL", pattern="^(ALL|NEEDS_REVIEW|VERIFIED|EXPORTED|REJECTED)$"),
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
) -> ReceiptListResponse:
    """List a client's receipts for the SCR-02 inbox (§6.3.2)."""
    get_active_owned_client(db, client_id, accountant_id)

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
        db.execute(
            base.options(selectinload(Receipt.line_items))
            .order_by(Receipt.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    # One grouped count feeds every tab; the active filter must not narrow it.
    by_status = dict(
        db.execute(
            select(Receipt.status, func.count())
            .where(Receipt.client_id == client_id)
            .group_by(Receipt.status)
        ).all()
    )
    # §6.2 requires a PROCESSING badge over the whole client. It is a count
    # bucket only: the ``status`` query enum stays fixed by §6.4.4, so this
    # entry is deliberately absent from INBOX_STATUS_FILTERS.
    status_buckets = {
        **INBOX_STATUS_FILTERS,
        "PROCESSING": tuple(PROCESSING_STATUSES),
    }
    status_counts = {
        name: sum(by_status.get(member, 0) for member in members)
        if members is not None
        else sum(by_status.values())
        for name, members in status_buckets.items()
    }

    return ReceiptListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[_build_list_item(client_id, receipt) for receipt in rows],
        status_counts=status_counts,
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
    get_active_owned_client(db, client_id, accountant_id)
    return _build_detail(client_id, _receipt_or_404(db, client_id, receipt_id))


@router.get("/clients/{client_id}/receipts/{receipt_id}/image")
def get_client_receipt_image(
    client_id: uuid.UUID,
    receipt_id: uuid.UUID,
    db: DbSession,
    accountant_id: AccountantId,
) -> Response:
    """Stream the stored receipt image for the review console viewport (§6.3.3).

    The blob is read through :func:`load_receipt_file`, which rejects a path that
    escapes the storage root, so a corrupted ``storage_path`` cannot become an
    arbitrary file read.
    """
    get_active_owned_client(db, client_id, accountant_id)
    receipt = _receipt_or_404(db, client_id, receipt_id)

    try:
        payload = load_receipt_file(receipt.storage_path)
    except (FileNotFoundError, ValueError):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Receipt image not found"
        ) from None
    return Response(content=payload, media_type=receipt.mime_type)


@router.get(
    "/clients/{client_id}/receipts/{receipt_id}/audit",
    response_model=ReceiptAuditResponse,
)
def get_client_receipt_audit(
    client_id: uuid.UUID,
    receipt_id: uuid.UUID,
    db: DbSession,
    accountant_id: AccountantId,
) -> ReceiptAuditResponse:
    """Manual-edit history for one receipt, newest first (§6.3.7)."""
    get_active_owned_client(db, client_id, accountant_id)
    receipt = _receipt_or_404(db, client_id, receipt_id)

    rows = (
        db.execute(
            select(ReceiptAuditLog)
            .where(ReceiptAuditLog.receipt_id == receipt.id)
            .order_by(
                ReceiptAuditLog.created_at.desc(), ReceiptAuditLog.id.desc()
            )
            .limit(200)
        )
        .scalars()
        .all()
    )
    return ReceiptAuditResponse(
        items=[ReceiptAuditRead.model_validate(row) for row in rows]
    )


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
    clears the stored value. Line items are replaced only when the payload
    carries the field, so a header-only save never deletes the persisted rows.
    The math discrepancy and any ``MATH_MISMATCH_DELTA_*`` flag are recomputed
    from the persisted rows, never from an unvalidated echo of the submission.
    """
    get_active_owned_client(db, client_id, accountant_id)
    receipt = _receipt_or_404(db, client_id, receipt_id)
    _reject_if_exported(receipt)
    _reject_if_processing(receipt)

    changed: list[tuple[str, str | None, str | None]] = []
    old_status = (
        receipt.status.value
        if hasattr(receipt.status, "value")
        else str(receipt.status)
    )

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

    if "line_items" in payload.model_fields_set and payload.line_items is not None:
        previous = [
            (row.description, str(row.line_total)) for row in receipt.line_items
        ]
        incoming = [
            (item.description, str(item.line_total)) for item in payload.line_items
        ]
        if previous != incoming:
            changed.append(
                ("line_items", f"{len(previous)} rows", f"{len(incoming)} rows")
            )
        receipt.line_items = [
            ReceiptLineItem(
                line_index=index,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=item.line_total,
                expense_category=classify_expense(item.description),
            )
            for index, item in enumerate(payload.line_items)
        ]
        db.flush()

    tax = receipt.tax_amount if receipt.tax_amount is not None else Decimal("0.00")
    line_sum = sum(
        (item.line_total for item in receipt.line_items), start=Decimal("0.00")
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
    # A manually verified receipt is no longer in an error state, so the detail
    # payload must stop advertising the stale pipeline failure text.
    receipt.processing_error = None
    receipt.verified_by = accountant_id
    receipt.verified_at = utcnow()

    if old_status != ReceiptStatus.STATUS_VERIFIED.value:
        changed.append(
            ("status", old_status, ReceiptStatus.STATUS_VERIFIED.value)
        )

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


@router.post(
    "/clients/{client_id}/receipts/{receipt_id}/reject",
    response_model=ReceiptUpdateResponse,
)
def reject_client_receipt(
    client_id: uuid.UUID,
    receipt_id: uuid.UUID,
    db: DbSession,
    accountant_id: AccountantId,
) -> ReceiptUpdateResponse:
    """Mark a receipt as rejected by the accountant."""
    get_active_owned_client(db, client_id, accountant_id)
    receipt = _receipt_or_404(db, client_id, receipt_id)
    _reject_if_exported(receipt)
    _reject_if_processing(receipt)

    # Rejecting an already-rejected receipt is idempotent: re-stamping
    # verified_by/verified_at would attribute the rejection to whoever pressed
    # the button last, and a REJECTED -> REJECTED audit row is noise in a trail
    # that is read as history. Return the row exactly as it stands.
    if receipt.status == ReceiptStatus.STATUS_REJECTED:
        return ReceiptUpdateResponse(
            id=receipt.id,
            status=receipt.status,
            updated_at=receipt.updated_at,
            verified_by=receipt.verified_by,
            math_discrepancy=_money_text(receipt.math_discrepancy) or "0.00",
        )

    old_status = (
        receipt.status.value
        if hasattr(receipt.status, "value")
        else str(receipt.status)
    )
    receipt.status = ReceiptStatus.STATUS_REJECTED
    receipt.verified_by = accountant_id
    receipt.verified_at = utcnow()

    db.add(
        ReceiptAuditLog(
            receipt_id=receipt.id,
            user_id=accountant_id,
            field_name="status",
            old_value=old_status,
            new_value=ReceiptStatus.STATUS_REJECTED.value,
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
    "MAX_BATCH_BYTES",
    "MAX_BATCH_FILES",
    "MAX_FILE_BYTES",
    "PROCESSING_STATUSES",
    "detect_mime_type",
    "process_receipt_background",
    "router",
    "run_pipeline",
]
