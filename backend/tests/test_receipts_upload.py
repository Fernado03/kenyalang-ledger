"""Receipt batch upload endpoint (docs/06_schema_api.md §6.3.1, REQ-101).

OCR and the LLM are stubbed at the pipeline boundary: the point of these tests is
the endpoint's own contract -- guards, persistence, tenant isolation, status
mapping -- not EasyOCR or a paid model call.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import receipts as receipts_api
from app.core import storage
from app.core.database import SessionLocal
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_line_item import ReceiptLineItem
from app.pipeline.extractor import ExtractionError, ExtractionTimeout
from app.pipeline.ocr_engine import OCRToken
from app.pipeline.preprocessor import ImageDecodeError
from app.schemas.receipt import ExtractedField, LineItemSchema, ParsedReceiptSchema

ACCOUNTANT_BODY = {
    "business_name": "Kim Guan Hardware",
    "industry_category": "HARDWARE",
}
UPLOAD_URL = "/api/v1/clients/{client_id}/receipts/upload"
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


def _parsed(
    *, grand_total: str = "14.50", line_total: str = "14.50"
) -> ParsedReceiptSchema:
    return ParsedReceiptSchema(
        merchant_name="Kim Guan Hardware",
        invoice_date=date.today() - timedelta(days=3),
        invoice_number="INV-99120",
        subtotal=Decimal(line_total),
        tax_amount=Decimal("0.00"),
        grand_total=Decimal(grand_total),
        line_items=[
            LineItemSchema(
                line_index=0,
                description='PVC Pipe 2"',
                quantity=Decimal("1.00"),
                unit_price=Decimal(line_total),
                line_total=Decimal(line_total),
                confidence=0.93,
                bbox=[0.05, 0.15, 0.9, 0.18],
            )
        ],
        fields=[
            ExtractedField(name="merchant_name", confidence=0.96),
            ExtractedField(name="invoice_date", confidence=0.94),
            ExtractedField(name="grand_total", confidence=0.95),
            ExtractedField(name="subtotal", confidence=0.93),
        ],
    )


@pytest.fixture(autouse=True)
def _storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep uploaded blobs out of the repository working tree."""
    monkeypatch.setenv("KENYALANG_STORAGE_ROOT", str(tmp_path / "storage"))
    return tmp_path / "storage"


@pytest.fixture
def stub_pipeline(monkeypatch: pytest.MonkeyPatch):
    """Replace the OCR + LLM boundary with a deterministic receipt."""

    def install(
        parsed: ParsedReceiptSchema | None = None, error: Exception | None = None
    ):
        if error is not None:

            def _ocr(_payload: bytes):
                raise error

            monkeypatch.setattr("app.api.receipts.process_receipt_image", _ocr)
            return
        monkeypatch.setattr(
            "app.api.receipts.process_receipt_image", lambda _payload: _tokens()
        )
        monkeypatch.setattr(
            "app.api.receipts.extract_receipt",
            lambda _tokens, **_: parsed or _parsed(),
        )

    return install


def _create_client(client: TestClient) -> str:
    response = client.post("/api/clients", json=ACCOUNTANT_BODY)
    assert response.status_code == 201
    return response.json()["id"]


def _upload(
    client: TestClient, client_id: str, files: list[tuple[str, bytes]] | None = None
):
    return client.post(
        UPLOAD_URL.format(client_id=client_id),
        files=files or [("files", ("receipt.jpg", JPEG_BYTES, "image/jpeg"))],
    )


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


def test_upload_persists_receipt_and_line_items(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)

    response = _upload(client, client_id)

    assert response.status_code == 202
    body = response.json()
    assert body["total_received"] == 1
    uuid.UUID(body["batch_id"])
    item = body["receipts"][0]
    assert item["filename"] == "receipt.jpg"
    assert item["status"] == ReceiptStatus.STATUS_AUTO_VERIFIED.value

    with SessionLocal() as db:
        receipt = db.get(Receipt, uuid.UUID(item["id"]))
        assert receipt is not None
        assert receipt.merchant_name == "Kim Guan Hardware"
        assert receipt.grand_total == Decimal("14.50")
        assert receipt.status is ReceiptStatus.STATUS_AUTO_VERIFIED
        assert receipt.validation_flags == []
        assert float(receipt.overall_confidence) == pytest.approx(0.93, abs=0.01)
        assert len(receipt.ocr_raw_tokens) == 5

        line = db.execute(
            select(ReceiptLineItem).where(ReceiptLineItem.receipt_id == receipt.id)
        ).scalar_one()
        assert line.description == 'PVC Pipe 2"'
        assert line.line_total == Decimal("14.50")
        assert line.bbox == [0.05, 0.15, 0.9, 0.18]

    stored = _storage_root / "tenants" / client_id / f"{item['id']}.jpg"
    assert stored.read_bytes() == JPEG_BYTES


def test_upload_flags_math_mismatch_for_review(
    client: TestClient, stub_pipeline
) -> None:
    stub_pipeline(_parsed(grand_total="70.00", line_total="50.00"))
    client_id = _create_client(client)

    response = _upload(client, client_id)

    assert response.status_code == 202
    assert (
        response.json()["receipts"][0]["status"]
        == ReceiptStatus.STATUS_NEEDS_REVIEW.value
    )

    with SessionLocal() as db:
        receipt = db.execute(select(Receipt)).scalar_one()
        assert "MATH_MISMATCH_DELTA_20.00" in receipt.validation_flags
        assert receipt.math_discrepancy == Decimal("20.00")


def test_upload_accepts_multiple_files_in_one_batch(
    client: TestClient, stub_pipeline
) -> None:
    stub_pipeline()
    client_id = _create_client(client)

    response = _upload(
        client,
        client_id,
        files=[
            ("files", ("a.jpg", JPEG_BYTES, "image/jpeg")),
            ("files", ("b.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, "image/png")),
        ],
    )

    assert response.status_code == 202
    assert response.json()["total_received"] == 2
    with SessionLocal() as db:
        assert len(db.execute(select(Receipt)).scalars().all()) == 2


# --------------------------------------------------------------------------- #
# Failure mapping: the receipt is persisted, never silently dropped
# --------------------------------------------------------------------------- #


def test_corrupt_image_is_persisted_as_error(client: TestClient, stub_pipeline) -> None:
    stub_pipeline(error=ImageDecodeError("not an image"))
    client_id = _create_client(client)

    response = _upload(client, client_id)

    assert response.status_code == 202
    assert (
        response.json()["receipts"][0]["status"] == ReceiptStatus.ERR_FILE_CORRUPT.value
    )
    with SessionLocal() as db:
        receipt = db.execute(select(Receipt)).scalar_one()
        assert receipt.processing_error
        assert receipt.grand_total is None


def test_too_few_ocr_tokens_is_persisted_as_unreadable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.api.receipts.process_receipt_image", lambda _payload: _tokens()[:2]
    )
    client_id = _create_client(client)

    response = _upload(client, client_id)

    assert response.status_code == 202
    assert (
        response.json()["receipts"][0]["status"] == ReceiptStatus.ERR_UNREADABLE.value
    )


def test_infrastructure_failure_is_503_and_leaves_no_rows(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, _storage_root: Path
) -> None:
    """A provider/credential failure is not a receipt defect: no row, no blob, 503."""
    monkeypatch.setattr(
        "app.api.receipts.process_receipt_image", lambda _payload: _tokens()
    )

    def _boom(_tokens, **_):
        raise ExtractionError("model unavailable")

    monkeypatch.setattr("app.api.receipts.extract_receipt", _boom)
    client_id = _create_client(client)

    response = _upload(client, client_id)

    assert response.status_code == 503
    with SessionLocal() as db:
        assert db.execute(select(Receipt)).scalars().all() == []
    assert not list(_storage_root.rglob("*.jpg"))


def test_genuine_timeout_is_persisted_as_timeout(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.api.receipts.process_receipt_image", lambda _payload: _tokens()
    )

    def _slow(_tokens, **_):
        raise ExtractionTimeout("provider timed out")

    monkeypatch.setattr("app.api.receipts.extract_receipt", _slow)
    client_id = _create_client(client)

    response = _upload(client, client_id)

    assert response.status_code == 202
    assert response.json()["receipts"][0]["status"] == ReceiptStatus.ERR_TIMEOUT.value


# --------------------------------------------------------------------------- #
# Ingestion guards (§5.6.2) and tenancy (§6.3.5)
# --------------------------------------------------------------------------- #


def test_rejects_unsupported_file_type_by_magic_bytes(client: TestClient) -> None:
    client_id = _create_client(client)

    response = _upload(
        client,
        client_id,
        files=[("files", ("payload.jpg", b"MZ\x90\x00 not an image", "image/jpeg"))],
    )

    assert response.status_code == 415


def test_rejects_file_over_15mb(client: TestClient) -> None:
    client_id = _create_client(client)
    oversized = b"\xff\xd8\xff\xe0" + b"\x00" * (15 * 1024 * 1024)

    response = _upload(
        client, client_id, files=[("files", ("big.jpg", oversized, "image/jpeg"))]
    )

    assert response.status_code == 413


def test_rejects_batch_over_50_files(client: TestClient) -> None:
    client_id = _create_client(client)

    response = _upload(
        client,
        client_id,
        files=[("files", (f"{i}.jpg", JPEG_BYTES, "image/jpeg")) for i in range(51)],
    )

    assert response.status_code == 413


def test_upload_to_foreign_workspace_is_not_found(
    client: TestClient,
    test_app: TestClient,
    other_accountant_id: uuid.UUID,
    stub_pipeline,
) -> None:
    stub_pipeline()
    foreign_id = test_app.post(
        "/api/clients",
        json={**ACCOUNTANT_BODY, "business_name": "Not Mine"},
        headers={"X-Accountant-Id": str(other_accountant_id)},
    ).json()["id"]

    response = _upload(client, foreign_id)

    assert response.status_code == 404
    with SessionLocal() as db:
        assert db.execute(select(Receipt)).scalars().all() == []


def test_upload_requires_authentication(test_app: TestClient) -> None:
    response = test_app.post(
        UPLOAD_URL.format(client_id=uuid.uuid4()),
        files=[("files", ("receipt.jpg", JPEG_BYTES, "image/jpeg"))],
    )

    assert response.status_code == 401


@pytest.mark.parametrize("invalid,status", [(b"", 422), (b"not an image", 415)])
def test_invalid_later_file_leaves_no_partial_batch(
    client: TestClient, stub_pipeline, _storage_root: Path, invalid: bytes, status: int
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    response = _upload(
        client,
        client_id,
        files=[
            ("files", ("good.jpg", JPEG_BYTES, "image/jpeg")),
            ("files", ("bad.jpg", invalid, "image/jpeg")),
        ],
    )

    assert response.status_code == status
    with SessionLocal() as db:
        assert db.execute(select(Receipt)).scalars().all() == []
        assert db.execute(select(ReceiptLineItem)).scalars().all() == []
    assert not any(path.is_file() for path in _storage_root.rglob("*"))


@pytest.mark.parametrize("stage", ["storage", "pipeline", "database"])
def test_later_infrastructure_failure_rolls_back_only_current_batch(
    client: TestClient,
    stub_pipeline,
    monkeypatch: pytest.MonkeyPatch,
    _storage_root: Path,
    stage: str,
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    existing = _upload(client, client_id).json()["receipts"][0]["id"]
    target = {
        "storage": "save_receipt_file",
        "pipeline": "extract_receipt",
        "database": "_persist_receipt",
    }[stage]
    original = getattr(receipts_api, target)
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            if stage == "pipeline":
                raise ExtractionError("provider unavailable")
            raise RuntimeError("infrastructure unavailable")
        result = original(*args, **kwargs)
        if stage == "database":
            args[0].flush()
        return result

    monkeypatch.setattr(receipts_api, target, fail_second)
    files = [("files", (name, JPEG_BYTES, "image/jpeg")) for name in ("a.jpg", "b.jpg")]
    if stage == "pipeline":
        assert _upload(client, client_id, files=files).status_code == 503
    else:
        with pytest.raises(RuntimeError):
            _upload(client, client_id, files=files)

    with SessionLocal() as db:
        assert [str(row.id) for row in db.execute(select(Receipt)).scalars()] == [
            existing
        ]
        assert len(db.execute(select(ReceiptLineItem)).scalars().all()) == 1
    blobs = [path for path in _storage_root.rglob("*") if path.is_file()]
    assert blobs == [_storage_root / "tenants" / client_id / f"{existing}.jpg"]
    assert blobs[0].read_bytes() == JPEG_BYTES


def test_upload_reads_only_size_limit_plus_one(
    client: TestClient,
    accountant_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    _storage_root: Path,
) -> None:
    client_id = uuid.UUID(_create_client(client))
    monkeypatch.setattr(receipts_api, "MAX_FILE_BYTES", 8)
    reads = []

    class BoundedStream:
        def read(self, size=-1):
            reads.append(size)
            assert size == 9
            return JPEG_BYTES[:size]

    upload = UploadFile(filename="big.jpg", file=BoundedStream())
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as error:
            receipts_api.upload_receipts(client_id, db, accountant_id, [upload])
        assert error.value.status_code == 413
        assert db.execute(select(Receipt)).scalars().all() == []
    assert reads == [9]
    assert not any(path.is_file() for path in _storage_root.rglob("*"))


@pytest.mark.parametrize("operation", ["write_bytes", "replace"])
def test_failed_blob_write_removes_temporary_file(
    monkeypatch: pytest.MonkeyPatch, _storage_root: Path, operation: str
) -> None:
    original_write = Path.write_bytes

    def fail(path, *args):
        if operation == "write_bytes":
            original_write(path, b"partial")
        raise OSError("storage unavailable")

    monkeypatch.setattr(Path, operation, fail)
    with pytest.raises(OSError):
        storage.save_receipt_file(uuid.uuid4(), uuid.uuid4(), "receipt.jpg", JPEG_BYTES)
    assert not any(path.is_file() for path in _storage_root.rglob("*"))


@pytest.mark.parametrize(
    "filename,expected,extension",
    [
        ("../folder/receipt.JPG", "receipt.JPG", ".jpg"),
        ("..\\folder\\receipt.JPG", "receipt.JPG", ".jpg"),
        ("../folder\\receipt\x00\n.JPG", "receipt.JPG", ".jpg"),
        ("x" * 260 + ".jpg", "x" * 255, ".jpg"),
        ("\x00\n", "receipt", ".bin"),
    ],
)
def test_upload_filename_metadata_cannot_supply_blob_path(
    filename: str, expected: str, extension: str
) -> None:
    client_id, receipt_id = uuid.uuid4(), uuid.uuid4()
    assert storage.safe_filename(filename) == expected
    assert storage.safe_filename(filename, max_length=300) == expected
    assert storage.receipt_storage_path(client_id, receipt_id, filename) == (
        f"tenants/{client_id}/{receipt_id}{extension}"
    )
