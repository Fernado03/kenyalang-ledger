"""Update integrity: line-item persistence, math recomputation, flag handling.

The review console's ``PUT`` (docs/06_schema_api.md §6.3.4) must never trust the
submitted echo of the receipt: the discrepancy and the ``MATH_MISMATCH_DELTA_*``
flag are recomputed from the persisted rows. These tests pin that contract down,
including the subtle cases — a header-only save must not delete line items, an
explicit ``null`` must not either, and a non-math validation flag must survive a
successful reconciliation.

OCR and the LLM are stubbed at the pipeline boundary (same as
``tests/test_receipts_upload.py``).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.auth import ACCOUNTANT_HEADER
from app.core.database import SessionLocal
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_line_item import ReceiptLineItem
from app.pipeline.ocr_engine import OCRToken
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


def _parsed() -> ParsedReceiptSchema:
    return ParsedReceiptSchema(
        merchant_name="Kim Guan Hardware",
        invoice_date=date.today() - timedelta(days=3),
        invoice_number="INV-99120",
        subtotal=Decimal("14.50"),
        tax_amount=Decimal("0.00"),
        grand_total=Decimal("14.50"),
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
            ExtractedField(name="invoice_date", confidence=0.94),
            ExtractedField(name="grand_total", confidence=0.95),
            ExtractedField(name="subtotal", confidence=0.93),
        ],
    )


def _line(description: str, amount: str) -> dict[str, str]:
    return {
        "description": description,
        "quantity": "1.00",
        "unit_price": amount,
        "line_total": amount,
    }


@pytest.fixture(autouse=True)
def _storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep uploaded blobs out of the repository working tree."""
    monkeypatch.setenv("KENYALANG_STORAGE_ROOT", str(tmp_path / "storage"))
    return tmp_path / "storage"


@pytest.fixture
def stub_pipeline(monkeypatch: pytest.MonkeyPatch):
    """Replace the OCR + LLM boundary with a deterministic receipt."""

    def install():
        monkeypatch.setattr(
            "app.api.receipts.process_receipt_image", lambda *_a, **_k: _tokens()
        )
        monkeypatch.setattr(
            "app.api.receipts.extract_receipt", lambda _t, **_: _parsed()
        )

    return install


def _create_client(client: TestClient, headers: dict[str, str] | None = None) -> str:
    response = client.post("/api/clients", json=ACCOUNTANT_BODY, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def _upload(
    client: TestClient, client_id: str, headers: dict[str, str] | None = None
) -> str:
    response = client.post(
        UPLOAD_URL.format(client_id=client_id),
        files=[("files", ("receipt.jpg", JPEG_BYTES, "image/jpeg"))],
        headers=headers,
    )
    assert response.status_code == 202
    return response.json()["receipts"][0]["id"]


def _detail_url(client_id: str, receipt_id: str) -> str:
    return f"/api/v1/clients/{client_id}/receipts/{receipt_id}"


def _line_item_count(receipt_id: str) -> int:
    with SessionLocal() as db:
        return db.execute(
            select(func.count())
            .select_from(ReceiptLineItem)
            .where(ReceiptLineItem.receipt_id == uuid.UUID(receipt_id))
        ).scalar_one()


# --------------------------------------------------------------------------- #
# Header-only saves cannot destroy or bypass line items
# --------------------------------------------------------------------------- #


def test_header_only_update_recomputes_discrepancy_from_persisted_lines(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload(client, client_id)

    # The persisted line is 14.50 and tax is 0.00, so a 70.00 header is off by
    # 55.50 -- the route must use the stored rows, not trust the submission.
    response = client.put(
        _detail_url(client_id, receipt_id), json={"grand_total": "70.00"}
    )

    assert response.status_code == 200
    assert response.json()["math_discrepancy"] == "55.50"

    detail = client.get(_detail_url(client_id, receipt_id)).json()
    assert detail["grand_total"] == "70.00"
    assert "MATH_MISMATCH_DELTA_55.50" in detail["validation_flags"]
    assert detail["math_discrepancy"] == "55.50"
    # A header-only save leaves the line-item rows intact.
    assert len(detail["line_items"]) == 1
    assert detail["line_items"][0]["line_total"] == "14.50"
    assert _line_item_count(receipt_id) == 1


def test_explicit_null_line_items_leaves_persisted_rows_alone(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload(client, client_id)

    response = client.put(
        _detail_url(client_id, receipt_id), json={"line_items": None}
    )

    assert response.status_code == 200
    # `null` is not `[]`: the key is present but carries no replacement rows.
    assert _line_item_count(receipt_id) == 1
    detail = client.get(_detail_url(client_id, receipt_id)).json()
    assert len(detail["line_items"]) == 1
    assert detail["line_items"][0]["description"] == 'PVC Pipe 2"'
    assert detail["line_items"][0]["line_total"] == "14.50"


# --------------------------------------------------------------------------- #
# Reconciling line items clear the math flag and classify the rows
# --------------------------------------------------------------------------- #


def test_reconciling_line_items_clear_math_flag_and_classify_categories(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload(client, client_id)

    response = client.put(
        _detail_url(client_id, receipt_id),
        json={
            "grand_total": "14.50",
            "line_items": [
                _line('PVC Pipe 2"', "10.00"),
                _line("Nasi lemak", "3.00"),
                _line("Mystery item", "1.50"),
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["math_discrepancy"] == "0.00"

    detail = client.get(_detail_url(client_id, receipt_id)).json()
    assert detail["math_discrepancy"] == "0.00"
    assert not any(
        flag.startswith("MATH_MISMATCH") for flag in detail["validation_flags"]
    )
    assert [line["expense_category"] for line in detail["line_items"]] == [
        "HARDWARE",
        "F&B",
        "OTHER",
    ]
    assert [line["description"] for line in detail["line_items"]] == [
        'PVC Pipe 2"',
        "Nasi lemak",
        "Mystery item",
    ]

    with SessionLocal() as db:
        rows = (
            db.execute(
                select(ReceiptLineItem)
                .where(ReceiptLineItem.receipt_id == uuid.UUID(receipt_id))
                .order_by(ReceiptLineItem.line_index)
            )
            .scalars()
            .all()
        )
    assert [row.expense_category for row in rows] == ["HARDWARE", "F&B", "OTHER"]
    assert [row.line_index for row in rows] == [0, 1, 2]


def test_explicit_empty_line_items_clears_the_rows(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload(client, client_id)

    response = client.put(_detail_url(client_id, receipt_id), json={"line_items": []})

    assert response.status_code == 200
    assert _line_item_count(receipt_id) == 0
    detail = client.get(_detail_url(client_id, receipt_id)).json()
    assert detail["line_items"] == []


def test_update_rederives_flags_instead_of_patching_only_the_math_flag(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    """M5: stale per-row flags must not survive a line-item rewrite.

    Rewriting the rows used to leave ``LOW_CONFIDENCE_line_items[i]`` pointing
    at rows that no longer existed, because only ``MATH_*`` was refreshed. The
    audit is deterministic, so the update re-derives the whole flag list from
    the persisted state.
    """
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload(client, client_id)

    with SessionLocal() as db:
        receipt = db.get(Receipt, uuid.UUID(receipt_id))
        assert receipt is not None
        receipt.validation_flags = [
            "LOW_CONFIDENCE_line_items[3]",
            "LOW_CONFIDENCE_line_items[7]",
            "MATH_MISMATCH_DELTA_9.99",
        ]
        db.commit()

    response = client.put(
        _detail_url(client_id, receipt_id),
        json={
            "grand_total": "14.50",
            "line_items": [_line('PVC Pipe 2"', "14.50")],
        },
    )

    assert response.status_code == 200
    assert response.json()["math_discrepancy"] == "0.00"

    detail = client.get(_detail_url(client_id, receipt_id)).json()
    flags = detail["validation_flags"]
    # The two phantom rows are gone: the receipt now has one line item.
    assert not any(flag.startswith("LOW_CONFIDENCE_line_items[") for flag in flags)
    # And the stale mismatch flag is gone because the maths now reconciles.
    assert not any(flag.startswith("MATH_MISMATCH_DELTA_") for flag in flags)


def test_update_keeps_a_genuine_low_confidence_flag(
    client: TestClient, stub_pipeline, _storage_root: Path
) -> None:
    """Re-derivation must preserve warnings that still describe the data."""
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload(client, client_id)

    with SessionLocal() as db:
        receipt = db.get(Receipt, uuid.UUID(receipt_id))
        assert receipt is not None
        # A header field whose OCR evidence is genuinely weak.
        receipt.field_provenance = [
            {"name": "merchant_name", "confidence": 0.42, "bbox": None},
            {"name": "invoice_date", "confidence": 0.99, "bbox": None},
            {"name": "grand_total", "confidence": 0.99, "bbox": None},
        ]
        db.commit()

    response = client.put(
        _detail_url(client_id, receipt_id),
        json={
            "grand_total": "14.50",
            "line_items": [_line('PVC Pipe 2"', "14.50")],
        },
    )
    assert response.status_code == 200

    detail = client.get(_detail_url(client_id, receipt_id)).json()
    assert "LOW_CONFIDENCE_merchant_name" in detail["validation_flags"]


# --------------------------------------------------------------------------- #
# Tenancy isolation (§6.3.5)
# --------------------------------------------------------------------------- #


def test_cross_tenant_update_is_not_found_and_leaves_receipt_unchanged(
    client: TestClient,
    stub_pipeline,
    _storage_root: Path,
    other_accountant_id: uuid.UUID,
) -> None:
    stub_pipeline()
    other_headers = {ACCOUNTANT_HEADER: str(other_accountant_id)}
    foreign_client_id = _create_client(client, headers=other_headers)
    foreign_receipt_id = _upload(client, foreign_client_id, headers=other_headers)

    response = client.put(
        _detail_url(foreign_client_id, foreign_receipt_id),
        json={"merchant_name": "Hijacked Supplier", "grand_total": "1.00"},
    )

    assert response.status_code == 404

    with SessionLocal() as db:
        receipt = db.get(Receipt, uuid.UUID(foreign_receipt_id))
        assert receipt is not None
        assert receipt.merchant_name == "Kim Guan Hardware"
        assert receipt.grand_total == Decimal("14.50")
        assert receipt.status is ReceiptStatus.STATUS_AUTO_VERIFIED
        assert receipt.verified_by is None
        assert receipt.verified_at is None
        # No audit trail was written by the rejected attempt.
        assert receipt.audit_logs == []
