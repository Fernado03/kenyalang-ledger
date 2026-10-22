# Kenyalang Ledger - Step 6: Backend Schema, Data Models & API Contracts

This document mirrors the shipped SQLAlchemy models (`backend/app/models/*.py`), the Pydantic
schemas (`backend/app/schemas/*.py`), and the FastAPI routes (`backend/app/api/*.py`). Every path,
method and JSON field named here exists in the implementation.

---

## 6.1 Relational Database DDL (PostgreSQL / SQLite Compatible)

The schema enforces multi-tenant isolation through `client_id` foreign keys and stores OCR tokens
and per-field provenance as JSON. It is realized as SQLAlchemy 2.0 models with portable column
types: `JSONBType` -> `JSONB` on PostgreSQL / `JSON` on SQLite, `GUID` -> native `UUID` /
`CHAR(36)`, `Money = NUMERIC(12,2)`, `Confidence = NUMERIC(3,2)`, `Quantity = NUMERIC(10,3)`.
Tables are created by `Base.metadata.create_all`; there is no separate queue or job table.

```sql
-- Enable UUID generation extension (PostgreSQL)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- 1. CLIENT WORKSPACES (Tenant Partition for Accountants)
-- ============================================================================
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    accountant_id UUID NOT NULL,               -- owner/accountant id
    business_name VARCHAR(255) NOT NULL,
    registration_number VARCHAR(64),           -- SSM / BRN, e.g. '202001012345'
    sst_number VARCHAR(64),                    -- SST registration no.
    industry_category VARCHAR(64),             -- 'F&B', 'HARDWARE', 'WORKSHOP', 'RETAIL'
    is_active BOOLEAN NOT NULL DEFAULT TRUE,   -- soft delete flag
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
    'STATUS_REJECTED',
    'ERR_UNREADABLE',
    'ERR_TIMEOUT',
    'ERR_FILE_CORRUPT',
    'ERR_EXTRACTION'
);

CREATE TABLE receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- Ingestion & storage metadata
    original_filename VARCHAR(255) NOT NULL,
    storage_path VARCHAR(512) NOT NULL,     -- 'tenants/{client_id}/{receipt_id}{ext}'
    mime_type VARCHAR(64) NOT NULL,         -- image/jpeg, image/png, image/heic, application/pdf
    file_size_bytes INTEGER NOT NULL,

    -- Pipeline execution state
    status receipt_status NOT NULL DEFAULT 'PENDING_UPLOAD',
    processing_error VARCHAR(255),          -- populated when status starts with 'ERR_'

    -- Extracted header entities
    merchant_name VARCHAR(255),
    merchant_brn VARCHAR(64),
    merchant_sst VARCHAR(64),
    invoice_date DATE,
    invoice_number VARCHAR(128),

    -- Financial totals (NUMERIC for absolute precision in Ringgit)
    subtotal NUMERIC(12, 2),
    tax_amount NUMERIC(12, 2) DEFAULT 0.00,
    grand_total NUMERIC(12, 2),

    -- Validation & confidence telemetry
    overall_confidence NUMERIC(3, 2),                  -- 0.00 to 1.00
    math_discrepancy NUMERIC(12, 2) DEFAULT 0.00,      -- abs(sum(line_total) + tax - grand_total)
    validation_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    field_provenance JSONB NOT NULL DEFAULT '[]'::jsonb, -- [{'name','confidence','bbox'}]
    ocr_raw_tokens JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{text, confidence, bbox, line_num}]

    -- Timestamps & verification audit
    verified_by UUID,
    verified_at TIMESTAMPTZ,
    exported_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_receipts_client_status ON receipts(client_id, status);
CREATE INDEX idx_receipts_client_date ON receipts(client_id, invoice_date);

-- ============================================================================
-- 3. RECEIPT LINE ITEMS
-- ============================================================================
CREATE TABLE receipt_line_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    receipt_id UUID NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    line_index INTEGER NOT NULL,             -- 0-indexed position on the receipt
    description VARCHAR(255) NOT NULL,
    quantity NUMERIC(10, 3) NOT NULL DEFAULT 1.000,
    unit_price NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    line_total NUMERIC(12, 2) NOT NULL DEFAULT 0.00,

    -- Fixed taxonomy: F&B, HARDWARE, WORKSHOP, RETAIL, OTHER
    expense_category VARCHAR(16) NOT NULL DEFAULT 'OTHER',

    -- Spatial bounding box & confidence for GUI highlighting
    confidence NUMERIC(3, 2) NOT NULL DEFAULT 1.00,
    bbox JSONB,                              -- [x_min, y_min, x_max, y_max], normalized 0..1

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_line_items_receipt ON receipt_line_items(receipt_id, line_index);

-- ============================================================================
-- 4. AUDIT LOGS (Manual-override trail)
-- ============================================================================
CREATE TABLE receipt_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    receipt_id UUID NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    field_name VARCHAR(64) NOT NULL,         -- 'grand_total', 'status', 'line_items', ...
    old_value TEXT,
    new_value TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_receipt ON receipt_audit_logs(receipt_id);
```

`expense_category` is assigned at write time by `classify_expense()` using a closed keyword
taxonomy. Unknown or null descriptions become `OTHER`; the five persisted values are
`F&B`, `HARDWARE`, `WORKSHOP`, `RETAIL`, `OTHER`.

### 6.1.1 Receipt status values (14 members)

| Status | Written by | Meaning |
|---|---|---|
| `PENDING_UPLOAD` | model default | Declared lifecycle start; not used by the upload route. |
| `UPLOADED` | - | Declared lifecycle state; the upload route writes `PROCESSING_OCR` immediately. |
| `PROCESSING_OCR` | upload handler | Placeholder row committed before the background worker runs. |
| `PROCESSING_LLM` | worker | OCR finished; LLM extraction in progress. |
| `VALIDATING_MATH` | worker | Extraction finished; reconciler audit in progress. |
| `STATUS_NEEDS_REVIEW` | worker | Parse succeeded but flags require an accountant (math mismatch, low confidence, missing total). |
| `STATUS_AUTO_VERIFIED` | worker | Parse succeeded with no blocking flags. |
| `STATUS_VERIFIED` | `PUT /api/v1/clients/{client_id}/receipts/{receipt_id}` | Accountant reviewed/saved the receipt. |
| `STATUS_EXPORTED` | `POST /api/v1/clients/{client_id}/exports/mark` | Included in a marked export batch. |
| `STATUS_REJECTED` | `POST /api/v1/clients/{client_id}/receipts/{receipt_id}/reject` | Manual terminal state; excluded from spend and exports. |
| `ERR_UNREADABLE` | worker | Fewer than five OCR tokens detected. |
| `ERR_TIMEOUT` | worker | Extraction stage exceeded its timeout. |
| `ERR_FILE_CORRUPT` | worker | Image/PDF could not be decoded, or the stored blob could not be read. |
| `ERR_EXTRACTION` | worker | Extraction provider was unavailable or refused the request. |

The worker moves a row `PROCESSING_OCR -> PROCESSING_LLM -> VALIDATING_MATH` and then resolves it
to exactly one terminal state: `STATUS_AUTO_VERIFIED` or `STATUS_NEEDS_REVIEW` on success, or one
of the `ERR_*` states on failure. Status updates are conditional on the row still being in a
`PROCESSING_*` state, so a late task cannot overwrite an accountant's decision.
`STATUS_REJECTED` is never produced by the pipeline: it exists only when an accountant calls the
reject endpoint. A later explicit review save through
`PUT /api/v1/clients/{client_id}/receipts/{receipt_id}` does set the row back to `STATUS_VERIFIED`, but nothing in ingestion or the worker path will change it. A receipt already in
`STATUS_EXPORTED` is immutable: both the review save and the reject call return `409` once
`exported_at` is set, so a month that has been exported cannot drift from its filed file.

---

## 6.2 Core Pydantic Schemas (`schemas/receipt.py`)

The extraction schema is flat: the LLM receives scalars plus `line_items`; per-field provenance is
attached afterwards by the extractor and audited by the reconciler.

```python
class LineItemSchema(BaseModel):
    line_index: int
    description: str
    quantity: Decimal = Decimal("1.00")
    unit_price: Decimal = Decimal("0.00")
    line_total: Decimal = Decimal("0.00")
    confidence: float = 1.0            # 0.0..1.0
    bbox: list[float] | None = None    # [x_min, y_min, x_max, y_max], 0.0..1.0

class ExtractedReceiptData(BaseModel):
    merchant_name: str | None
    merchant_brn: str | None
    merchant_sst: str | None
    invoice_date: date | None
    invoice_number: str | None
    subtotal: Decimal | None
    tax_amount: Decimal | None = Decimal("0.00")
    grand_total: Decimal | None        # nullable on purpose
    line_items: list[LineItemSchema]

class ExtractedField(BaseModel):
    name: str
    confidence: float
    bbox: list[float] | None

class ParsedReceiptSchema(ExtractedReceiptData):
    fields: list[ExtractedField]
```

Money fields reject `NaN`/`Infinity`; `bbox` must be four ordered normalized coordinates.
`ReceiptUploadResponse` is `{batch_id, total_received, receipts:[ReceiptUploadItem]}` where each
item is `{id, filename, status}`. Review-console schemas add:

- `ReceiptListItem` / `ReceiptListResponse {total, limit, offset, items, status_counts}`.
  `status_counts` maps every inbox filter (`ALL`, `NEEDS_REVIEW`, `VERIFIED`, `EXPORTED`,
  `PROCESSING`) to a row count over the whole client, computed by one grouped count so the
  tabs do not need a request each. It ignores the active `status` filter: asking for one
  bucket still reports the others. `VERIFIED` sums `AUTO_VERIFIED` and `VERIFIED`.
- `ReceiptDetailLineItem {id, line_index, description, quantity, unit_price, line_total,
  expense_category, confidence, bbox}`
- `ReceiptField {name, confidence, bbox}`, `ReceiptOcrToken {text, confidence, bbox, line_num}`
- `ReceiptDetailResponse` (all detail fields listed in 6.4.5)
- `ReceiptUpdateLineItem`, `ReceiptUpdateRequest`, `ReceiptUpdateResponse {id, status, updated_at,
  verified_by, math_discrepancy}`
- `ReceiptAuditRead {id, user_id, field_name, old_value, new_value, created_at}` and
  `ReceiptAuditResponse {items}`

Money on the wire is a decimal **string** (e.g. `"105.47"`), including `quantity` (`"1.00"`),
`unit_price`, `line_total`, `subtotal`, `tax_amount`, `grand_total` and `math_discrepancy`;
`overall_confidence` is a JSON number. `bbox` is `[x_min, y_min, x_max, y_max]` or `null`.

---

## 6.3 Authentication, tenancy and storage

### Demo header authentication

- Every route except `GET /api/health/live` and `GET /api/health/ready` requires the header
  `X-Accountant-Id: <uuid>`.
- `app/core/auth.py` accepts the header only when `KENYALANG_ENV` is `local` or `test`
  (case-insensitive). For any other or missing value the guard returns
  `401 {"detail": "Demo authentication disabled"}`.
- A missing header returns `401 {"detail": "Missing X-Accountant-Id header"}`; a malformed UUID
  returns `401 {"detail": "Malformed accountant id"}`.
- `create_app()` refuses to start when `KENYALANG_ENV=production`: it raises
  `RuntimeError("Kenyalang Ledger demo auth must not run in production")`.
- **The header is forgeable.** It is an unsigned demo identity, not authentication. Any caller can
  claim any accountant UUID. Tenancy is still enforced against the claimed id: a client owned by a
  different `accountant_id` is reported as `404`, never `403`. `get_active_owned_client` also
  returns `404` for soft-deleted (`is_active = false`) clients.

### Local blob storage

- Blobs live under `<KENYALANG_STORAGE_ROOT or "storage">/tenants/{client_id}/{receipt_id}{ext}`;
  `receipts.storage_path` stores that relative path. Blobs stay on the API host's local disk;
  there is no object-storage backend and no externally issued download URL.
- Only the sanitized extension is taken from the uploaded filename (`safe_extension`, lowercased,
  `^\\.[a-z0-9]{1,8}$`, otherwise `.bin`). The stored filename is the receipt UUID, so a crafted
  upload name cannot influence the directory.
- Uploads are written to a temporary `.<name>.<random>.part` file and atomically renamed.
- `safe_filename()` strips path separators and control characters for the `original_filename`
  metadata (max 255 chars).
- `load_receipt_file()` resolves the path against the storage root and raises `ValueError` if the
  result escapes that root; the image route maps this to `404`, so a corrupted `storage_path`
  cannot become an arbitrary file read.
- Blobs are served only through `GET /api/v1/clients/{client_id}/receipts/{receipt_id}/image` after a tenancy check; there
  is no static mount.

---

## 6.4 REST API

Module mounting: health and client routes are under `/api`; receipts, exports and dashboard are
under `/api/v1`. All routes below exist. All client-scoped routes return `404` for a client or
receipt that belongs to another accountant.

### 6.4.1 Health

**`GET /api/health/live`** - process liveness, no database access, no auth.

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

**`GET /api/health/ready`** - executes `SELECT 1`; no auth.

`200 OK`:

```json
{
  "status": "ok",
  "database": "connected",
  "dialect": "sqlite",
  "version": "0.1.0"
}
```

`503 Service Unavailable` when the query fails:

```json
{
  "detail": "database unavailable"
}
```

### 6.4.2 Clients

**`GET /api/clients`** - workspaces owned by the session accountant, newest first, with receipt
counts. `unreviewed_count` counts `STATUS_NEEDS_REVIEW`; `verified_count` counts
`STATUS_AUTO_VERIFIED`, `STATUS_VERIFIED` plus `STATUS_EXPORTED` (an exported receipt is still a
verified one, and dropping it made a fully processed workspace look unreviewed). `total_count`
counts every receipt whatever its status, so the dashboard's `Total receipts` stat is not
silently `verified_count + unreviewed_count`. Rejected and failed receipts are counted by
neither of the two review counts.

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
      "updated_at": "2026-09-28T10:12:00Z",
      "unreviewed_count": 3,
      "verified_count": 12,
      "total_count": 19
    }
  ]
}
```

**`POST /api/clients`** - body `{business_name, registration_number?, sst_number?,
industry_category?}`; `accountant_id` always comes from the header. Returns `201` with a single
`ClientRead` object:

```json
{
  "id": "c1a2b3c4-0000-4000-8000-000000000001",
  "accountant_id": "00000000-0000-0000-0000-000000000001",
  "business_name": "Kim Guan Hardware",
  "registration_number": "202001012345",
  "sst_number": "W10-1808-32000018",
  "industry_category": "HARDWARE",
  "is_active": true,
  "created_at": "2026-09-01T10:00:00Z",
  "updated_at": "2026-09-01T10:00:00Z"
}
```

Errors: `401` unauthenticated, `422` validation, `409` integrity failure.

**`GET /api/clients/{client_id}`** - one `ClientRead`, including soft-deleted workspaces so they can
be reactivated; `404` when the client is not owned by the caller.

**`PUT /api/clients/{client_id}`** - partial update; body may contain any of `business_name`,
`registration_number`, `sst_number`, `industry_category`, `is_active`. Returns `200` with the
updated `ClientRead`.

**`DELETE /api/clients/{client_id}`** - soft delete: sets `is_active = false` and returns `204`
with no body. Receipt history is preserved.

### 6.4.3 Receipt upload

**`POST /api/v1/clients/{client_id}/receipts/upload`** - `multipart/form-data`, repeated `files`
field.

Preflight (before anything is written):

| Check | Failure |
|---|---|
| client exists, active, owned | `404` |
| at least one file | `422` |
| at most 50 files | `413` |
| each file non-empty | `422` |
| each file <= 15 MiB | `413` |
| batch total <= 50 MiB | `413` |
| magic bytes are JPEG (`FF D8 FF`), PNG (`89 50 4E 47 0D 0A 1A 0A`), PDF (`%PDF-`), or HEIC (ISO-BMFF `ftyp` + `hei*` brand) | `415` |

The filename extension is ignored; the detected MIME type is persisted. JPEG, PNG, HEIC and PDF
are all decoded by the preprocessor (HEIC through `pillow-heif`, PDF page 1 through PyMuPDF).
Images are capped at 40 megapixels.

Duplicate dedupe: within one workspace, a file whose sanitized filename and byte size match an
existing receipt is not stored again; the existing receipt is returned in the response with its
current status. Duplicates inside the same batch also collapse to one receipt.

Each accepted file creates a receipt row with `status = PROCESSING_OCR` in a single transaction,
and the blob is written under tenant storage. If the transaction fails, the blobs written by that
request are deleted. The transaction commits before the pipeline is queued; responses therefore
never report a terminal status for a newly created row.

Response `202 Accepted`:

```json
{
  "batch_id": "b1a7d654-e67c-48be-8f37-679901ad8921",
  "total_received": 2,
  "receipts": [
    {
      "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "filename": "hardware_receipt_01.jpg",
      "status": "PROCESSING_OCR"
    },
    {
      "id": "2b3c4d5e-6f7a-8b9c-0d1e-2f3a4b5c6d7e",
      "filename": "faded_thermal.png",
      "status": "PROCESSING_OCR"
    }
  ]
}
```

`total_received` counts the returned items, including deduped ones. `batch_id` is generated per
request.

Background processing: extraction runs after the response in a FastAPI `BackgroundTask` in the API
process. There is no external broker or worker. The worker re-reads the row, moves it through
`PROCESSING_OCR -> PROCESSING_LLM -> VALIDATING_MATH`, and finishes as `STATUS_AUTO_VERIFIED`,
`STATUS_NEEDS_REVIEW`, `ERR_UNREADABLE` (< 5 OCR tokens), `ERR_TIMEOUT`, `ERR_FILE_CORRUPT`
(undecodable file or unreadable blob) or `ERR_EXTRACTION` (provider outage), always storing
`processing_error` for `ERR_*`.

**Restart caveat:** because the task lives in-process, a process restart (or crash) between the
commit and task completion strands the row in `PROCESSING_*` indefinitely. There is no retry
queue. Re-uploading the identical filename and byte size dedupes onto the stranded row, so the
accountant must use a changed file (or a new filename) to create a fresh receipt.

### 6.4.4 Receipt list

**`GET /api/v1/clients/{client_id}/receipts`**

Query parameters:

- `status`: `ALL` (default) | `NEEDS_REVIEW` | `VERIFIED` | `EXPORTED` | `REJECTED`.
  `VERIFIED` spans `STATUS_AUTO_VERIFIED` and `STATUS_VERIFIED`. Any other value is `422`.
- `limit`: 1-200, default 50.
- `offset`: >= 0, default 0.

Rows are ordered `created_at DESC`; `total` is the filtered count.

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
      "image_url": "/api/v1/clients/c1a2b3c4-0000-4000-8000-000000000001/receipts/7c9e6679-7425-40de-944b-e07fc1f90ae7/image"
    }
  ]
}
```

### 6.4.5 Receipt detail

**`GET /api/v1/clients/{client_id}/receipts/{receipt_id}`** - `404` unless the receipt exists and
belongs to `client_id`. Line items are returned in `line_index` order.

```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "client_id": "c1a2b3c4-0000-4000-8000-000000000001",
  "filename": "hardware_receipt_01.jpg",
  "status": "STATUS_NEEDS_REVIEW",
  "processing_error": null,
  "image_url": "/api/v1/clients/c1a2b3c4-0000-4000-8000-000000000001/receipts/7c9e6679-7425-40de-944b-e07fc1f90ae7/image",
  "merchant_name": "Kim Guan Hardware",
  "merchant_brn": "202001012345",
  "merchant_sst": "W10-1808-32000018",
  "invoice_date": "2026-09-12",
  "invoice_number": "INV-99120",
  "subtotal": "99.50",
  "tax_amount": "5.97",
  "grand_total": "105.47",
  "math_discrepancy": "2.40",
  "overall_confidence": 0.88,
  "validation_flags": ["MATH_MISMATCH_DELTA_2.40"],
  "fields": [
    { "name": "merchant_name", "confidence": 0.96, "bbox": [0.05, 0.05, 0.9, 0.08] }
  ],
  "line_items": [
    {
      "id": "3f1c2d3e-0000-4000-8000-000000000010",
      "line_index": 0,
      "description": "PVC Pipe 2\"",
      "quantity": "1.00",
      "unit_price": "14.50",
      "line_total": "14.50",
      "expense_category": "HARDWARE",
      "confidence": 0.93,
      "bbox": [0.05, 0.15, 0.9, 0.18]
    }
  ],
  "ocr_tokens": [
    { "text": "KIM GUAN HARDWARE", "confidence": 0.96, "bbox": [0.05, 0.05, 0.9, 0.08], "line_num": 0 }
  ],
  "created_at": "2026-09-29T18:58:00Z",
  "updated_at": "2026-09-29T19:03:00Z",
  "verified_at": null
}
```

**`GET /api/v1/clients/{client_id}/receipts/{receipt_id}/image`** - streams the stored blob with
`Content-Type` equal to the persisted `mime_type`; `404` when the receipt is unknown or the blob is
missing. No static file mount is involved.

### 6.4.6 Receipt update (verify)

**`PUT /api/v1/clients/{client_id}/receipts/{receipt_id}`** - body `ReceiptUpdateRequest`:

```json
{
  "merchant_name": "Kim Guan Hardware Sdn Bhd",
  "grand_total": "105.47",
  "line_items": [
    { "description": "PVC Pipe 2\"", "quantity": "1.00", "unit_price": "14.50", "line_total": "14.50" }
  ]
}
```

Semantics:

- Header keys omitted from the payload are left untouched; an explicit `null` clears the value.
- `line_items`, when the key is present with a list, replaces all rows and re-indexes them `0..n-1`;
  `expense_category` is recomputed with `classify_expense`. When the key is absent, or present as
  `null`, stored rows are kept; an explicit `[]` clears them.
- `math_discrepancy` is recomputed from persisted rows as
  `abs(sum(line_total) + tax_amount - grand_total)` (exact Decimal; `0.00` when `grand_total` is
  null).
- Existing `MATH_MISMATCH_DELTA_*` flags are dropped; if the new discrepancy exceeds `0.02`,
  `MATH_MISMATCH_DELTA_{d:.2f}` is appended.
- The status becomes `STATUS_VERIFIED`, with `verified_by` and `verified_at` set.
- One audit row is written per header field whose value actually changed, plus `field_name =
  'line_items'` when the submitted descriptions/totals differ from the stored rows, plus a `status`
  row when the prior status was not `STATUS_VERIFIED`. `old_value`/`new_value` are strings;
  `line_items` values are row counts like `'2 rows'`.

Response `200 OK`:

```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "status": "STATUS_VERIFIED",
  "updated_at": "2026-09-29T19:03:00Z",
  "verified_by": "00000000-0000-0000-0000-000000000001",
  "math_discrepancy": "0.00"
}
```

### 6.4.7 Receipt reject

**`POST /api/v1/clients/{client_id}/receipts/{receipt_id}/reject`** - no body. Sets
`status = STATUS_REJECTED`, `verified_by`, `verified_at`, and writes one audit row with
`field_name = 'status'`, `old_value` = prior status, `new_value = 'STATUS_REJECTED'`. Returns
`200` with the same `ReceiptUpdateResponse` envelope:

```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "status": "STATUS_REJECTED",
  "updated_at": "2026-09-29T19:04:00Z",
  "verified_by": "00000000-0000-0000-0000-000000000001",
  "math_discrepancy": "2.40"
}
```

`STATUS_REJECTED` is a manual terminal state: the pipeline never produces or clears it, rejected
receipts are excluded from dashboard spend and from both export formats, and only an explicit
accountant action changes it (a review save via `PUT /api/v1/clients/{client_id}/receipts/{receipt_id}`, which sets
`STATUS_VERIFIED`, or another reject call). Nothing in the ingestion or background path will move
a rejected receipt on its own. Receipts already in `STATUS_EXPORTED` cannot be rejected or
re-saved: both endpoints return `409` and the row keeps its `exported_at`.

### 6.4.8 Audit trail

**`GET /api/v1/clients/{client_id}/receipts/{receipt_id}/audit`** - newest first, at most 200 rows.

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

### 6.4.9 Dashboard summary

**`GET /api/v1/clients/{client_id}/dashboard/summary?month=2026-09`** - optional `month` in strict
`YYYY-MM` form (defaults to the current month; invalid values are `422`). Includes receipts in
`STATUS_AUTO_VERIFIED`, `STATUS_VERIFIED` and `STATUS_EXPORTED`. `total_spend` sums `grand_total`;
top suppliers group by `merchant_name` (blank names omitted), ordered spend-descending and capped
at 5. `category_breakdown` always contains all five categories in taxonomy order and sums pre-tax
`receipt_line_items.line_total`, so category totals need not equal `total_spend` when tax is
present.

```json
{
  "month": "2026-09",
  "total_spend": "4820.55",
  "top_suppliers": [
    { "supplier_name": "Kim Guan Hardware", "total_spend": "1204.00", "receipt_count": 12 },
    { "supplier_name": "Uncle Lim Kopi", "total_spend": "342.10", "receipt_count": 21 }
  ],
  "category_breakdown": [
    { "category": "F&B", "total_spend": "880.25" },
    { "category": "HARDWARE", "total_spend": "2110.40" },
    { "category": "WORKSHOP", "total_spend": "0.00" },
    { "category": "RETAIL", "total_spend": "415.60" },
    { "category": "OTHER", "total_spend": "120.30" }
  ]
}
```

---

## 6.5 Export engine

All export routes are tenancy-guarded, accept an optional strict `month=YYYY-MM`, and select
receipts in `STATUS_VERIFIED`, `STATUS_AUTO_VERIFIED` or `STATUS_EXPORTED`. Month filtering uses
`invoice_date` when present, otherwise the `created_at` date. Downloads are pure reads: neither
the CSV nor the JSON route changes a receipt status.

### 6.5.1 Accounting CSV

**`GET /api/v1/clients/{client_id}/exports/accounting-csv?month=2026-09`**

Response headers: `Content-Type: text/csv; charset=utf-8`,
`Content-Disposition: attachment; filename="Kenyalang_PurJournal_202609.csv"` (suffix `all` when
`month` is omitted).

Columns, in order:

`DocDate,DocNo,SupplierCode,SupplierName,Description,ItemCode,Qty,UnitPrice,TaxCode,TaxAmount,TotalAmount`

- `DocDate`: `DD/MM/YYYY` from `invoice_date`, else `created_at`, else today.
- `DocNo`: `invoice_number`, else `REC-<first 8 hex of receipt id>`.
- `SupplierCode`: `SUPP-` plus the first 10 alphanumerics of `merchant_brn`; if absent, of
  `merchant_name`; otherwise `SUPP-CASH`.
- `SupplierName`: `merchant_name`, else `Cash Supplier`.
- One row per line item: `ItemCode = ITEM-<line_index+1:02d>` (e.g. `ITEM-01`), `Qty` trimmed to at
  most 3 decimals, `UnitPrice` at 2 decimals.
- A receipt with no line items emits one summary row: `Description = General Purchase`,
  `ItemCode = ITEM-01`, `Qty = 1`, `UnitPrice = subtotal` (or `grand_total`), `TaxAmount =
  tax_amount`, `TotalAmount = grand_total`.
- `TaxCode`: `SST-6` when `tax_amount > 0`, otherwise `NONE`.
- Tax is allocated per line in **integer cents** using the largest-remainder method: each line
  gets `floor(line_cents * tax_cents / subtotal_cents)`, and leftover cents go one at a time to
  the largest remainders (ties by line order). Allocation sums exactly to `tax_cents` when
  distributable. `TaxAmount` is the allocated cents / 100; `TotalAmount = line_total + allocated
  tax`.

Sample (note CSV quoting around a description containing a comma):

```csv
DocDate,DocNo,SupplierCode,SupplierName,Description,ItemCode,Qty,UnitPrice,TaxCode,TaxAmount,TotalAmount
12/09/2026,INV-99120,SUPP-2020010123,Kim Guan Hardware,"PVC Pipe 2""",ITEM-01,1,14.50,SST-6,0.87,15.37
12/09/2026,INV-99120,SUPP-2020010123,Kim Guan Hardware,Minyak Hitam 4L,ITEM-02,1,85.00,SST-6,5.10,90.10
```

Formula-injection guard: any **text** cell beginning with `=`, `+`, `-`, `@`, tab or carriage
return is prefixed with `'` so spreadsheet software treats it as literal text. Numeric cells are
written unquoted/prefixed.

### 6.5.2 MyInvois-shaped JSON (draft)

**`GET /api/v1/clients/{client_id}/exports/myinvois-json?month=2026-09`** returns a JSON document
with `Content-Disposition: attachment; filename="Kenyalang_MyInvois_202609.json"`.

The envelope is **draft** and mirrors the official SDK sample layout. It is not validated against
the MyInvois schema, is not submitted anywhere, and generating it never changes receipt status.
Supplier name is `merchant_name` or `Unknown Supplier`; party IDs use `schemeID: "BRN"` when
`merchant_brn` exists, `schemeID: "SST"` with the canonical registration number when
`merchant_sst` carries one, and `NA`/`BRN` otherwise. The SST value is canonicalised with
`extract_sst_number` (backend `services/reconciler.py`) because a stored field may hold the BRN
alongside it (`"200401032489 / Y24-1808-31015655"`); a value with no well-formed token is omitted
rather than exported under the wrong scheme.

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
      "TaxCurrencyCode": [{ "_": "MYR" }],
      "AccountingSupplierParty": [
        {
          "Party": [
            {
              "PartyName": [{ "Name": [{ "_": "Kim Guan Hardware" }] }],
              "PartyLegalEntity": [{ "RegistrationName": [{ "_": "Kim Guan Hardware" }] }],
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
          "AllowanceTotalAmount": [{ "_": 0.0, "currencyID": "MYR" }],
          "ChargeTotalAmount": [{ "_": 0.0, "currencyID": "MYR" }],
          "PayableRoundingAmount": [{ "_": 0.0, "currencyID": "MYR" }],
          "PayableAmount": [{ "_": 105.47, "currencyID": "MYR" }]
        }
      ],
      "TaxTotal": [
        {
          "TaxAmount": [{ "_": 5.97, "currencyID": "MYR" }],
          "TaxSubtotal": [
            {
              "TaxableAmount": [{ "_": 99.50, "currencyID": "MYR" }],
              "TaxAmount": [{ "_": 5.97, "currencyID": "MYR" }],
              "TaxCategory": [
                {
                  "ID": [{ "_": "01" }],
                  "TaxScheme": [
                    { "ID": [{ "_": "OTH", "schemeID": "UN/ECE 5153", "schemeAgencyID": "6" }] }
                  ]
                }
              ]
            }
          ]
        }
      ],
      "InvoiceLine": [
        {
          "ID": [{ "_": "1" }],
          "InvoicedQuantity": [{ "_": 1.0, "unitCode": "C62" }],
          "LineExtensionAmount": [{ "_": 14.50, "currencyID": "MYR" }],
          "TaxTotal": [{ "TaxAmount": [{ "_": 0.87, "currencyID": "MYR" }] }],
          "Item": [{ "Description": [{ "_": "PVC Pipe 2\"" }] }],
          "Price": [{ "PriceAmount": [{ "_": 14.50, "currencyID": "MYR" }] }],
          "ItemPriceExtension": [{ "Amount": [{ "_": 14.50, "currencyID": "MYR" }] }]
        }
      ]
    }
  ]
}
```

Line-level tax uses the same integer-cent largest-remainder allocation as the CSV.

### 6.5.3 Mark as exported

**`POST /api/v1/clients/{client_id}/exports/mark?month=2026-09`** - the only export action that
mutates data. It moves receipts in `STATUS_VERIFIED` or `STATUS_AUTO_VERIFIED` to
`STATUS_EXPORTED`, sets `exported_at`, and writes one audit row per receipt with
`field_name = "status"`, `old_value` = prior status, `new_value = "STATUS_EXPORTED"`. Already
exported receipts are untouched, so repeating the call returns `0`. Receipts in any other status
are never moved.

```json
{
  "updated": 7
}
```
