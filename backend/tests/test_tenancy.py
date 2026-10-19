"""Soft-delete tenancy: deleting a workspace revokes every client-scoped route.

The delete is a soft delete (the client row survives so receipt history does),
but §6.3.5 requires that data access is revoked: every receipt/export/dashboard
route resolves through :func:`app.core.tenancy.get_active_owned_client` and so
must 404 until the workspace is reactivated.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.auth import ACCOUNTANT_HEADER
from app.pipeline.ocr_engine import OCRToken
from app.schemas.receipt import (
    ExtractedField,
    LineItemSchema,
    ParsedReceiptSchema,
)

ACCOUNTANT_BODY = {
    "business_name": "Kim Guan Hardware",
    "industry_category": "HARDWARE",
}
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

            def _ocr(*_args, **_kwargs):
                raise error

            monkeypatch.setattr("app.api.receipts.process_receipt_image", _ocr)
            return
        monkeypatch.setattr(
            "app.api.receipts.process_receipt_image", lambda *_a, **_k: _tokens()
        )
        monkeypatch.setattr(
            "app.api.receipts.extract_receipt",
            lambda _tokens, **_: parsed or _parsed(),
        )

    return install


def _create_client(client: TestClient) -> str:
    response = client.post("/api/clients", json=ACCOUNTANT_BODY)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _upload(client: TestClient, client_id: str):
    return client.post(
        f"/api/v1/clients/{client_id}/receipts/upload",
        files=[("files", ("receipt.jpg", JPEG_BYTES, "image/jpeg"))],
    )


def _receipt_routes(client_id: str, receipt_id: str) -> dict[str, str]:
    """Every GET client-scoped route that must be revoked by a soft delete."""
    base = f"/api/v1/clients/{client_id}"
    return {
        "list": f"{base}/receipts",
        "detail": f"{base}/receipts/{receipt_id}",
        "image": f"{base}/receipts/{receipt_id}/image",
        "audit": f"{base}/receipts/{receipt_id}/audit",
        "accounting-csv": f"{base}/exports/accounting-csv",
        "myinvois-json": f"{base}/exports/myinvois-json",
        "dashboard": f"{base}/dashboard/summary",
    }


def test_delete_client_revokes_every_receipt_route(
    client: TestClient, stub_pipeline
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    uploaded = _upload(client, client_id)
    assert uploaded.status_code == 202, uploaded.text
    receipt_id = uploaded.json()["receipts"][0]["id"]

    routes = _receipt_routes(client_id, receipt_id)
    assert client.get(routes["list"]).status_code == 200

    assert client.delete(f"/api/clients/{client_id}").status_code == 204

    for name, url in routes.items():
        assert client.get(url).status_code == 404, name
    assert client.post(f"/api/v1/clients/{client_id}/exports/mark").status_code == 404
    assert _upload(client, client_id).status_code == 404


def test_reactivating_a_client_restores_receipt_access(
    client: TestClient, stub_pipeline
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload(client, client_id).json()["receipts"][0]["id"]
    list_url = _receipt_routes(client_id, receipt_id)["list"]

    assert client.delete(f"/api/clients/{client_id}").status_code == 204
    assert client.get(list_url).status_code == 404

    reactivated = client.put(f"/api/clients/{client_id}", json={"is_active": True})

    assert reactivated.status_code == 200
    assert reactivated.json()["is_active"] is True
    restored = client.get(list_url)
    assert restored.status_code == 200
    assert restored.json()["total"] == 1


def test_delete_is_idempotent(client: TestClient) -> None:
    client_id = _create_client(client)

    assert client.delete(f"/api/clients/{client_id}").status_code == 204
    assert client.delete(f"/api/clients/{client_id}").status_code == 204


def test_other_accountant_cannot_reach_a_deleted_workspace(
    client: TestClient,
    test_app: TestClient,
    other_accountant_id: uuid.UUID,
    stub_pipeline,
) -> None:
    stub_pipeline()
    client_id = _create_client(client)
    receipt_id = _upload(client, client_id).json()["receipts"][0]["id"]
    assert client.delete(f"/api/clients/{client_id}").status_code == 204

    # A second, valid accountant identity still gets a bare 404, never 403.
    foreign_headers = {ACCOUNTANT_HEADER: str(other_accountant_id)}
    for name, url in _receipt_routes(client_id, receipt_id).items():
        assert test_app.get(url, headers=foreign_headers).status_code == 404, name
