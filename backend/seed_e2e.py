"""Deterministic fixture database + blob store for the Playwright E2E suite.

Run standalone (``python seed_e2e.py``) or as the first half of the API
``webServer`` command. It deletes the E2E database and blob root before seeding,
so it never touches ``kenyalang.db``.

Environment must be set before ``app`` is imported: the SQLAlchemy engine and
the storage root are both resolved at import time.
"""

from __future__ import annotations

import os
import shutil
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

HERE = Path(__file__).resolve().parent
DB_FILE = HERE / "kenyalang-e2e.db"
STORAGE_DIR = HERE / "storage-e2e"

os.environ.setdefault("DATABASE_URL", f"sqlite:///{DB_FILE.as_posix()}")
os.environ.setdefault("KENYALANG_STORAGE_ROOT", str(STORAGE_DIR))
os.environ.setdefault("KENYALANG_ENV", "local")

from PIL import Image, ImageDraw

from app.core.database import SessionLocal, utcnow
from app.models import (
    Client,
    Receipt,
    ReceiptAuditLog,
    ReceiptLineItem,
    ReceiptStatus,
    init_db,
)
from app.services.classifier import classify_expense

ACCOUNTANT_ID = UUID("a0000000-0000-4000-8000-000000000001")
OTHER_ACCOUNTANT_ID = UUID("b0b0b0b0-2222-4333-8444-555555555555")
CLIENT_MAIN_ID = UUID("c1000000-0000-4000-8000-000000000001")
CLIENT_EMPTY_ID = UUID("c1000000-0000-4000-8000-000000000002")


def r(receipt_id: str) -> UUID:
    return UUID(f"e2e00000-0000-4000-8000-0000000000{receipt_id}")


R_MATH = r("01")
R_CLEAN = r("02")
R_VERIFIED = r("03")
R_EXPORTED = r("04")
R_REJECTED = r("05")
R_UNREADABLE = r("06")
R_PROCESSING = r("07")
R_SAVE = r("08")
R_REJECT = r("09")
R_MARK = r("10")
R_EXPORTED_FROZEN = r("11")

TODAY = date.today()
CURRENT_MONTH_DAY = TODAY.replace(day=min(TODAY.day, 28))
FIXED_MONTH = "2026-03"
FIXED_MONTH_DAY = date(2026, 3, 12)


def image_bytes(path: Path, label: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (700, 900), (248, 246, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle((40, 40, 660, 860), outline=(40, 40, 40), width=3)
    draw.text((70, 90), label, fill=(20, 20, 20))
    draw.text((70, 140), "KEDAI E2E HARDWARE & SUPPLY", fill=(20, 20, 20))
    for i in range(9):
        draw.line((70, 220 + i * 55, 630, 220 + i * 55), fill=(190, 190, 190), width=1)
    img.save(path, "JPEG", quality=80)
    return path.stat().st_size


def receipt(
    *,
    rid: UUID,
    client_id: UUID,
    filename: str,
    status: ReceiptStatus,
    merchant: str | None,
    invoice_date: date | None,
    invoice_number: str | None,
    subtotal: str | None,
    tax: str | None,
    total: str | None,
    created_at: datetime,
    lines: list[tuple[str, str, str, str]],
    flags: list[str] | None = None,
    confidence: str = "0.93",
    discrepancy: str = "0.00",
    processing_error: str | None = None,
    exported_at: datetime | None = None,
) -> Receipt:
    rel = f"tenants/{client_id}/{rid}.jpg"
    size = image_bytes(STORAGE_DIR / rel, merchant or filename)
    row = Receipt(
        id=rid,
        client_id=client_id,
        original_filename=filename,
        storage_path=rel,
        mime_type="image/jpeg",
        file_size_bytes=size,
        status=status,
        processing_error=processing_error,
        merchant_name=merchant,
        invoice_date=invoice_date,
        invoice_number=invoice_number,
        subtotal=None if subtotal is None else Decimal(subtotal),
        tax_amount=None if tax is None else Decimal(tax),
        grand_total=None if total is None else Decimal(total),
        overall_confidence=Decimal(confidence),
        math_discrepancy=Decimal(discrepancy),
        validation_flags=flags or [],
        field_provenance=[
            {"name": "merchant_name", "confidence": 0.96, "bbox": [0.10, 0.14, 0.88, 0.19]},
            {"name": "invoice_number", "confidence": 0.91, "bbox": [0.10, 0.22, 0.60, 0.27]},
            {"name": "grand_total", "confidence": 0.88, "bbox": [0.55, 0.78, 0.90, 0.84]},
        ],
        ocr_raw_tokens=[
            {"text": merchant or "UNREADABLE", "confidence": 0.97, "bbox": [0.1, 0.14, 0.88, 0.19], "line_num": 0},
            {"text": invoice_number or "-", "confidence": 0.9, "bbox": [0.1, 0.22, 0.6, 0.27], "line_num": 1},
            {"text": f"TOTAL {total or '0.00'}", "confidence": 0.86, "bbox": [0.55, 0.78, 0.9, 0.84], "line_num": 2},
        ],
        created_at=created_at,
        updated_at=created_at,
        exported_at=exported_at,
        line_items=[
            ReceiptLineItem(
                line_index=index,
                description=description,
                quantity=Decimal(quantity),
                unit_price=Decimal(unit_price),
                line_total=Decimal(line_total),
                expense_category=classify_expense(description),
                confidence=Decimal("0.85"),
                bbox=[0.1, 0.3 + index * 0.05, 0.9, 0.34 + index * 0.05],
            )
            for index, (description, quantity, unit_price, line_total) in enumerate(lines)
        ],
    )
    return row


def clear() -> None:
    DB_FILE.unlink(missing_ok=True)
    shutil.rmtree(STORAGE_DIR, ignore_errors=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def seed() -> None:
    clear()
    init_db()

    with SessionLocal() as db:
        db.add_all(
            [
                Client(
                    id=CLIENT_MAIN_ID,
                    accountant_id=ACCOUNTANT_ID,
                    business_name="E2E Hardware & Supply",
                    registration_number="202301234567",
                    sst_number="W10-1808-32000123",
                    industry_category="HARDWARE",
                ),
                Client(
                    id=CLIENT_EMPTY_ID,
                    accountant_id=ACCOUNTANT_ID,
                    business_name="E2E Second Client",
                    registration_number="202309876543",
                    sst_number=None,
                    industry_category="RETAIL",
                ),
            ]
        )
        db.flush()

        now = utcnow()
        db.add_all(
            [
                receipt(
                    rid=R_MATH,
                    client_id=CLIENT_MAIN_ID,
                    filename="math-mismatch.jpg",
                    status=ReceiptStatus.STATUS_NEEDS_REVIEW,
                    merchant="Kedai E2E Hardware",
                    invoice_date=CURRENT_MONTH_DAY,
                    invoice_number="INV-E2E-001",
                    subtotal="245.00",
                    tax="15.00",
                    total="265.00",
                    created_at=now - timedelta(minutes=5),
                    flags=["MATH_MISMATCH_DELTA_5.00"],
                    discrepancy="5.00",
                    confidence="0.72",
                    lines=[
                        ("PVC pipe 1/2 inch", "4", "35.00", "140.00"),
                        ("Screw pack 100pcs", "3", "35.00", "105.00"),
                    ],
                ),
                receipt(
                    rid=R_CLEAN,
                    client_id=CLIENT_MAIN_ID,
                    filename="clean-review.jpg",
                    status=ReceiptStatus.STATUS_NEEDS_REVIEW,
                    merchant="Restoran E2E",
                    invoice_date=CURRENT_MONTH_DAY,
                    invoice_number="INV-E2E-002",
                    subtotal="83.00",
                    tax="5.20",
                    total="88.20",
                    created_at=now - timedelta(minutes=4),
                    lines=[("Nasi lemak set", "2", "25.00", "50.00"), ("Kopi-O", "3", "11.00", "33.00")],
                ),
                receipt(
                    rid=R_SAVE,
                    client_id=CLIENT_MAIN_ID,
                    filename="save-me.jpg",
                    status=ReceiptStatus.STATUS_NEEDS_REVIEW,
                    merchant="Bengkel E2E",
                    invoice_date=CURRENT_MONTH_DAY,
                    invoice_number="INV-E2E-003",
                    subtotal="100.00",
                    tax="6.00",
                    total="106.00",
                    created_at=now - timedelta(minutes=3),
                    lines=[("Engine oil 4L", "1", "100.00", "100.00")],
                ),
                receipt(
                    rid=R_REJECT,
                    client_id=CLIENT_MAIN_ID,
                    filename="reject-me.jpg",
                    status=ReceiptStatus.STATUS_NEEDS_REVIEW,
                    merchant="Kedai Runcit E2E",
                    invoice_date=CURRENT_MONTH_DAY,
                    invoice_number="INV-E2E-004",
                    subtotal="40.00",
                    tax="0.00",
                    total="40.00",
                    created_at=now - timedelta(minutes=2),
                    lines=[("Baju kerja", "1", "40.00", "40.00")],
                ),
                receipt(
                    rid=R_VERIFIED,
                    client_id=CLIENT_MAIN_ID,
                    filename="verified.jpg",
                    status=ReceiptStatus.STATUS_VERIFIED,
                    merchant="Pembekal E2E",
                    invoice_date=CURRENT_MONTH_DAY,
                    invoice_number="INV-E2E-005",
                    subtotal="150.00",
                    tax="0.00",
                    total="150.00",
                    created_at=now - timedelta(days=1),
                    lines=[("Tool box", "1", "150.00", "150.00")],
                ),
                receipt(
                    rid=R_EXPORTED,
                    client_id=CLIENT_MAIN_ID,
                    filename="exported.jpg",
                    status=ReceiptStatus.STATUS_EXPORTED,
                    merchant="Pembekal E2E",
                    invoice_date=date(2026, 9, 5),
                    invoice_number="INV-E2E-006",
                    subtotal="320.00",
                    tax="0.00",
                    total="320.00",
                    created_at=now - timedelta(days=2),
                    exported_at=now - timedelta(days=2),
                    lines=[("Aluminium sheet", "2", "160.00", "320.00")],
                ),
                receipt(
                    rid=R_EXPORTED_FROZEN,
                    client_id=CLIENT_MAIN_ID,
                    filename="frozen-exported.jpg",
                    status=ReceiptStatus.STATUS_EXPORTED,
                    merchant="Pembekal Beku E2E",
                    invoice_date=FIXED_MONTH_DAY,
                    invoice_number="INV-E2E-007",
                    subtotal="95.00",
                    tax="0.00",
                    total="95.00",
                    created_at=now - timedelta(days=3),
                    exported_at=now - timedelta(days=3),
                    lines=[("Cable roll", "1", "95.00", "95.00")],
                ),
                receipt(
                    rid=R_MARK,
                    client_id=CLIENT_MAIN_ID,
                    filename="mark-exported.jpg",
                    status=ReceiptStatus.STATUS_VERIFIED,
                    merchant="Pembekal Mac E2E",
                    invoice_date=FIXED_MONTH_DAY,
                    invoice_number="INV-E2E-008",
                    subtotal="180.00",
                    tax="0.00",
                    total="180.00",
                    created_at=now - timedelta(days=4),
                    lines=[("Gear set", "1", "180.00", "180.00")],
                ),
                receipt(
                    rid=R_REJECTED,
                    client_id=CLIENT_MAIN_ID,
                    filename="rejected.jpg",
                    status=ReceiptStatus.STATUS_REJECTED,
                    merchant="Tidak Sah E2E",
                    invoice_date=CURRENT_MONTH_DAY,
                    invoice_number="INV-E2E-009",
                    subtotal="12.00",
                    tax="0.00",
                    total="12.00",
                    created_at=now - timedelta(days=5),
                    lines=[("Minuman", "1", "12.00", "12.00")],
                ),
                receipt(
                    rid=R_UNREADABLE,
                    client_id=CLIENT_MAIN_ID,
                    filename="unreadable.jpg",
                    status=ReceiptStatus.ERR_UNREADABLE,
                    merchant=None,
                    invoice_date=None,
                    invoice_number=None,
                    subtotal=None,
                    tax=None,
                    total=None,
                    created_at=now - timedelta(days=6),
                    processing_error="OCR could not read this scan",
                    confidence="0.00",
                    lines=[],
                ),
                receipt(
                    rid=R_PROCESSING,
                    client_id=CLIENT_MAIN_ID,
                    filename="processing.jpg",
                    status=ReceiptStatus.PROCESSING_OCR,
                    merchant=None,
                    invoice_date=None,
                    invoice_number=None,
                    subtotal=None,
                    tax=None,
                    total=None,
                    created_at=now - timedelta(seconds=30),
                    confidence="0.00",
                    lines=[],
                ),
            ]
        )
        db.add(
            ReceiptAuditLog(
                receipt_id=R_VERIFIED,
                user_id=ACCOUNTANT_ID,
                field_name="grand_total",
                old_value="140.00",
                new_value="150.00",
                created_at=now - timedelta(days=1, hours=1),
            )
        )
        db.commit()


if __name__ == "__main__":
    seed()
    print(f"seeded {DB_FILE.name} + {STORAGE_DIR.name}")
