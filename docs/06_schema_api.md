# Kenyalang Ledger — Step 6: Backend Schema, Data Models & API Contracts

---

## 6.1 Relational Database DDL (PostgreSQL / SQLite Compatible)

The schema enforces strict multi-tenant isolation via `client_id` foreign keys, maintains high-performance indices on financial queries, and stores raw spatial OCR tokens in `JSONB` for zero-data-loss auditability.

> **Implementation note.** This DDL is realized as SQLAlchemy 2.0 models (`app/models/*.py`) with
> portable column types: `JSONBType` → `JSONB` on PostgreSQL / `JSON` on SQLite, `GUID` → native
> `UUID` / `CHAR(36)`, `Money = NUMERIC(12,2)`, `Confidence = NUMERIC(3,2)`. Tables are created by
> `Base.metadata.create_all` for dev/demo; production is expected to run Alembic migrations. The
> `receipt_audit_logs` write path ships with the update/verify flow (§6.3.4); the audit-trail read
> route (§6.3.7) remains future intent.

```sql
-- Enable UUID generation extension (PostgreSQL)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- 1. CLIENT WORKSPACES (Tenant Partition for Accountants)
-- ============================================================================
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    accountant_id UUID NOT NULL, -- Owner/Accountant ID
    business_name VARCHAR(255) NOT NULL,
    registration_number VARCHAR(64), -- SSM / BRN (e.g., 202001012345 or 123456-X)
    sst_number VARCHAR(64),          -- SST Registration No (e.g., W10-1808-32000018)
    industry_category VARCHAR(64),   -- 'F&B', 'HARDWARE', 'WORKSHOP', 'RETAIL'
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_clients_accountant ON clients(accountant_id);

-- ============================================================================
-- 2. RECEIPTS & INVOICES (Core Header Entity)
-- ============================================================================
CREATE TYPE receipt_status AS ENUM (
    'PENDING_UPLOAD',
    'UPLOADED',
    'PROCESSING_OCR',
    'PROCESSING_LLM',
    'VALIDATING_MATH',
    'STATUS_NEEDS_REVIEW',
    'STATUS_AUTO_VERIFIED',
    'STATUS_VERIFIED',
    'STATUS_EXPORTED',
    'ERR_UNREADABLE',
    'ERR_TIMEOUT',
    'ERR_FILE_CORRUPT'
);

CREATE TABLE receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- Ingestion & Storage Metadata
    original_filename VARCHAR(255) NOT NULL,
    storage_path VARCHAR(512) NOT NULL,     -- e.g., 'tenants/{client_id}/{receipt_id}.webp'
    mime_type VARCHAR(64) NOT NULL,         -- original upload: 'image/jpeg', 'image/png', 'image/heic', 'application/pdf'
    file_size_bytes INT NOT NULL,

    -- Pipeline Execution State
    status receipt_status NOT NULL DEFAULT 'PENDING_UPLOAD',
    processing_error VARCHAR(255),          -- Populated if status starts with 'ERR_'

    -- Extracted Header Entities
    merchant_name VARCHAR(255),
    merchant_brn VARCHAR(64),
    merchant_sst VARCHAR(64),
    invoice_date DATE,
    invoice_number VARCHAR(128),

    -- Financial Totals (Numeric for absolute precision in Ringgit)
    subtotal NUMERIC(12, 2),
    tax_amount NUMERIC(12, 2) DEFAULT 0.00,  -- SST amount
    grand_total NUMERIC(12, 2),

    -- Validation & Confidence Telemetry
    overall_confidence NUMERIC(3, 2),        -- 0.00 to 1.00
    math_discrepancy NUMERIC(12, 2) DEFAULT 0.00, -- abs(sum(line_total) + tax - grand_total)
    validation_flags JSONB NOT NULL DEFAULT '[]'::jsonb, -- e.g. ["MATH_MISMATCH", "LOW_CONFIDENCE"]
    field_provenance JSONB NOT NULL DEFAULT '[]'::jsonb, -- [{'name','confidence','bbox'}] per-field provenance
    ocr_raw_tokens JSONB NOT NULL DEFAULT '[]'::jsonb,   -- Full array of OCRToken objects

    -- Timestamps & Verification Audit
    verified_by UUID,
    verified_at TIMESTAMPTZ,
    exported_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Compound index for fast Inbox listing and filtering
CREATE INDEX idx_receipts_client_status ON receipts(client_id, status);
CREATE INDEX idx_receipts_client_date ON receipts(client_id, invoice_date DESC);

-- ============================================================================
-- 3. RECEIPT LINE ITEMS
-- ============================================================================
CREATE TABLE receipt_line_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    receipt_id UUID NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    line_index INT NOT NULL,                 -- 0-indexed position on receipt
    description VARCHAR(255) NOT NULL,
    quantity NUMERIC(10, 3) NOT NULL DEFAULT 1.000,
    unit_price NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    line_total NUMERIC(12, 2) NOT NULL DEFAULT 0.00,

    -- Spatial Bounding Box & Confidence for GUI highlighting
    confidence NUMERIC(3, 2) NOT NULL DEFAULT 1.00,
    bbox JSONB,                              -- [x_min, y_min, x_max, y_max] normalized (0.0 - 1.0)

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_line_items_receipt ON receipt_line_items(receipt_id, line_index);

-- ============================================================================
-- 4. AUDIT LOGS (Compliance Trail for Manual Overrides)
-- ============================================================================
CREATE TABLE receipt_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    receipt_id UUID NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    field_name VARCHAR(64) NOT NULL,        -- 'grand_total', 'merchant_name', etc.
    old_value TEXT,
    new_value TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_receipt ON receipt_audit_logs(receipt_id);
```

---

## 6.2 Core Pydantic Schemas (`schemas/receipt.py`)

These Pydantic models govern LLM structured extraction via `instructor`, the reconciler input, the
upload response, and the review-console list/detail/update envelopes (§6.3.2–§6.3.4). The extraction schema is **flat**: the LLM receives scalars plus a `line_items`
array, and per-field provenance is attached afterwards by `extractor.attach_provenance`.

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.models.receipt import ReceiptStatus

# Line item parsed from receipt
class LineItemSchema(BaseModel):
    line_index: int = Field(..., ge=0)
    description: str
    quantity: Decimal = Decimal("1.00")
    unit_price: Decimal = Decimal("0.00")
    line_total: Decimal = Decimal("0.00")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    bbox: Optional[list[float]] = None  # normalized 0.0-1.0, validated

# Flat extraction schema passed directly to the LLM (instructor Mode.TOOLS)
class ExtractedReceiptData(BaseModel):
    merchant_name: Optional[str] = Field(None, description="Trade name of supplier/shop")
    merchant_brn: Optional[str] = Field(None, description="Malaysian Business Registration Number")
    merchant_sst: Optional[str] = Field(None, description="SST registration number if visible")
    invoice_date: Optional[date] = Field(None, description="Transaction date on the receipt")
    invoice_number: Optional[str] = Field(None, description="Receipt or Invoice sequence number")
    subtotal: Optional[Decimal] = Field(None, description="Subtotal before tax")
    tax_amount: Optional[Decimal] = Field(Decimal("0.00"), description="Total SST or service tax")
    grand_total: Optional[Decimal] = Field(None, description="Final payable amount in MYR")
    line_items: list[LineItemSchema] = Field(default_factory=list)

# Per-field provenance attached by the extractor (NOT returned by the LLM):
# name + measured confidence + the bbox of the OCR token that supports the value.
# A value with no supporting token gets confidence 0.0 (fail closed).
class ExtractedField(BaseModel):
    name: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    bbox: Optional[list[float]] = None  # normalized 0.0-1.0, validated

# Reconciler input: the extraction payload + provenance.
class ParsedReceiptSchema(ExtractedReceiptData):
    fields: list[ExtractedField] = Field(default_factory=list)

    def get_fields(self) -> list[ExtractedField]:
        """Every audited field: header provenance followed by the line items."""
        items = [
            ExtractedField(name=f"line_items[{i}]", confidence=item.confidence, bbox=item.bbox)
            for i, item in enumerate(self.line_items)
        ]
        return [*self.fields, *items]

# 202 Accepted envelope for a receipt batch upload (§6.3.1)
class ReceiptUploadItem(BaseModel):
    id: UUID
    filename: str
    status: ReceiptStatus

class ReceiptUploadResponse(BaseModel):
    batch_id: UUID
    total_received: int
    receipts: list[ReceiptUploadItem]
```

> **Nullability is deliberate.** `grand_total` is `Optional` so a faded receipt whose total is
> unreadable still produces a parseable payload; the reconciler's `INVALID_GRAND_TOTAL` flag is what
> routes it to review. `tax_amount` defaults to `Decimal("0.00")` when the receipt states no tax.
>
> **Validators.** Money fields (`subtotal`, `tax_amount`, `grand_total`, and each line item's
> `quantity`/`unit_price`/`line_total`) reject non-finite values (`NaN`/`Infinity`); `bbox` is
> validated to the normalized `0.0–1.0` range on both `ExtractedField` and `LineItemSchema`. The
> earlier `BoundingBox` model was removed — no caller used it.
>
> **Shipped review-console schemas (§6.3.2–§6.3.4).** The module now also defines:
> `ReceiptField {name, confidence, bbox}` and `ReceiptOcrToken {text, confidence, bbox, line_num}`;
> `ReceiptListItem` / `ReceiptListResponse {total, limit, offset, items}`;
> `ReceiptDetailLineItem {id, line_index, description, quantity, unit_price, line_total, confidence,
> bbox}` and `ReceiptDetailResponse` (full detail with `fields` / `line_items` / `ocr_tokens` /
> `image_url` / `processing_error` / `created_at` / `updated_at` / `verified_at`); and
> `ReceiptUpdateLineItem` / `ReceiptUpdateRequest` / `ReceiptUpdateResponse {id, status, updated_at,
> verified_by, math_discrepancy}`. The per-field provenance returned as `fields` is persisted on the
> receipt row in `receipts.field_provenance` (`[{'name', 'confidence', 'bbox'}]`, §6.1).
>
> **Money on the wire is decimal strings.** Every monetary value (`subtotal`, `tax_amount`,
> `grand_total`, line-item `unit_price` / `line_total`, `math_discrepancy`) serializes as a JSON
> **string** (e.g. `"105.47"`), never a float — the frontend parses exact BigInt cents.
> `quantity` is quantized to 2 decimal places; `bbox` is `[x_min, y_min, x_max, y_max]` normalized
> 0.0–1.0 or `null`.


---

## 6.3 Contract-First REST API Specifications

> **Implementation status (current).** Shipping route groups: the batch upload endpoint (§6.3.1,
> mounted at `/api/v1`), the client-workspace CRUD + health routes (§6.3.5, mounted at
> `/api/clients`), and — as of Sprint 3 — the Inbox list (§6.3.2), receipt detail (§6.3.3),
> receipt image streaming (§6.3.3) and update/verify (§6.3.4), all under `/api/v1` and all
> tenancy-guarded (foreign tenant → `404`, never `403`). The dashboard (§6.3.6) and audit-trail
> (§6.3.7) routes and the export engine (§6.4) remain the **target contract for future workers** —
> specified here but not yet implemented, with no production code backing them.

### 1. Ingestion: Batch Upload Receipts

* **Route:** `POST /api/v1/clients/{client_id}/receipts/upload`
* **Content-Type:** `multipart/form-data`
* **Request:** `files: UploadFile[]` (max 50 files per batch, max 15 MiB per file)
* **Behavior:** The pipeline (preprocess → OCR → LLM extraction → audit) runs **inline and
  synchronously** within the request; no queue or background worker is involved. All files are
  **preflight-read** first (size limit + magic-byte check) so a bad file rejects the whole request
  before anything is stored. Each accepted file is then written to private tenant storage and
  processed, and the **entire batch is committed in one transaction** (`db.commit()` once, after the
  loop). If the batch fails, the transaction rolls back and only the blobs written during the
  current request are deleted — no orphan files or half-written rows survive. Image decoding,
  unreadable OCR, and genuine extraction timeout outcomes are persisted with their documented
  `ERR_*` status and `processing_error`. Other extraction failures reject the batch with `503`.
* **Response `202 Accepted`:** reports each file's **terminal** status (there is no
  `PROCESSING_OCR` placeholder in the response):

```json
{
  "batch_id": "b1a7d654-e67c-48be-8f37-679901ad8921",
  "total_received": 2,
  "receipts": [
    {
      "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "filename": "hardware_receipt_01.jpg",
      "status": "STATUS_AUTO_VERIFIED"
    },
    {
      "id": "2b3c4d5e-6f7a-8b9c-0d1e-2f3a4b5c6d7e",
      "filename": "faded_thermal.png",
      "status": "STATUS_NEEDS_REVIEW"
    }
  ]
}
```

Per-file terminal statuses: `STATUS_AUTO_VERIFIED`, `STATUS_NEEDS_REVIEW`, `ERR_UNREADABLE` (fewer
than 5 OCR tokens), `ERR_FILE_CORRUPT` (undecodable image, including HEIC/PDF that cannot be
decoded), or `ERR_TIMEOUT` (the extraction stage exceeded its timeout). A generic (non-timeout)
extraction error is **not** persisted per-file: it aborts the request with `503` and rolls the whole
batch back.

* **Error responses (preflight rejection or complete batch rollback):**
    * `401` unauthenticated; `404` workspace not owned by the session accountant.
    * `422` no files supplied, or an empty file.
    * `413` batch over 50 files, or a file over 15 MiB.
    * `415` file whose **magic bytes** are not a recognized container (extension is ignored).
    * `503` a non-timeout extraction failure; the batch is rolled back.
* **Supported formats (current decision):** the guard accepts JPEG (`FF D8 FF`), PNG, PDF (`%PDF-`),
  and HEIC (ISO-BMFF `ftyp` + `hei*` brand) signatures. Only **raster JPEG/PNG** are processed
  end-to-end today: OpenCV cannot decode HEIC, and PDF pages are not rasterized, so a HEIC or PDF
  upload passes the signature guard and then fails the pipeline as `ERR_FILE_CORRUPT` (persisted,
  not reported as success). HEIC/PDF support is future work; the docs must not claim those paths
  succeed.


### 2. Inbox View: List Client Receipts

* **Route:** `GET /api/v1/clients/{client_id}/receipts`
* **Query Parameters:**
    * `status`: `ALL` (default) | `NEEDS_REVIEW` | `VERIFIED` | `EXPORTED`. `VERIFIED` spans both
      `STATUS_AUTO_VERIFIED` and `STATUS_VERIFIED`. Anything else → `422`.
    * `limit`: int, 1–200, default 50 (`422` outside the bounds)
    * `offset`: int ≥ 0, default 0
* **Behavior:** tenancy-guarded; rows ordered `created_at DESC`. Date-range filters are future work.
* **Response `200 OK`:**

```json
{
  "total": 128,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "filename": "hardware_receipt_01.jpg",
      "merchant_name": "Kim Guan Hardware",
      "invoice_date": "2026-09-12",
      "subtotal": "99.50",
      "tax_amount": "5.97",
      "grand_total": "105.47",
      "status": "STATUS_NEEDS_REVIEW",
      "validation_flags": ["MATH_MISMATCH_DELTA_2.40"],
      "overall_confidence": 0.88,
      "math_discrepancy": "2.40",
      "line_item_count": 2,
      "image_url": "/api/v1/clients/{client_id}/receipts/7c9e6679-.../image"
    }
  ]
}
```

All monetary values are decimal **strings**. Thumbnails are rendered by the console from the
authenticated `image_url` (no separate `thumbnail_url` exists).

### 3. Review Console: Fetch Full Receipt & Tokens

* **Route:** `GET /api/v1/clients/{client_id}/receipts/{receipt_id}` — full
  `ReceiptDetailResponse` for the SCR-03 console: header fields (money as decimal strings),
  `status`, `processing_error`, `math_discrepancy`, `overall_confidence`, `validation_flags`,
  `fields` (per-field provenance `[{name, confidence, bbox}]` from `receipts.field_provenance`),
  `line_items` (`[{id, line_index, description, quantity, unit_price, line_total, confidence, bbox}]`,
  quantity quantized to 2 dp), `ocr_tokens` (`[{text, confidence, bbox, line_num}]`),
  `created_at` / `updated_at` / `verified_at`, and `image_url`. `404` unless the receipt exists
  **and** belongs to `client_id`.
* **Image:** `GET /api/v1/clients/{client_id}/receipts/{receipt_id}/image` streams the stored blob
  via `FileResponse` with `receipt.mime_type` — private tenant storage is never exposed as a static
  mount, and every byte served re-checks tenancy. `404` when the blob is missing. The pre-signed
  high-resolution URL remains future intent; the console fetches `image_url` with the
  `X-Accountant-Id` header and renders an object URL.

### 4. Review Console: Update & Verify Receipt

* **Route:** `PUT /api/v1/clients/{client_id}/receipts/{receipt_id}`
* **Payload:** `ReceiptUpdateRequest`
* **Semantics:**
    * Header keys omitted from the payload are left untouched (`model_fields_set` semantics); an
      explicit `null` clears the stored value.
    * Line items are replaced wholesale, re-indexed `0..n-1`.
    * One `ReceiptAuditLog` row is recorded per changed header field, plus one summary row
      with `field_name = 'line_items'` (`old_value = '<prior> rows'`, `new_value = '<new> rows'`).
    * `math_discrepancy` is recomputed as `abs(sum(line_total) + tax - grand_total)` (exact Decimal;
      `0.00` if `grand_total` is `null`).
    * Validation flags are refreshed: any existing `MATH_MISMATCH_DELTA_*` flags are dropped, and if
      `math_discrepancy > 0.02`, `MATH_MISMATCH_DELTA_{discrepancy:.2f}` is appended.
    * Sets `status = 'STATUS_VERIFIED'`, `verified_by = session.accountant_id`, and `verified_at = utcnow()`.
* **Response `200 OK` (`ReceiptUpdateResponse`):**

```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "status": "STATUS_VERIFIED",
  "updated_at": "2026-09-29T19:03:00Z",
  "verified_by": "00000000-0000-0000-0000-000000000001",
  "math_discrepancy": "0.00"
}
```

Money values are serialized as decimal strings.

---

### 5. Workspace: List & Create Client Profiles

* **Route:** `GET /api/clients` *(mounted without the `/v1` prefix; only the ingestion and future export routes use `/api/v1`)*
* **Behavior:** Returns all client workspaces owned by the authenticated accountant (tenancy guard: `clients.accountant_id == session.user_id`).
* **Response `200 OK`** — `ClientRead` objects (the aggregate `unreviewed_count` / `verified_count` / `last_upload_at` fields shown below are a target contract, not yet computed):

```json
{
  "items": [
    {
      "id": "c1a2b3c4-0000-4000-8000-000000000001",
      "accountant_id": "00000000-0000-0000-0000-000000000001",
      "business_name": "Kim Guan Hardware",
      "registration_number": "202001012345",
      "sst_number": "W10-1808-32000018",
      "industry_category": "HARDWARE",
      "is_active": true,
      "created_at": "2026-09-01T10:00:00Z",
      "updated_at": "2026-09-28T10:12:00Z"
    }
  ]
}
```

* **Route:** `POST /api/clients`
* **Request:** `{"business_name": str, "registration_number": str | null, "sst_number": str | null, "industry_category": str | null}`
* **Response `201 Created`:** Returns the created `ClientRead` object with `id`. `accountant_id` is always taken from the session, never the payload.
* **Errors:** `422` invalid payload, `401` unauthenticated.

### 6. Dashboard: Supplier Spend Summary

* **Route:** `GET /api/v1/clients/{client_id}/dashboard/summary?month=2026-09`
* **Behavior:** Aggregates `receipts` where `status IN ('STATUS_AUTO_VERIFIED', 'STATUS_VERIFIED', 'STATUS_EXPORTED')` for the billing period, grouped by `merchant_name`.
* **Response `200 OK`:**

```json
{
  "month": "2026-09",
  "total_spend": "4820.55",
  "receipt_count": 63,
  "top_suppliers": [
    { "merchant_name": "Kim Guan Hardware", "total_spend": "1204.00", "receipt_count": 12 },
    { "merchant_name": "Uncle Lim Kopi", "total_spend": "342.10", "receipt_count": 21 }
  ],
  "category_breakdown": [
    { "category": "HARDWARE", "total_spend": "2110.40" },
    { "category": "F&B", "total_spend": "880.25" }
  ]
}
```

### 7. Audit Trail: Manual Edit History

* **Route:** `GET /api/v1/clients/{client_id}/receipts/{receipt_id}/audit`
* **Behavior:** Returns rows from `receipt_audit_logs` for the receipt, newest first.
* **Response `200 OK`:**

```json
{
  "items": [
    {
      "id": "e5f6a7b8-0000-4000-8000-000000000009",
      "user_id": "00000000-0000-0000-0000-000000000001",
      "field_name": "grand_total",
      "old_value": "108.00",
      "new_value": "105.47",
      "created_at": "2026-09-29T19:03:00Z"
    }
  ]
}
```

---

## 6.4 Export Engine Specifications

> **Implementation status (current).** Not yet implemented — `services/export_engine.py` is a
> placeholder. The routes, CSV layout and LHDN JSON envelope below are the target contract for
> future workers, retained as architecture intent.

### 1. AutoCount / SQL Account Compatible CSV

* **Route:** `GET /api/v1/clients/{client_id}/exports/accounting-csv?month=2026-09`
* **Response Headers:** `Content-Type: text/csv`, `Content-Disposition: attachment; filename="Kenyalang_PurJournal_202609.csv"`
* **CSV Column Layout:**

```csv
DocDate,DocNo,SupplierCode,SupplierName,Description,ItemCode,Qty,UnitPrice,TaxCode,TaxAmount,TotalAmount
12/09/2026,INV-99120,SUPP-KIMGUAN,Kim Guan Hardware,PVC Pipe 2",HW-PVC-02,1,14.50,SST-6,0.87,15.37
12/09/2026,INV-99120,SUPP-KIMGUAN,Kim Guan Hardware,Minyak Hitam 4L,OIL-4L,1,85.00,SST-6,5.10,90.10
```

### 2. Official LHDN MyInvois v1.1 JSON Payload

* **Route:** `GET /api/v1/clients/{client_id}/exports/myinvois-json?month=2026-09`
* **Transformation Contract:** Formats verified receipts into the official LHDN SDK document envelope (`1.1-Invoice-MultiLineItem-Sample.json`):

```json
{
  "_D": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
  "_A": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
  "_B": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
  "Invoice": [
    {
      "ID": [{ "_": "INV-99120" }],
      "IssueDate": [{ "_": "2026-09-12" }],
      "IssueTime": [{ "_": "14:30:00Z" }],
      "InvoiceTypeCode": [{ "_": "01", "listVersionID": "1.1" }],
      "DocumentCurrencyCode": [{ "_": "MYR" }],
      "AccountingSupplierParty": [
        {
          "Party": [
            {
              "PartyName": [{ "Name": [{ "_": "Kim Guan Hardware" }] }],
              "PartyIdentification": [
                { "ID": [{ "_": "202001012345", "schemeID": "BRN" }] }
              ]
            }
          ]
        }
      ],
      "LegalMonetaryTotal": [
        {
          "LineExtensionAmount": [{ "_": 99.50, "currencyID": "MYR" }],
          "TaxExclusiveAmount": [{ "_": 99.50, "currencyID": "MYR" }],
          "TaxInclusiveAmount": [{ "_": 105.47, "currencyID": "MYR" }],
          "PayableAmount": [{ "_": 105.47, "currencyID": "MYR" }]
        }
      ],
      "InvoiceLine": [
        {
          "ID": [{ "_": "1" }],
          "InvoicedQuantity": [{ "_": 1.0, "unitCode": "C62" }],
          "LineExtensionAmount": [{ "_": 14.50, "currencyID": "MYR" }],
          "Item": [
            { "Description": [{ "_": "PVC Pipe 2\"" }] }
          ]
        },
        {
          "ID": [{ "_": "2" }],
          "InvoicedQuantity": [{ "_": 1.0, "unitCode": "C62" }],
          "LineExtensionAmount": [{ "_": 85.00, "currencyID": "MYR" }],
          "Item": [
            { "Description": [{ "_": "Minyak Hitam 4L" }] }
          ]
        }
      ]
    }
  ]
}
```
