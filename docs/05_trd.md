# Kenyalang Ledger — Step 5: Technical Requirements Document (TRD) & System Architecture

---

## 5.1 System Architecture Topology

Kenyalang Ledger is a two-tier application: a React single-page console and one
FastAPI process. There is **no broker, no worker process and no object storage**.
Receipt bytes are written to the local filesystem under `KENYALANG_STORAGE_ROOT`;
metadata lives in PostgreSQL or SQLite through SQLAlchemy 2.x. Uploads return
immediately and the pipeline runs afterwards in the same process via a FastAPI
`BackgroundTask`.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                               CLIENT TIER                                │
│  React 18 + Vite 8 | TypeScript 6 | Tailwind 3 | Zustand 5 | react-router │
└─────────────────────────────────────┬────────────────────────────────────┘
                                      │ REST over HTTP (multipart uploads & JSON)
                                      │ X-Accountant-Id demo header
                                      ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        API PROCESS (single Uvicorn)                      │
│  FastAPI 0.115+ | Uvicorn | Pydantic 2 | SQLAlchemy 2.x                  │
│  • Demo accountant header       • Per-client tenancy guard (404)         │
│  • Magic-byte sniff + size caps • Security headers + CORS allowlist      │
│                                                                          │
│  BackgroundTasks ──► OCR ──► LLM extraction ──► reconciler (in-process)  │
│  (same process; no queue, no separate worker)                            │
└───────────────┬──────────────────────────────────────┬───────────────────┘
                │                                      │
       Local filesystem                       SQLAlchemy session
                │                                      │
                ▼                                      ▼
┌──────────────────────────────┐          ┌──────────────────────────────┐
│   RECEIPT BLOB DIRECTORY     │          │       PERSISTENCE TIER       │
│  <KENYALANG_STORAGE_ROOT>/   │          │  PostgreSQL 15 or SQLite     │
│  tenants/{client_id}/        │          │  (SQLAlchemy 2.x; schema     │
│    {receipt_id}{ext}         │          │  created by init_db, no      │
│  (JPEG/PNG/HEIC/PDF bytes)   │          │  migration framework)        │
└──────────────────────────────┘          └──────────────────────────────┘
```

There is no migration framework. `app.models.init_db()` runs
`Base.metadata.create_all` and then a small set of **additive guards**: create the
`pgcrypto` extension and add `ERR_EXTRACTION` to the `receipt_status` enum on
Postgres, and add `receipt_line_items.expense_category` where it is missing (via
`ALTER TABLE … IF NOT EXISTS` on Postgres and a `PRAGMA table_info` probe on
SQLite). The guards widen an older database without destroying rows; they never
drop or rewrite a column. Startup retries `init_db` five times so a Postgres
container that is still booting does not crash the API.

The API is mounted at `/api` for client management/health and `/api/v1` for
receipts, exports and the dashboard.

### 5.1.1 Demo limits vs. a production deployment

| Concern | What this demo actually does | What production would need |
| --- | --- | --- |
| Pipeline execution | `BackgroundTasks` inside the API process | Durable queue, separate worker pool, idempotent retries |
| Crash recovery | Best effort: a task lost to a restart leaves the row in a `PROCESSING_*` state; the accountant re-uploads | Leases/heartbeats, dead-letter handling, automatic re-drive |
| Schema changes | `create_all` + additive guards | Versioned migration tooling with rollback |
| Receipt storage | Local disk (a Docker volume in Compose) | Encrypted object storage, versioning, lifecycle rules |
| Abuse control | Per-file 15 MiB, per-batch 50 MiB / 50 files, MIME sniff | Per-account throttling, quotas, WAF |
| Identity | Forgeable `X-Accountant-Id` header, accepted only when `KENYALANG_ENV` is `local` or `test` | Identity provider, sessions, RBAC, access audit |
| Observability | Uvicorn logs plus `/api/health/live` and `/api/health/ready` | Structured logs, metrics, tracing, alerting |
| Encryption at rest | None beyond whatever the host volume provides | Disk/volume encryption and key management |

### 5.1.2 Asynchronous upload contract

`POST /api/v1/clients/{client_id}/receipts/upload` is a multipart batch endpoint
(one repeated `files` field per file, max 50).

1. **Preflight is atomic.** Every file's size and magic bytes are checked before
   anything is written. A rejected batch leaves no receipt rows and no blobs on disk.
2. **The response is `202 Accepted`.** Each accepted file appears as
   `{id, filename, status}` with `status = PROCESSING_OCR`, alongside a `batch_id`
   and `total_received`. A new upload never receives a terminal verdict in the
   response itself.
3. **Processing happens after the response.** Only once the placeholder rows are
   committed are the `process_receipt_background` tasks queued. The worker advances
   `PROCESSING_OCR → PROCESSING_LLM → VALIDATING_MATH`, committing each transition
   in its own short session, and finishes in a terminal status.
4. **Terminal statuses** are `STATUS_NEEDS_REVIEW`, `STATUS_AUTO_VERIFIED` (both
   produced by the reconciler) and the error states `ERR_FILE_CORRUPT`,
   `ERR_UNREADABLE`, `ERR_TIMEOUT` and `ERR_EXTRACTION`. Errors carry a
   `processing_error` string so a bad file is auditable instead of silently stuck.
5. **Restart loss is possible and accepted.** With no broker there is no
   redelivery: a receipt whose task was lost stays in a `PROCESSING_*` state and the
   console shows it as in-flight. Re-uploading the file is the recovery path.
6. **Duplicate uploads dedupe.** A file whose sanitized filename and byte size match
   an existing receipt in the same workspace returns that receipt's `id` and current
   status instead of writing a second blob or scheduling a second run. The same
   identity check applies within one batch. This is an identity heuristic on
   (name, size), not a content hash.
7. **Terminal rows are never overwritten.** The worker writes only while the row is
   still in a `PROCESSING_*` state, so a duplicate or retried task cannot clobber an
   accountant's review.

---

## 5.2 Image Preprocessing & Spatial OCR Engine

Thermal paper fades, curls and suffers from uneven shadows when photographed in a
Kuching coffee shop or workshop. The backend normalizes each accepted container
before text recognition.

### 5.2.1 OpenCV Image Preprocessing Pipeline (`pipeline/preprocessor.py`)

Supported containers are JPEG and PNG (OpenCV), HEIC/HEIF (`pillow-heif`) and PDF
(PyMuPDF, page 1 only). Constants:

```python
MAX_DIMENSION = 2048          # longest edge after downscale
MAX_IMAGE_PIXELS = 40_000_000 # decompression-bomb ceiling, checked before decode
PDF_DPI = 200                 # PDF rasterization scale
CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_GRID_SIZE = (8, 8)
BILATERAL_D, BILATERAL_SIGMA_COLOR, BILATERAL_SIGMA_SPACE = 9, 75, 75
```

1. **Decode & pixel guard.** Raster dimensions are read from the header
   (`_probe_size`) and checked against `MAX_IMAGE_PIXELS` *before* a
   full-resolution buffer is allocated; an oversized or malformed payload becomes
   `ImageDecodeError` → `ERR_FILE_CORRUPT`. PDFs are rejected when encrypted or when
   they contain no pages.
2. **EXIF auto-orientation.** Orientation tag `0x0112` is read with `piexif` and
   orientations 2–8 are applied explicitly, including mirrored cases. OpenCV's own
   EXIF rotation is disabled at decode time (`IMREAD_IGNORE_ORIENTATION`) so the
   transform happens exactly once.
3. **Dimension scaling.** If `max(width, height) > MAX_DIMENSION`, the image is
   downscaled with `INTER_AREA`, preserving aspect ratio. Small images are never
   upscaled.
4. **Contrast-Limited Adaptive Histogram Equalization (CLAHE):** convert to LAB,
   apply CLAHE to the L-channel only (the A/B channels carry paper tint that must
   survive), convert back.
5. **Bilateral filtering:** `cv2.bilateralFilter(img, d=9, sigmaColor=75,
   sigmaSpace=75)` runs last, so denoising cannot smooth away the contrast CLAHE
   just recovered.

The chain is `auto_orient_image → resize_if_needed → apply_clahe_contrast →
denoise`. There is no explicit deskew stage; the extractor estimates document slant
when grouping tokens into rows (§5.3.2).

### 5.2.2 Spatial OCR Token Extraction (`pipeline/ocr_engine.py`)

* **Engine:** EasyOCR 1.7 with PyTorch, CPU by default. `EASYOCR_USE_GPU` forces GPU
  on/off; otherwise CUDA availability is probed. The reader is cached process-wide
  because it loads roughly 100 MB of weights.
* **Languages:** English (`en`) and Malay (`ms`).
* **Confidence floor:** tokens below `0.10` are dropped (`KENYALANG_OCR_MIN_CONFIDENCE`
  overrides). Faint handwriting is why the floor is low.
* **Spatial Coordinate Normalization:** EasyOCR's four-point pixel polygons are
  flattened to an axis-aligned box, divided by the image dimensions, and clamped to
  `0.0–1.0`:

$$\bar{x}_{\min} = \frac{\min(x)}{W}, \quad \bar{y}_{\min} = \frac{\min(y)}{H}, \quad \bar{x}_{\max} = \frac{\max(x)}{W}, \quad \bar{y}_{\max} = \frac{\max(y)}{H}$$

* **Entrypoints:** `process_receipt_image(payload, mime_type=None)` selects the
  PDF/HEIC decoder through `preprocess_receipt(payload, mime_type, max_dim=2048)`
  and otherwise runs `preprocess_image`. `tokens_to_dicts` serializes the list for the
  JSON/JSONB `receipts.ocr_raw_tokens` column.
* **Intermediate Representation (OCR Document Contract):**

```python
class OCRToken(BaseModel):
    text: str
    confidence: float  # 0.0 to 1.0, rounded to 4 decimals
    bbox: list[float]  # [x_min, y_min, x_max, y_max], normalized to 0.0-1.0
    line_num: int      # index in EasyOCR's raw readtext output
```

`line_num` is the index in EasyOCR's raw result list, assigned before the confidence
filter, so it is not necessarily contiguous.

---

## 5.3 LLM Structured Entity Extraction Contract

Raw OCR output is spatial text tokens. The LLM turns those tokens into a structured
accounting model, parsing mixed Bahasa Melayu, English and Manglish terms.

### 5.3.1 System Prompt Architecture

The prompt below is the literal `SYSTEM_PROMPT` in `pipeline/extractor.py`:

```text
You are the core extraction engine for Kenyalang Ledger, an expert Malaysian accounting parser.
Your task is to extract structured invoice/receipt data from raw OCR tokens.

CRITICAL LOCAL KNOWLEDGE:
1. Malaysian Business Reg:
   - BRN: 9-12 digits, or old format (e.g., 123456-X or 202001012345).
   - SST Number: Often formatted as [Letter][Digits]-[Digits]-[Digits] (e.g., W10-1808-32000018).
2. Currencies:
   - All amounts are in Malaysian Ringgit (MYR). Remove 'RM', 'MYR', '$' prefixes.
3. Dialect & Terminology (Sarawak/Manglish):
   - F&B: "kopi c peng", "teh o", "mee kolok", "laksa", "nasi goreng".
   - Hardware/Workshop: "minyak hitam", "upah pasang", "pvc pipe", "bateri", "tayar".
   - Labels: "Jumlah" = Total, "Cukai" = Tax, "Tarikh" = Date, "Resit Rasmi" = Official Receipt.
4. Line Item Extraction:
   - Identify line items strictly: description, quantity (default 1 if absent), unit_price, line_total.
   - Do not hallucinate items. If line items are unreadable due to fading, extract grand_total and set line_items to empty array.

Return ONLY a validated JSON payload adhering to the requested schema.
```

### 5.3.2 Extraction Strategy

* **Structured output framework:** `instructor` wrapping the OpenAI client in
  **`Mode.MD_JSON`**, with the JSON Schema appended to the user turn. Function
  calling (`Mode.TOOLS`) is deliberately avoided: instructor sends `tool_choice`
  as an object, which OpenAI-compatible relays reject outright
  (`cannot unmarshal object into Go struct field ... of type string`), and
  MD_JSON is the only mode that survives both a first-party endpoint and a
  relay. The client is built once per process with
  `timeout=15.0` and `max_retries=0` (the SDK retry loop is disabled so it cannot
  stack on instructor's); instructor itself retries schema validation twice
  (`max_retries=2`). No Anthropic or Ollama provider is wired in. `OPENAI_BASE_URL`,
  when set, is normalized to end in `/v1`.
* **Flat extraction schema:** the model returns `ExtractedReceiptData` — flat header
  scalars plus a `line_items` array. `grand_total` is `Optional[Decimal]`, so a
  receipt that does not state a total parses as `null` and the reconciler flags it
  rather than the model inventing one. Monetary fields reject NaN/Infinity at the
  Pydantic boundary.
* **Deterministic provenance:** after the model returns, `attach_provenance` matches
  each populated header value to the OCR token that carries it (numeric, date-format
  or text match, with a similarity fallback for single tokens). No supporting token
  means confidence `0.0` and no bbox — never a model-reported confidence. Line-item
  confidence is the model's own score when it is below `1.0`; otherwise it is the
  minimum of the description and amount token confidences, and `0.0` if either is
  missing.
* **Description / price separation:** the prompt states that `description` is the
  item name only, and `_strip_price_from_description` enforces it deterministically
  afterwards. The rule is deliberately narrow: only a *trailing* amount that equals
  the line's own `line_total` or `unit_price` is removed, so `PAKU 2 INCI 4.50`
  becomes `PAKU 2 INCI` while `PAKU 2 INCI`, `SHELL TELLUS 4L` and `BATERI 12V` keep
  their numbers. Stripping every trailing number would rename products; stripping
  nothing leaves a price in the audit trail and in the CSV description column. A
  description consisting only of the price is left alone rather than blanked, because
  an empty description hides the row from the reviewer.
* **Token pruning:** tokens are grouped into visual rows using an estimated document
  slant (searched over slopes ±0.20, about ±11°), ordered top-to-bottom and joined
  left-to-right within a row. Each row is sent with its normalized `y` as a spatial
  hint: `[0.412] KIM GUAN HARDWARE RM 105.47`.
* **Configuration (environment variables):**

  | Variable | Purpose | Default |
  | --- | --- | --- |
  | `OPENAI_API_KEY` | Required; extraction raises without it. | — |
  | `OPENAI_BASE_URL` | Optional OpenAI-compatible endpoint; `/v1` appended if absent. | SDK default |
  | `KENYALANG_LLM_MODEL` | Extraction model. | `gpt-4o-mini` |
  | `KENYALANG_STORAGE_ROOT` | Receipt blob root (§5.6). | `storage` |
  | `DATABASE_URL` | SQLAlchemy URL. | `sqlite:///./kenyalang.db` |
  | `KENYALANG_OCR_MIN_CONFIDENCE` | EasyOCR token confidence floor. | `0.10` |
  | `EASYOCR_USE_GPU` | Force EasyOCR GPU on/off. | auto-detect |

  The API key is read from the **backend process environment only** and is never
  exposed to the client bundle (§5.6). The SDK call carries a 15-second timeout, so a
  slow provider ends the receipt at `ERR_TIMEOUT`; there is no separate wall-clock
  budget for OCR.

---

## 5.4 Deterministic Rule-Based Math & Verification Engine

Before writing to the database, a pure Python service (`services/reconciler.py`)
runs deterministic audits. It performs no I/O, accepts an optional `today`
(defaulting to the local date) and never calls the LLM. Every flag string it emits is
persisted verbatim into `receipts.validation_flags` and rendered by the review
console, so the names are part of the API surface.

The audit consumes a `ParsedReceiptSchema`: the flat extraction payload plus
`fields`, a list of per-field `ExtractedField` provenance entries attached by
`extractor.attach_provenance`. Each populated header value is matched back to the
OCR token that carries it; when no token supports a value, the field is recorded
with confidence `0.0` and no bbox. This is **fail closed**: an unsupported critical
field cannot pass the confidence gate, so it always routes to a human. A line item
requires both its description and its amount in the OCR. Its confidence is the
minimum of the supporting OCR confidences, and `0.0` if either is missing.

```python
# services/reconciler.py
MATH_TOLERANCE: Decimal = Decimal("0.02")  # rounding slack on the arithmetic identity
CONFIDENCE_THRESHOLD: float = 0.80        # below this, a human confirms the field
MAX_RECEIPT_AGE_DAYS: int = 365
CRITICAL_FIELDS: tuple[str, ...] = ("merchant_name", "invoice_date", "grand_total")
_SST_TOKEN_RE = re.compile(r"[A-Z]\d+-\d+-\d+")
SST_REGISTRATION_RE = re.compile(r"^[A-Z]\d{2}-\d{4}-\d{8}$")

def extract_sst_number(value: str | None) -> str | None:
    """First well-formed SST number in the field, upper-cased; None otherwise.

    A receipt prints the SST ID beside the BRN ("No. Pendaftaran (BRN) /
    SST ID"), so extraction stores the concatenation. Both the audit and the
    MyInvois export canonicalise through this helper instead of demanding the
    whole field match the registration shape.
    """
    if not value:
        return None
    match = _SST_TOKEN_RE.search(value.strip().upper())
    return match.group(0) if match else None

class ReconcilerService:
    @staticmethod
    def audit_receipt(data: ParsedReceiptSchema, today: date | None = None) -> AuditResult:
        flags: list[str] = []

        # 1. Mandatory fields (grand_total is nullable, so a faded receipt still parses)
        if not data.merchant_name or len(data.merchant_name.strip()) < 2:
            flags.append("MISSING_MERCHANT_NAME")
        if not data.invoice_date:
            flags.append("MISSING_DATE")
        if data.grand_total is None or data.grand_total <= 0:
            flags.append("INVALID_GRAND_TOTAL")

        # 2. Date sanity: never in the future, never out of period
        if data.invoice_date:
            reference = today or date.today()
            if data.invoice_date > reference:
                flags.append("DATE_IN_FUTURE")
            elif (reference - data.invoice_date).days > MAX_RECEIPT_AGE_DAYS:
                flags.append("DATE_EXCEEDS_1_YEAR")

        # 3. Arithmetic reconciliation, tax-basis aware (see below):
        #    inclusive -> sum(line_total)              + rounding == grand_total
        #    exclusive -> sum(line_total) + tax_amount + rounding == grand_total
        discrepancy = ReconcilerService._math_discrepancy(data)
        if discrepancy is None:
            if not data.line_items and data.subtotal is None:
                flags.append("MISSING_SUBTOTAL")
        elif discrepancy > MATH_TOLERANCE:      # raw Decimal, compared before rounding
            flags.append(f"MATH_MISMATCH_DELTA_{discrepancy:.2f}")

        # 3b. SST-registered merchant that charged no tax (documented review heuristic)
        if not data.tax_amount and ReconcilerService._is_sst_registered(data):
            flags.append("MISSING_SST_ON_REGISTERED_MERCHANT")

        # 3c. An SST number was printed but does not fit the registration shape.
        # Structural damage only: the format carries no check digit, so a
        # plausible digit substitution (1808 -> 7808) still passes and is left
        # to the confidence gate.
        sst_number = extract_sst_number(data.merchant_sst)
        if sst_number is not None and not SST_REGISTRATION_RE.match(sst_number):
            flags.append("SST_FORMAT_INVALID")

        # 4. Confidence gate: the least-trusted audited field bounds the record
        low_confidence = [
            f.name for f in data.get_fields() if f.confidence < CONFIDENCE_THRESHOLD
        ]
        if low_confidence:
            flags.append(f"LOW_CONFIDENCE_{'_'.join(low_confidence)}")

        # 5. Fail closed when a critical value or its provenance entry is missing
        provenance = {f.name for f in data.fields}
        unsupported = [
            name for name in CRITICAL_FIELDS
            if name in provenance and _is_unsupported(data, name)
        ]
        missing = [name for name in CRITICAL_FIELDS if name not in provenance]
        if unsupported or missing:
            flags.append(
                f"MISSING_CRITICAL_EVIDENCE_{'_'.join([*unsupported, *missing])}"
            )

        status = (
            ReceiptStatus.STATUS_NEEDS_REVIEW
            if flags
            else ReceiptStatus.STATUS_AUTO_VERIFIED
        )
        return AuditResult(
            status=status,
            flags=flags,
            math_discrepancy=discrepancy or Decimal("0.00"),
            overall_confidence=ReconcilerService._overall_confidence(data),
        )
```

**Tax basis (`amount_basis`).** Whether a receipt's printed line totals already
contain the tax is not universal: Malaysian retail till receipts print GST-inclusive
line amounts, while trade invoices print them tax-exclusive. Treating the basis as
fixed double-counts tax on the retail case — a receipt whose lines sum to RM 7.42
with GST 0.42 and a total of 7.42 was reported as a 42-cent mismatch, exactly equal
to the tax.

`ExtractedReceiptData.amount_basis` carries the answer (`INCLUSIVE` or `EXCLUSIVE`),
the extraction prompt reports it, and `receipts.amount_basis` persists it. Free-text
labels are canonicalised by `normalize_amount_basis` (`"Tax Inclusive"`,
`"GST-INCLUSIVE"` and friends); an unrecognised label becomes `NULL` so the
reconciler falls back to inference instead of trusting a value it cannot interpret.
The column is nullable: rows written before the basis existed keep `NULL`.

**Printed rounding line (`rounding`).** Malaysian tills round the payable amount
to the nearest 5 sen and print the adjustment on its own line (`ROUNDING -0.04`,
`PEMBUNDARAN 0.03`). It is neither tax nor a discount, so without a field of its own
it went *into* `grand_total` only — making a correctly printed receipt report a
discrepancy exactly equal to the rounding, on a screen whose only remedy is to edit
a number that is already right. `rounding` is a signed nullable money column
(`receipts.rounding`) with its own prompt rule, and it joins the arithmetic
identity: `Σ lines + tax + rounding == grand_total` (exclusive) or
`Σ lines + rounding == grand_total` (inclusive). `NULL` means the receipt prints no
rounding line and contributes zero, so every existing receipt keeps its previous
result. The tolerance was **not** widened to hide these deltas: RM 0.02 of slack is
for printed drift, and a RM 0.04 rounding line is a fact about the receipt, not
noise.

`ReconcilerService.resolve_amount_basis` returns the explicit basis when present.
Otherwise it infers: an exclusive receipt satisfies `Σ lines + tax == grand_total`
and an inclusive one satisfies `Σ lines == grand_total`. Exclusive is tested first,
so a receipt with no tax — where both identities hold — keeps the pre-basis
behaviour, and a receipt satisfying neither is treated as exclusive so it reports
the same delta it always did.

**Reconciliation source of truth.** `_math_discrepancy` returns
`abs(expected - grand_total)` as an exact `Decimal`, or `None` when there is no
`grand_total`. `expected` is the sum of `line_total` when line items exist, plus
`tax_amount` only when the basis is `EXCLUSIVE`, plus `rounding` when present. With no line items it falls back to
the printed `subtotal` plus tax — a printed subtotal is the tax-exclusive figure on
the layouts this app targets — and otherwise the result is `None`. The flag decision
compares that raw value against `MATH_TOLERANCE` **before** any rounding; only the
stored `math_discrepancy` is quantized by the database column. `tax_amount` is
coerced to `Decimal("0.00")` when absent. Flag text is formatted from the `Decimal`
itself (`:.2f`), not via `float()`. The `0.02` slack absorbs printed rounding drift,
not binary float error.

**Exports normalise to tax-exclusive.** UBL requires every
`InvoiceLine/LineExtensionAmount` to be tax-exclusive and the header
`LegalMonetaryTotal/LineExtensionAmount` to equal their sum. On an inclusive receipt
the printed line totals cannot be copied straight through, so
`receipt_line_amounts` allocates the tax back out of each line by largest remainder
and rebuilds the header from the resulting net amounts. The CSV follows the same
split: `UnitPrice` is the net figure, `TaxAmount` the allocated tax, and
`TotalAmount` what the line actually cost — so a RM 7.42 receipt exports as
7.00 + 0.42 = 7.42 rather than 7.84.

A missing `grand_total` yields `INVALID_GRAND_TOTAL` and can also yield
`MISSING_SUBTOTAL` when there are no line items and no printed subtotal, since both
checks see the same absence. A non-positive total with a printed subtotal is flagged
once, by `INVALID_GRAND_TOTAL`.

**SST review heuristic (not a legal rule).** When `tax_amount` is absent/zero and
`merchant_sst` contains an SST number — the field is upper-cased and searched for
`[A-Z]\d+-\d+-\d+`, e.g. `W10-1808-32000018`, including when the BRN is stored alongside it
(`"200401032489 / Y24-1808-31015655"`) — the audit raises
`MISSING_SST_ON_REGISTERED_MERCHANT` for a human to check. The same helper canonicalises the
number the MyInvois export ships under `schemeID: "SST"`. This is triage for the review console;
it does not assert that every SST registrant must charge tax on every receipt (exempt supplies,
zero-rated items and non-taxable turnover exist). `merchant_sst` is the dedicated SST field;
there is no combined `brn_tin` column or alias.

A printed SST number that does not fit the registered shape (`SST_REGISTRATION_RE`,
`^[A-Z]\d{2}-\d{4}-\d{8}$`) raises `SST_FORMAT_INVALID`. That catches structural
damage — a dropped group, a letter where a digit belongs — and nothing more: the
format has no check digit, so a plausible substitution such as `W10-1808-…` read as
`W10-7808-…` is well-formed and passes. Such a misread is caught, if at all, by the
confidence gate (`LOW_CONFIDENCE_merchant_sst`), never by this flag. Do not read
`SST_FORMAT_INVALID`'s absence as evidence that a printed ID was read correctly.

**Confidence gate and critical fields.** `_overall_confidence` returns `0.0` when any
critical field is absent from provenance or holds `None`/`""`; otherwise it is the
minimum confidence across every audited field (header provenance followed by line
items), rounded to two decimals, and `0.0` when there are no fields at all. Missing
entries or values block auto-verification and raise
`MISSING_CRITICAL_EVIDENCE_{fields}`; unsupported OCR evidence is recorded with
confidence `0.0` and additionally raises `LOW_CONFIDENCE_{field}`.

---

## 5.5 Dual-Format Export Architecture (`services/export_engine.py`)

Kenyalang Ledger produces two outputs. Both are **pure reads**: generating or
downloading either file changes no receipt status.

### 1. Accounting CSV — purchase journal (AutoCount & SQL Account import)

`GET /api/v1/clients/{client_id}/exports/accounting-csv?month=YYYY-MM` returns
`Kenyalang_PurJournal_{YYYYMM|all}.csv` with `Content-Type: text/csv; charset=utf-8`.
Columns, in order:

| # | Column | Notes |
| --- | --- | --- |
| 1 | `DocDate` | `DD/MM/YYYY`; falls back to `created_at` when `invoice_date` is null |
| 2 | `DocNo` | `invoice_number`, else `REC-{first 8 chars of the UUID, upper-cased}` |
| 3 | `SupplierCode` | `SUPP-{first 10 alphanumerics of BRN}`, else of the name, else `SUPP-CASH` |
| 4 | `SupplierName` | `merchant_name`, else `Cash Supplier` |
| 5 | `Description` | Line description, else `General Item` |
| 6 | `ItemCode` | `ITEM-{line_index + 1}`, zero-padded to two digits |
| 7 | `Qty` | Trailing-zero-trimmed decimal, e.g. `1`, `2.5` |
| 8 | `UnitPrice` | Two decimals |
| 9 | `TaxCode` | `SST-6` when tax > 0, else `NONE` (a fixed label, not a computed rate) |
| 10 | `TaxAmount` | Tax allocated to this line, two decimals |
| 11 | `TotalAmount` | `line_total + allocated tax`, two decimals |

Tax is allocated in **integer cents**: `allocate_tax_cents` gives each line its
proportional floor and distributes the leftover cents one at a time to the largest
remainders, ties broken by line order. The allocated amounts therefore sum exactly to
the receipt's tax. A receipt with no line items is emitted as a single summary row
(`General Purchase`, qty `1`) that uses the receipt subtotal, tax and total.

A printed till-rounding line becomes its own row (`Rounding adjustment`, item code
`ITEM-RND`, qty `0`, tax code `NONE`, signed `TotalAmount`), so the batch posts what
the buyer actually paid. Without it the line rows summed to the pre-rounding figure
and the journal disagreed with the receipt by exactly the rounding amount — a
RM 0.04 error introduced by the export itself. No row is emitted when the receipt
prints no rounding line.

Every text cell passes through `_csv_text`, which prefixes an apostrophe when the
value starts with `=`, `+`, `-`, `@`, tab or carriage return, neutralising
spreadsheet formula injection.

### 2. MyInvois-shaped JSON — a draft envelope, never submitted

`GET /api/v1/clients/{client_id}/exports/myinvois-json?month=YYYY-MM` returns
`Kenyalang_MyInvois_{YYYYMM|all}.json`. It is a **draft document envelope** shaped
after `dataset/official_lhdn_sample/1.1-Invoice-MultiLineItem-Sample.json`. It is
**not validated against the LHDN schema and is never submitted** to MyInvois: there
is no signing, no TIN mapping, no submission client and no acknowledgement tracking.

Mapped shape:

* Root namespaces `_D`, `_A`, `_B`, and an `Invoice` **array** (one entry per
  receipt).
* `ID`, `IssueDate` (`YYYY-MM-DD`), `IssueTime` (`created_at` as `HH:MM:SSZ`).
* `InvoiceTypeCode` = `01` with `listVersionID` = `1.1`; `DocumentCurrencyCode` and
  `TaxCurrencyCode` = `MYR`.
* `AccountingSupplierParty`: `PartyName` and `PartyLegalEntity` from the merchant
  name, and `PartyIdentification` with `BRN` and/or `SST` scheme IDs when present
  (fallback `{"_": "NA", "schemeID": "BRN"}`). There is no TIN field.
* `LegalMonetaryTotal` (`LineExtensionAmount`, `TaxExclusiveAmount`,
  `TaxInclusiveAmount`, `AllowanceTotalAmount`, `ChargeTotalAmount`,
  `PayableRoundingAmount`, `PayableAmount`) and `TaxTotal` (category `01`, scheme
  `OTH` / `UN/ECE 5153`). `PayableRoundingAmount` carries the receipt's own printed
  rounding line (signed, `0.0` when absent); it used to be a hardcoded zero, which
  left the document unable to explain why its own totals differed by four sen.
* `InvoiceLine` per line item: `ID`, `InvoicedQuantity` (unit code `C62`),
  `LineExtensionAmount`, `TaxTotal`, `Item.Description`, `Price`,
  `ItemPriceExtension`. Per-line tax uses the same integer-cent allocation as the CSV.
  A receipt with no line items emits one line for the merchant total.

Amounts in this envelope are emitted as JSON numbers via `float`/`round(..., 2)`; the
CSV and the API's receipt payloads use exact decimal strings. The envelope is a
convenience export, not a money-of-record format.

### 3. Marking receipts as exported

`POST /api/v1/clients/{client_id}/exports/mark?month=YYYY-MM` is the **only** state
change: it moves `STATUS_VERIFIED` and `STATUS_AUTO_VERIFIED` receipts in the period
to `STATUS_EXPORTED`, stamps `exported_at`, writes one `receipt_audit_log` row per
receipt, and returns `{updated: n}`. It is idempotent — a repeat call returns
`updated: 0`. Already exported receipts remain in later downloads, which is why both
downloads read rows in `VERIFIED`, `AUTO_VERIFIED` or `EXPORTED`.

---

## 5.6 Security Model & Data Handling

This is a demo build. It makes **no PDPA compliance claim**: there is no consent
capture, no data-subject request workflow, no retention/purge job, no encryption at
rest, and no access log for reading a receipt image beyond the standard request log.
Receipt images and PDFs live as plain files on the local disk path described below; a
production deployment would need encryption, retention limits and an access-audit
trail before handling real client data.

1. **Local-disk storage isolation.** Uploaded bytes are written under
   `<KENYALANG_STORAGE_ROOT>/tenants/{client_id}/{receipt_id}{ext}`
   (`core/storage.py`). The client-supplied filename is never used to build the path
   — only a sanitized extension (`^\.[a-z0-9]{1,8}$`, else `.bin`) is — so a crafted
   upload name cannot escape the tenant directory. Each write goes to a randomly
   suffixed `.part` temp file and is atomically renamed into place. Blobs written by
   a batch that fails to commit are deleted.
2. **Path-escape rejection on read.** `load_receipt_file` resolves the stored
   relative path against the resolved storage root and raises `ValueError` unless the
   candidate is inside it, so a corrupted or tampered `storage_path` cannot become an
   arbitrary file read. The image route turns that into `404`.
3. **Tenancy guard.** Every receipt, export and dashboard route calls
   `get_active_owned_client`, which filters on
   `clients.accountant_id == <caller>` **and** `is_active`; client management uses
   the plainer `get_owned_client` so a soft-deleted workspace can be reactivated.
   A workspace or receipt
   belonging to another accountant is indistinguishable from a missing one: the API
   returns `404`, never `403`, and never leaks existence. `_receipt_or_404` folds the
   `client_id` predicate into the receipt lookup for the same reason.
4. **Demo authentication is not authentication.** `X-Accountant-Id` is a forgeable
   header. It is honoured only when `KENYALANG_ENV` is `local` or `test`; any other
   or missing value returns `401`. `create_app()` additionally refuses to start when
   `KENYALANG_ENV=production`. Do not expose this service on a public network.
5. **File ingestion guards.**
   * Maximum 15 MiB per file, 50 MiB and 50 files per batch; violations are `413`.
   * **Magic-byte verification** (the extension is ignored): JPEG (`FF D8 FF`), PNG
     (`89 50 4E 47 0D 0A 1A 0A`), PDF (`%PDF-`), and HEIC detected structurally as an
     ISO-BMFF `ftyp` box with a `hei*` brand. Unrecognized containers are `415`;
     empty files are `422`.
   * Decode limits (§5.2.1): 40 MP ceiling checked before allocation; PDFs render
     page 1 only; encrypted PDFs are rejected.
6. **Spreadsheet formula-injection escaping.** Every CSV text cell beginning with
   `=`, `+`, `-`, `@`, tab or carriage return is prefixed with `'` (§5.5).
7. **No key leakage.** `OPENAI_API_KEY` and friends are read only from the backend
   process environment and are never injected into the client bundle (`VITE_`
   variables are the only ones Vite exposes). All inference runs through the backend.
8. **Transport hardening.** Every response carries `X-Content-Type-Options: nosniff`,
   `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`,
   `Permissions-Policy: geolocation=(), camera=(), microphone=()`, and
   `Content-Security-Policy: frame-ancestors 'none';`. CORS is an explicit origin
   allowlist from `KENYALANG_CORS_ORIGINS`.

### 5.6.1 Review Console Frontend Architecture (`frontend/`)

The accountant review console is a keyboard-driven single-page application built with
react-router 6, lazy-loaded route chunks and a shared authenticated layout:
`RootLayout` runs `AccountantGate` inside a `Suspense` boundary, and each page
renders its own `AppShell` chrome.

1. **Core framework:** React 18.3, TypeScript 6, Vite 8 (`tsc -b` with `noUnusedLocals`, `noUnusedParameters`).
2. **Styling & tokens:** Tailwind CSS 3.4 with the brand teal palette defined in
   `tailwind.config.js`, dense 40px image rows (`dense-row`), and
   `.font-mono-numbers` tabular numerals for financial figures.
3. **Image viewport:** the receipt is **not** a public URL. `ReceiptCanvas` issues
   `fetch(receiptImageUrl(clientId, receiptId), { headers: { 'X-Accountant-Id': … } })`,
   converts the response blob to an object URL (`URL.createObjectURL`) and renders it
   in an `<img>`; the URL is revoked on cleanup/unmount. Inbox thumbnails use the same
   authenticated-blob pattern. Pan/drag and wheel zoom are applied as a GPU
   `translate3d(...) scale(...)` transform on a DOM node; the provenance boxes are an
   SVG overlay in a 0–1000 viewBox, not a rasterized HTML canvas.
4. **Flat receipt schema:** the review form is bound to flat header fields
   (`merchant_name`, `merchant_brn`, `merchant_sst`, `invoice_date`,
   `invoice_number`, `subtotal`, `tax_amount`, `grand_total`) plus a `line_items[]`
   array, mirroring the API's `ReceiptDetailResponse`. Confidence and bboxes arrive
   separately in a `fields[]` provenance list and are drawn as overlays; they are not
   nested per-field wrappers.
5. **State management (Zustand 5):**
   * `sessionStore.ts`: the acting accountant UUID in `localStorage`
     (`kenyalang.accountant_id`), sent as `X-Accountant-Id` on every API call.
   * `receiptStore.ts`: client selection (`kenyalang.current_client_id`), inbox
     pagination and status filter (`ALL`, `NEEDS_REVIEW`, `VERIFIED`, `EXPORTED`,
     `REJECTED`), active receipt, and draft form state. Drafts persist to
     `localStorage` under `kenyalang.draft.{receipt_id}` and are compared against a
     server-truth baseline to compute dirtiness; a dirty draft blocks navigation
     (`useBlocker`) and page unload (`useBeforeUnload`).
6. **Keyboard shortcuts (`lib/reviewShortcuts.ts`):** one pure resolver maps a keydown
   plus context (`typing`, `focusedLine`) to an action — `Escape` blurs a focused
   field or asks to reject (the page confirms first), `⌘/Ctrl+Enter` saves and
   advances, `Alt+A` adds a line, `Alt+Backspace` deletes the focused line. Save, add
   and delete are suppressed while typing. Zoom keys (`[`, `]`, `R`) and the
   confirm/reject strip are handled in `ReviewPage`.
7. **Client-side math audit (`lib/audit.ts`):** exact `BigInt` cents; checks
   $\Delta = \left| \sum \text{line\_total} + \text{tax} - \text{grand\_total} \right| \le 2$ cents
   and also validates `line_total` against `qty × unit_price`. `MathBanner.tsx`
   re-renders the verdict on every keystroke.
8. **Wire formatting:** monetary amounts in API payloads are decimal strings (e.g.
   `"105.47"`) so the BigInt cents parser never sees a JSON float.
9. **Dev proxy:** `vite.config.ts` proxies `/api` to `VITE_API_PROXY` or
   `http://127.0.0.1:8000`; Vitest runs in jsdom with `src/test/setup.ts`.

---

## 5.7 Tech Stack Matrix

| Layer | Technology | Version | Notes |
| --- | --- | --- | --- |
| **Frontend** | React + Vite + TypeScript | 18.3 / 8.3 / 6.0 | Typed receipt state; route-level lazy chunks. |
| **Routing** | react-router-dom | 6.30 | `createBrowserRouter` with a shared authenticated layout. |
| **Styling** | Tailwind CSS | 3.4 | Utility-first tokens; no runtime CSS-in-JS. |
| **State management** | Zustand | 5.0 | Session, workspace and review-draft stores. |
| **Client math** | TypeScript `BigInt` | — | Cents arithmetic in `lib/audit.ts`, no float money. |
| **Backend API** | Python + FastAPI + Uvicorn | 3.11 / 0.115+ / 0.30+ | Single ASGI process; Pydantic 2 serialization. |
| **Validation** | Pydantic | 2.x (2.11+) | Flat extraction schema, Decimal/date coercion, bbox validation. |
| **ORM & database** | SQLAlchemy + PostgreSQL / SQLite | 2.0+ / 15 / 3.x | Portable GUID/JSONB/UTCDateTime column types; `init_db` bootstrap. |
| **Image preprocessing** | OpenCV (headless) | 4.9+ | EXIF orientation, CLAHE on LAB-L, bilateral filter, INTER_AREA resize. |
| **Container decoding** | PyMuPDF + pillow-heif + Pillow | 1.24+ / 0.18+ / 10.3+ | PDF page 1 at 200 DPI, HEIC decode, header pixel probing. |
| **OCR engine** | EasyOCR (PyTorch) | 1.7+ | English + Malay, normalized polygon boxes, cached reader. |
| **LLM interface** | `instructor` + OpenAI SDK | 1.7+ / 1.60+ | `Mode.MD_JSON` + schema in the user turn, Pydantic validation retries, 15 s timeout. |
| **Async processing** | FastAPI `BackgroundTasks` | — | In-process, no broker or worker. |
| **Testing** | pytest / Vitest + Testing Library | 8.2+ / 5.0 + 16.3 | 311 backend tests, 56 frontend tests. |
| **Containerization** | Docker + Docker Compose | — | Postgres 15 + Python 3.11-slim API with a storage volume. |
