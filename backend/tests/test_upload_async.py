"""Asynchronous upload contract (docs/06_schema_api.md §6.3.1, REQ-101).

The upload request must return ``202`` with ``PROCESSING_OCR`` and leave the
expensive work to the background task. ``TestClient`` runs background tasks before
the response is handed back, so these tests separate the two guarantees: a
monkeypatched no-op worker proves the response is not blocked, while the
pipeline stubs prove the terminal state is persisted by the worker rather than
the request.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.receipts import (
    process_receipt_background as real_process_receipt_background,
)
from app.core.auth import ACCOUNTANT_HEADER
from app.core.database import SessionLocal
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_line_item import ReceiptLineItem
from app.pipeline.extractor import ExtractionError
from app.pipeline.ocr_engine import OCRToken
from app.pipeline.preprocessor import ImageDecodeError
from app.schemas.receipt import ExtractedField, LineItemSchema, ParsedReceiptSchema

ACCOUNTANT_BODY = {
    "business_name": "Kim Guan Hardware",
    "industry_category": "HARDWARE",
}
UPLOAD_URL = "/api/v1/clients/{client_id}/receipts/upload"
DETAIL_URL = "/api/v1/clients/{client_id}/receipts/{receipt_id}"
IMAGE_URL = "/api/v1/clients/{client_id}/receipts/{receipt_id}/image"
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def _tokens() -> list[OCRToken]:
    return [
        OCRToken(
            text=text,
            confidence=confidence,
            bbox=[0.05, 0.05 * i, 0.9, 0.05 * i + 0.03],
            line_num=i,
        )
        for i, (text, confidence) in enumerate(
            [
                ("KIM GUAN HARDWARE", 0.96),
                ("INV-99120", 0.94),
                ('PVC PIPE 2"', 0.91),
                ("14.50", 0.93),
                ("TOTAL 14.50", 0.95),
            ]
        )
    ]


def _parsed(grand_total: str = "14.50") -> ParsedReceiptSchema:
    return ParsedReceiptSchema(
        merchant_name="Kim Guan Hardware",
        invoice_date=date.today() - timedelta(days=3),
        invoice_number="INV-99120",
        subtotal=Decimal("14.50"),
        tax_amount=Decimal("0.00"),
        grand_total=Decimal(grand_total),
        line_items=[
            LineItemSchema(
                line_index=0,
                description='PVC Pipe 2"',
                quantity=Decimal("1.00"),
                unit_price=Decimal("14.50"),
                line_total=Decimal("14.50"),
                confidence=0.93,
                bbox=[0.05, 0.15, 0.9, 0.18],
            )
        ],
        fields=[
            ExtractedField(name="merchant_name", confidence=0.96),
            ExtractedField(name="grand_total", confidence=0.95),
        ],
    )


@pytest.fixture(autouse=True)
def _storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("KENYALANG_STORAGE_ROOT", str(tmp_path / "storage"))
    return tmp_path / "storage"


@pytest.fixture
def defer_worker(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    """Capture queued receipt ids instead of running the pipeline in-request."""
    queued: list[uuid.UUID] = []
    monkeypatch.setattr(
        "app.api.receipts.process_receipt_background",
        lambda receipt_id: queued.append(receipt_id),
    )
    return queued


@pytest.fixture
def stub_pipeline(monkeypatch: pytest.MonkeyPatch):
    """Install a deterministic OCR + extraction boundary on the receipts API."""

    def install(parsed: ParsedReceiptSchema | None = None) -> None:
        monkeypatch.setattr(
            "app.api.receipts.process_receipt_image", lambda *_a, **_k: _tokens()
        )
        monkeypatch.setattr(
            "app.api.receipts.extract_receipt", lambda _t, **_: parsed or _parsed()
        )

    return install


def _create_client(client: TestClient, name: str = "Kim Guan Hardware") -> str:
    response = client.post(
        "/api/clients", json={**ACCOUNTANT_BODY, "business_name": name}
    )
    assert response.status_code == 201
    return response.json()["id"]


def _upload(
    client: TestClient,
    client_id: str,
    files: list[tuple[str, bytes, str]] | None = None,
    headers: dict[str, str] | None = None,
):
    return client.post(
        UPLOAD_URL.format(client_id=client_id),
        files=files or [("files", ("receipt.jpg", JPEG_BYTES, "image/jpeg"))],
        headers=headers,
    )


def _stored(receipt_id: str) -> Receipt | None:
    """Reload one receipt inside a live session (callers may read relations)."""
    with SessionLocal() as db:
        return db.execute(
            select(Receipt).where(Receipt.id == uuid.UUID(receipt_id))
        ).scalar_one_or_none()


def _stored_field(receipt_id: str, attribute: str):
    with SessionLocal() as db:
        row = db.execute(
            select(Receipt).where(Receipt.id == uuid.UUID(receipt_id))
        ).scalar_one_or_none()
        return None if row is None else getattr(row, attribute)


def _line_item_count(receipt_id: str) -> int:
    with SessionLocal() as db:
        return len(
            db.execute(
                select(ReceiptLineItem).where(
                    ReceiptLineItem.receipt_id == uuid.UUID(receipt_id)
                )
            )
            .scalars()
            .all()
        )


def _terminal(client: TestClient, client_id: str, receipt_id: str):
    return client.get(DETAIL_URL.format(client_id=client_id, receipt_id=receipt_id))


# --------------------------------------------------------------------------- #
# The request itself returns before the pipeline runs
# --------------------------------------------------------------------------- #


def test_upload_returns_202_before_the_worker_runs(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A no-op worker must leave the row in ``PROCESSING_OCR``.

    If the route called the pipeline inline the status would already be terminal,
    so this is the regression test for a synchronous ingest path.
    """
    calls: list[uuid.UUID] = []
    monkeypatch.setattr(
        "app.api.receipts.process_receipt_background",
        lambda receipt_id: calls.append(receipt_id),
    )
    client_id = _create_client(client)

    response = _upload(client, client_id)

    assert response.status_code == 202
    body = response.json()
    assert body["total_received"] == 1
    assert body["batch_id"]
    item = body["receipts"][0]
    assert item["status"] == ReceiptStatus.PROCESSING_OCR.value
    assert calls == [uuid.UUID(item["id"])]

    stored = _stored(item["id"])
    assert stored is not None
    assert stored.status is ReceiptStatus.PROCESSING_OCR
    assert stored.processing_error is None
    assert _line_item_count(item["id"]) == 0


def test_duplicate_upload_returns_the_same_id_without_reprocessing(
    client: TestClient, stub_pipeline
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    first = _upload(client, client_id).json()["receipts"][0]

    second_response = _upload(client, client_id)
    assert second_response.status_code == 202
    second = second_response.json()["receipts"][0]

    assert second["id"] == first["id"]
    assert second["status"] == ReceiptStatus.STATUS_NEEDS_REVIEW.value

    with SessionLocal() as db:
        rows = db.execute(select(Receipt)).scalars().all()
    assert len(rows) == 1


def test_duplicate_inside_one_batch_returns_one_receipt(
    client: TestClient, stub_pipeline
) -> None:
    stub_pipeline()
    client_id = _create_client(client)

    response = _upload(
        client,
        client_id,
        files=[
            ("files", ("receipt.jpg", JPEG_BYTES, "image/jpeg")),
            ("files", ("receipt.jpg", JPEG_BYTES, "image/jpeg")),
        ],
    )

    assert response.status_code == 202
    ids = {item["id"] for item in response.json()["receipts"]}
    assert len(ids) == 1
    with SessionLocal() as db:
        assert len(db.execute(select(Receipt)).scalars().all()) == 1


# --------------------------------------------------------------------------- #
# The worker persists a terminal outcome
# --------------------------------------------------------------------------- #


def test_worker_persists_terminal_status_and_classified_lines(
    client: TestClient, stub_pipeline
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    item = _upload(client, client_id).json()["receipts"][0]
    assert item["status"] == ReceiptStatus.PROCESSING_OCR.value

    detail = _terminal(client, client_id, item["id"])
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == ReceiptStatus.STATUS_NEEDS_REVIEW.value
    assert body["merchant_name"] == "Kim Guan Hardware"
    assert body["grand_total"] == "14.50"
    assert body["line_items"][0]["expense_category"] == "HARDWARE"

    stored = _stored(item["id"])
    assert stored is not None
    assert stored.status is ReceiptStatus.STATUS_NEEDS_REVIEW
    assert stored.processing_error is None


def test_worker_does_not_overwrite_a_reviewed_receipt(
    client: TestClient, defer_worker: list[uuid.UUID]
) -> None:
    """A receipt the accountant already saved must survive a late worker run."""
    client_id = _create_client(client)
    item = _upload(client, client_id).json()["receipts"][0]

    with SessionLocal() as db:
        row = db.get(Receipt, uuid.UUID(item["id"]))
        assert row is not None
        row.status = ReceiptStatus.STATUS_VERIFIED
        row.merchant_name = "Human Corrected"
        db.commit()

    real_process_receipt_background(uuid.UUID(item["id"]))

    stored = _stored(item["id"])
    assert stored is not None
    assert stored.status is ReceiptStatus.STATUS_VERIFIED
    assert stored.merchant_name == "Human Corrected"


def test_missing_stored_blob_becomes_file_corrupt(
    client: TestClient, defer_worker: list[uuid.UUID]
) -> None:
    client_id = _create_client(client)
    item = _upload(client, client_id).json()["receipts"][0]

    storage_path = _stored_field(item["id"], "storage_path")
    (Path(__import__("os").environ["KENYALANG_STORAGE_ROOT"]) / storage_path).unlink()

    real_process_receipt_background(uuid.UUID(item["id"]))

    stored = _stored(item["id"])
    assert stored is not None
    assert stored.status is ReceiptStatus.ERR_FILE_CORRUPT
    assert stored.processing_error == "stored file could not be read"


def test_decode_failure_becomes_file_corrupt(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(*_a, **_k):
        raise ImageDecodeError("40 megapixel image exceeds the decode limit")

    monkeypatch.setattr("app.api.receipts.process_receipt_image", _raise)
    client_id = _create_client(client)

    item = _upload(client, client_id).json()["receipts"][0]

    stored = _stored(item["id"])
    assert stored is not None
    assert stored.status is ReceiptStatus.ERR_FILE_CORRUPT
    assert "40" in (stored.processing_error or "")


def test_provider_outage_becomes_err_extraction_without_fabricated_fields(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.api.receipts.process_receipt_image", lambda *_a, **_k: _tokens()
    )

    def _raise(_tokens, **_kwargs):
        raise ExtractionError("upstream 500: secret provider detail")

    monkeypatch.setattr("app.api.receipts.extract_receipt", _raise)
    client_id = _create_client(client)

    item = _upload(client, client_id).json()["receipts"][0]

    stored = _stored(item["id"])
    assert stored is not None
    assert stored.status is ReceiptStatus.ERR_EXTRACTION
    assert stored.processing_error == "extraction provider unavailable"
    assert "secret provider detail" not in (stored.processing_error or "")
    assert stored.merchant_name is None
    assert stored.grand_total is None
    assert _line_item_count(item["id"]) == 0


def test_unexpected_worker_exception_becomes_unreadable(
    client: TestClient, defer_worker: list[uuid.UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    client_id = _create_client(client)
    item = _upload(client, client_id).json()["receipts"][0]

    def _boom(*_a, **_k):
        raise RuntimeError("unexpected")

    monkeypatch.setattr("app.api.receipts._ocr_stage", _boom)

    real_process_receipt_background(uuid.UUID(item["id"]))

    stored = _stored(item["id"])
    assert stored is not None
    assert stored.status is ReceiptStatus.ERR_UNREADABLE
    assert stored.processing_error == "processing failed unexpectedly"


# --------------------------------------------------------------------------- #
# Blob fidelity and limits
# --------------------------------------------------------------------------- #


def test_image_route_streams_the_exact_uploaded_bytes(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    payload = JPEG_BYTES + b"unique-trailer-" + uuid.uuid4().bytes
    stub_pipeline()
    client_id = _create_client(client)

    item = _upload(
        client,
        client_id,
        files=[("files", ("receipt.jpg", payload, "image/jpeg"))],
    ).json()["receipts"][0]

    response = client.get(
        IMAGE_URL.format(client_id=client_id, receipt_id=item["id"])
    )

    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["content-type"] == "image/jpeg"


def test_batch_over_50_files_is_rejected_before_writing(
    client: TestClient, _storage_root: Path
) -> None:
    client_id = _create_client(client)
    files = [
        ("files", (f"receipt-{index}.jpg", JPEG_BYTES, "image/jpeg"))
        for index in range(51)
    ]

    response = _upload(client, client_id, files=files)

    assert response.status_code == 413
    assert "50" in response.json()["detail"]
    with SessionLocal() as db:
        assert db.execute(select(Receipt)).scalars().all() == []
    assert list(_storage_root.rglob("*")) == [] or not any(
        path.is_file() for path in _storage_root.rglob("*")
    )


def test_empty_file_is_422(client: TestClient) -> None:
    client_id = _create_client(client)

    response = _upload(
        client, client_id, files=[("files", ("empty.jpg", b"", "image/jpeg"))]
    )

    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()


def test_unsupported_magic_bytes_are_415_even_with_an_image_extension(
    client: TestClient,
) -> None:
    client_id = _create_client(client)

    response = _upload(
        client,
        client_id,
        files=[("files", ("receipt.jpg", b"GIF89a" + b"\x00" * 32, "image/jpeg"))],
    )

    assert response.status_code == 415
    assert "unsupported" in response.json()["detail"].lower()


def test_upload_to_a_foreign_workspace_is_404(
    client: TestClient,
    accountant_id: uuid.UUID,
    other_accountant_id: uuid.UUID,
) -> None:
    client_id = _create_client(client)

    response = _upload(
        client,
        client_id,
        headers={ACCOUNTANT_HEADER: str(other_accountant_id)},
    )

    assert response.status_code == 404


def test_pdf_upload_is_accepted(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The PDF is validated by magic bytes and reaches the worker as a PDF."""
    seen: list[str | None] = []

    def _ocr(_payload: bytes, mime_type: str | None = None):
        seen.append(mime_type)
        return _tokens()

    monkeypatch.setattr("app.api.receipts.process_receipt_image", _ocr)
    monkeypatch.setattr("app.api.receipts.extract_receipt", lambda _t, **_: _parsed())
    client_id = _create_client(client)
    pdf_bytes = b"%PDF-1.7\n" + b"0" * 64

    response = _upload(
        client,
        client_id,
        files=[("files", ("receipt.pdf", pdf_bytes, "application/pdf"))],
    )

    assert response.status_code == 202
    item = response.json()["receipts"][0]
    assert item["status"] == ReceiptStatus.PROCESSING_OCR.value
    assert seen == ["application/pdf"]


def test_oversized_file_is_413_and_leaves_no_row(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client_id = _create_client(client)
    monkeypatch.setattr("app.api.receipts.MAX_FILE_BYTES", 1024)

    response = _upload(
        client,
        client_id,
        files=[("files", ("big.jpg", JPEG_BYTES + b"\x00" * 2048, "image/jpeg"))],
    )

    assert response.status_code == 413
    with SessionLocal() as db:
        assert db.execute(select(Receipt)).scalars().all() == []


def test_background_tasks_are_queued_only_after_the_commit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rolled-back batch must not enqueue work for rows that do not exist."""
    queued: list[uuid.UUID] = []
    monkeypatch.setattr(
        "app.api.receipts.process_receipt_background",
        lambda receipt_id: queued.append(receipt_id),
    )
    client_id = _create_client(client)

    def _fail(*_a, **_k):
        raise RuntimeError("insert failed")

    monkeypatch.setattr("app.api.receipts._persist_receipt", _fail)

    with pytest.raises(RuntimeError):
        _upload(client, client_id)

    assert queued == []


def test_line_items_are_classified_when_the_worker_persists(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    parsed = _parsed()
    parsed.line_items = [
        LineItemSchema(
            line_index=index,
            description=description,
            quantity=Decimal("1.00"),
            unit_price=Decimal("5.00"),
            line_total=Decimal("5.00"),
            confidence=0.9,
        )
        for index, description in enumerate(
            ["Nasi lemak", 'PVC pipe 2"', "Mystery item"]
        )
    ]
    parsed.subtotal = Decimal("15.00")
    parsed.grand_total = Decimal("15.00")
    monkeypatch.setattr(
        "app.api.receipts.process_receipt_image", lambda *_a, **_k: _tokens()
    )
    monkeypatch.setattr("app.api.receipts.extract_receipt", lambda _t, **_: parsed)
    client_id = _create_client(client)

    item = _upload(client, client_id).json()["receipts"][0]

    with SessionLocal() as db:
        rows = (
            db.execute(
                select(ReceiptLineItem)
                .where(ReceiptLineItem.receipt_id == uuid.UUID(item["id"]))
                .order_by(ReceiptLineItem.line_index)
            )
            .scalars()
            .all()
        )
    assert [row.expense_category for row in rows] == ["F&B", "HARDWARE", "OTHER"]
