# Kenyalang Ledger — Step 5: Technical Requirements Document (TRD) & System Architecture

---

## 5.1 System Architecture Topology

Kenyalang Ledger is architected as an asynchronous, event-driven decoupled application. The core compute pipeline isolates compute-heavy computer vision (OpenCV/EasyOCR) and external API calls (LLMs) from the low-latency web layer.

```
┌────────────────────────────────────────────────────────────────────────┐
│                              CLIENT TIER                               │
│  React 18 + Vite | Tailwind CSS | HTML5 Canvas (Pan/Zoom) | Zustand    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTPS / REST (Multipart uploads & JSON)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                           API GATEWAY / APP                            │
│  FastAPI (Python 3.11+) | Uvicorn ASGI | Pydantic v2 Validation        │
│  • Auth / Session Guard        • Multi-tenant Tenant Isolation         │
│  • File Type Magic Byte Check  • Rate Limiting & Pre-signed URL issuer │
└──────────────┬──────────────────────────────────────────┬──────────────┘
               │                                          │
       Async Dispatch                             Sync Metadata / CRUD
               │                                          │
               ▼                                          ▼
┌──────────────────────────────┐          ┌──────────────────────────────┐
│     PROCESSING PIPELINE      │          │       PERSISTENCE TIER       │
│  1. OpenCV Image Normalize   │          │  PostgreSQL 15 / SQLite*     │
│  2. EasyOCR Token Extractor  │          │  (SQLAlchemy 2.0 / Alembic)  │
│  3. LLM Parsing (Instructor) │          │                              │
│  4. Deterministic Math Audit │          │  Blob Storage (MinIO / S3 /  │
│                              │          │  Local Persistent Volume)    │
└──────────────────────────────┘          └──────────────────────────────┘
(*SQLite supported for standalone single-tenant development; PostgreSQL for production multi-tenant.)
```

> **Architecture intent vs. current implementation.** The decoupled async topology above is the
> target design. The shipping ingest path (§6.3.1) runs the pipeline **inline and synchronously**
> inside the upload request — no broker or worker process is configured — and returns each file's
> *terminal* status in the `202` response instead of an intermediate `PROCESSING_*` placeholder.
> The stage boundaries (`preprocessor` → `ocr_engine` → `extractor` → `reconciler`) are already
> separate modules so a future worker can move them behind a queue without changing the contracts.

---

## 5.2 Image Preprocessing & Spatial OCR Engine

Thermal paper fades, curls, and suffers from uneven shadows when snapped via mobile cameras in Kuching coffee shops or workshops. The backend must normalize images before text recognition.

### 5.2.1 OpenCV Image Preprocessing Pipeline (`pipeline/preprocessor.py`)

1. **EXIF Auto-Orientation:** Inspect EXIF tag `0x0112` and rotate matrix ($90^\circ, 180^\circ, 270^\circ$) to correct smartphone camera orientation.
2. **Dimension Scaling:** If $\max(\text{width}, \text{height}) > 2048\text{px}$, resize down while preserving aspect ratio (reduces EasyOCR memory overhead by ~60%).
3. **Contrast-Limited Adaptive Histogram Equalization (CLAHE):**
    * Convert image to LAB color space.
    * Apply CLAHE (`clipLimit=2.0`, `tileGridSize=(8,8)`) to the L-channel to recover faded ink on thermal receipts without blowing out the paper background.
    * Convert back to BGR.
4. **Bilateral Filtering & Denoising:** Smooth background paper texture while preserving sharp character edge gradients (`cv2.bilateralFilter(img, d=9, sigmaColor=75, sigmaSpace=75)`).

### 5.2.2 Spatial OCR Token Extraction (`pipeline/ocr_engine.py`)

* **Engine:** EasyOCR with PyTorch CPU/CUDA backend.
* **Languages:** English (`en`) and Malay (`ms`).
* **Spatial Coordinate Normalization:** Raw pixel bounding boxes $[(x_1, y_1), (x_2, y_2), (x_3, y_3), (x_4, y_4)]$ are converted into normalized relative coordinates ($0.000$ to $1.000$):

$$\bar{x}_{\min} = \frac{\min(x)}{W}, \quad \bar{y}_{\min} = \frac{\min(y)}{H}, \quad \bar{x}_{\max} = \frac{\max(x)}{W}, \quad \bar{y}_{\max} = \frac{\max(y)}{H}$$

* **Intermediate Representation (OCR Document Contract):**

```python
class OCRToken(BaseModel):
    text: str
    confidence: float # 0.00 to 1.00
    bbox: list[float] # [x_min, y_min, x_max, y_max] normalized
    line_num: int
```

---

## 5.3 LLM Structured Entity Extraction Contract

Raw OCR outputs spatial text tokens. The LLM translates these tokens into a structured accounting model, parsing mixed Bahasa Melayu, English, and Manglish terms.

### 5.3.1 System Prompt Architecture

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

* **Structured Output Framework:** `instructor` wrapping the OpenAI client in **`Mode.TOOLS`**
  (function calling) for zero markdown wrapping and schema adherence. Anthropic/Ollama are not wired
  in the shipping code.
* **Flat extraction schema:** the LLM is handed `ExtractedReceiptData` — flat scalars plus a
  `line_items` array — not a nested per-field `ExtractedField<T>` envelope. A `grand_total` that the
  receipt does not state is parsed as `null` rather than forced to a number, so the reconciler can
  flag it; per-field confidence and bounding boxes are attached deterministically *after* the model
  returns (`attach_provenance`, §5.4), so confidence is measured from the OCR engine rather than
  self-reported by the model.
* **Token Pruning:** Sort OCR tokens vertically top-to-bottom, left-to-right (`y_min`, then `x_min`)
  and emit them as a compact text block for the LLM.
* **Configuration (environment variables):**

  | Variable | Purpose | Default |
  | --- | --- | --- |
  | `OPENAI_API_KEY` | Required; the client refuses to start LLM extraction without it. | — |
  | `OPENAI_BASE_URL` | Optional OpenAI-compatible endpoint override. | SDK default |
  | `KENYALANG_LLM_MODEL` | Extraction model. | `gpt-4o-mini` |
  | `KENYALANG_STORAGE_ROOT` | Receipt blob root (§5.6.1). | `storage` |
  | `DATABASE_URL` | SQLAlchemy URL (§6.1). | `sqlite:///./kenyalang.db` |

  The API key is read from the **backend process environment only** — never exposed to the client
  bundle (§5.6.3). Extraction is exercised against an OpenAI-compatible endpoint; no live accuracy
  claim is made here. The SDK call itself carries a 15-second timeout; there is no hard wall-clock
  guarantee on the OCR stage.


---

## 5.4 Deterministic Rule-Based Math & Verification Engine

Before writing to the database, a pure Python validation service (`services/reconciler.py`) executes
deterministic audits. It is I/O-free, accepts an optional `today` (defaults to the local date), and never calls
the LLM. Every flag string it emits is persisted verbatim into `receipts.validation_flags` and
rendered by the review console, so the names are part of the API surface.

The audit consumes a `ParsedReceiptSchema` (§6.2): the flat extraction payload plus `fields`, a list
of per-field `ExtractedField` provenance entries attached by `extractor.attach_provenance`. Each
populated header value is matched back to the OCR token that carries it (numeric, date or text
match); when no token supports a value — or the evidence is ambiguous — the field is recorded with
confidence `0.0` and no bbox. This is **fail closed**: an unsupported critical field cannot pass the
confidence gate, so it always routes to a human. A line item requires both its complete description
and amount on the same geometrical row. Its confidence is the minimum of the supporting OCR
confidence and model-cited confidence. Header amounts require a matching labeled row, such as
`Subtotal`, `Cukai`, or `Jumlah`/`Total`; an unrelated occurrence of the same amount is not evidence.

```python
# services/reconciler.py
MATH_TOLERANCE = Decimal("0.02")   # exact Decimal slack on the arithmetic identity
CONFIDENCE_THRESHOLD = 0.80        # below this, a human confirms the field
MAX_RECEIPT_AGE_DAYS = 365
CRITICAL_FIELDS = ("merchant_name", "invoice_date", "grand_total")  # must have OCR evidence

class ReconcilerService:
    @staticmethod
    def audit_receipt(data: ParsedReceiptSchema, today: date | None = None) -> AuditResult:
        flags = []

        # 1. Mandatory fields (grand_total is nullable so a faded receipt still
        #    parses; the audit is what flags it)
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

        # 3. Arithmetic reconciliation: sum(line_total) + tax == grand_total
        discrepancy = ReconcilerService._math_discrepancy(data)
        if discrepancy is None:
            if not data.line_items and data.subtotal is None:
                flags.append("MISSING_SUBTOTAL")
        elif discrepancy > MATH_TOLERANCE:     # raw Decimal compared before any rounding
            flags.append(f"MATH_MISMATCH_DELTA_{discrepancy:.2f}")

        # 3b. SST-registered merchant that charged no tax (documented review heuristic)
        if not data.tax_amount and ReconcilerService._is_sst_registered(data):
            flags.append("MISSING_SST_ON_REGISTERED_MERCHANT")

        # 4. Confidence gate: the least-trusted audited field bounds the record
        low_confidence = [f.name for f in data.get_fields() if f.confidence < CONFIDENCE_THRESHOLD]
        if low_confidence:
            flags.append(f"LOW_CONFIDENCE_{'_'.join(low_confidence)}")

        # 4b. Fail closed when a critical value or provenance entry is missing.
        provenance = {field.name for field in data.fields}
        missing_critical = [
            name for name in CRITICAL_FIELDS
            if name not in provenance or getattr(data, name) in (None, "", Decimal("0"))
        ]
        if missing_critical:
            flags.append(f"MISSING_CRITICAL_EVIDENCE_{'_'.join(missing_critical)}")

        status = ReceiptStatus.STATUS_NEEDS_REVIEW if flags else ReceiptStatus.STATUS_AUTO_VERIFIED
        return AuditResult(
            status=status,
            flags=flags,
            math_discrepancy=discrepancy or Decimal("0.00"),
            overall_confidence=ReconcilerService._overall_confidence(data),
        )
```

**Reconciliation source of truth.** `_math_discrepancy` computes `abs((expected + tax) -
grand_total)` as exact `Decimal` and compares it against `MATH_TOLERANCE` **before** any rounding
(the stored `math_discrepancy` may be quantized to `0.01`, but the flag decision uses the raw
value). `expected` is the sum of `line_total` when line items exist; otherwise it falls back to the
printed `subtotal`; otherwise there is nothing to reconcile and it returns `None` (→
`MISSING_SUBTOTAL`). A missing or non-positive `grand_total` is flagged `INVALID_GRAND_TOTAL`
independently, not reported as a subtotal problem. `tax_amount` is coerced to `Decimal("0.00")` when
absent. Flag text is formatted from the `Decimal` itself (`:.2f`), not via `float()`. The `0.02`
slack absorbs printed-rounding drift, not binary float error.

**SST review heuristic (not a legal rule).** When `tax_amount` is absent and the receipt's
`merchant_sst` matches the SST format `^[A-Z]\d+-\d+-\d+$` (e.g. `W10-1808-32000018`), the audit
raises `MISSING_SST_ON_REGISTERED_MERCHANT` for a human to check. This is a documented triage
heuristic for the review console — it does **not** assert that every SST registrant must charge tax
on every receipt (exempt supplies, zero-rated items and non-taxable turnover exist).
`merchant_sst` is the dedicated SST field; there is no combined `brn_tin` stored column or alias.

**Confidence gate and critical fields.** `_overall_confidence` is the minimum confidence across every
audited field (header provenance followed by line items), rounded to two decimals. Missing critical
values or provenance floor it at `0.0`. The critical header fields — `merchant_name`, `invoice_date`,
`grand_total` — must carry provenance. Missing values or entries block auto-verification and raise
`MISSING_CRITICAL_EVIDENCE_{field}`; unsupported OCR evidence is recorded with confidence `0.0`
and raises `LOW_CONFIDENCE_{field}`. `math_discrepancy` remains exact in the audit result; the database
stores two decimal places. Flag text uses Decimal money formatting, not binary float conversion.


---

## 5.5 Dual-Format Export Architecture (`services/export_engine.py`)

Kenyalang Ledger exports data into two distinct operational targets:

### 1. Accounting CSV / Excel (AutoCount & SQL Account Import)

* Formats records into Purchase Journal Batch specifications:
* Columns: `Date`, `Supplier_Name`, `Invoice_No`, `Account_Code`, `Item_Description`, `Qty`, `Unit_Price`, `Tax_Code (SST)`, `Total_Amount`.

### 2. LHDN MyInvois v1.1 JSON Payload

* Direct transformation from internal DB model to the official LHDN SDK sample schema (`1.1-Invoice-MultiLineItem-Sample.json`).
* Mandatory mapped fields:
    * `Invoice.IssueDate` & `Invoice.IssueTime`
    * `Invoice.InvoiceTypeCode` (Code `01` for standard invoice, `02` for consolidated receipt)
    * `Invoice.SupplierParty.PartyIdentification` (TIN / BRN)
    * `Invoice.InvoiceLine` array: `ID`, `InvoicedQuantity`, `LineExtensionAmount`, `TaxTotal`

---

## 5.6 Security & PDPA Compliance Architecture

1. **Storage Isolation:** Original uploaded bytes are written to tenant-scoped storage under
   `<KENYALANG_STORAGE_ROOT>/tenants/{client_id}/{receipt_id}{ext}` (`core/storage.py`). The
   client-supplied filename is never used to build the path — only a sanitized extension is — so a
   crafted upload name cannot escape the tenant directory. Each write goes to a temp file and is
   atomically renamed into place, so a crash mid-write cannot leave a truncated blob that later looks
   URLs (15 minutes), which is *architecture intent* — the review console streams images directly
   through the authenticated backend endpoint `GET /api/v1/clients/{client_id}/receipts/{receipt_id}/image`
   (`core/storage.py`), validating workspace ownership on every request.
2. **File Ingestion Guards:**
    * Maximum file size: 15 MiB per file; maximum 50 files per batch.
    * **Magic-byte verification** (extension ignored): JPEG (`FF D8 FF`), PNG, PDF (`%PDF-`), and
      HEIC detected structurally as an ISO-BMFF `ftyp` box with a `hei*` brand. Unrecognized
      containers are rejected `415`. See §6.3.1 for the supported-format decision.
3. **No PII Leaks:** API keys (`OPENAI_API_KEY`, etc.) are read only from the backend process
   environment and must never be injected into the client bundle (`VITE_`). All inference routes
   through internal backend endpoints.


### 5.6.1 Review Console Frontend Architecture (`frontend/`)

The accountant review console is implemented as a high-density, keyboard-driven Single Page Application (SPA) in `frontend/`:

1. **Core Framework:** React 18.3 + TypeScript (strict) + Vite 8.
2. **Styling & Tokens:** Tailwind CSS 3.4 using the custom Slate & Sarawak Hornbill Teal palette defined in `docs/04_ui_specs.md` (§4.1), dense 40px rows, and `.font-mono-numbers` tabular numerals for financial figures.
3. **State Management:**
   * `sessionStore.ts` (Zustand 5): stores authenticated accountant UUID (`kenyalang.accountant_id` in `localStorage`), passed as `X-Accountant-Id` header on all API calls.
   * `receiptStore.ts` (Zustand 5): workspace client selection, inbox pagination & status filters (`ALL`, `NEEDS_REVIEW`, `VERIFIED`, `EXPORTED`), active review receipt, and draft form state. Form drafts are persisted to `localStorage` under `kenyalang.draft.{receipt_id}` so dirty inputs survive browser refreshes without data loss.
4. **Client-Side Math Audit (`lib/audit.ts`):** Exact BigInt cents arithmetic; verifies $\Delta = \left| \sum \text{line\_total} + \text{tax} - \text{grand\_total} \right| \le 0.02$, providing real-time visual feedback (`MathBanner.tsx`) on every keystroke.
5. **Wire Formatting:** All monetary amounts on the wire are serialized as decimal strings (e.g. `"105.47"`) to eliminate JSON floating-point inaccuracies.
6. **Dev Proxy:** `vite.config.ts` proxies `/api` requests to `http://127.0.0.1:8000`.

---

## 5.7 Tech Stack Matrix

| Layer | Technology | Version | Justification |
| --- | --- | --- | --- |
| **Frontend** | React + Vite + TypeScript | 18.x / 5.x | Ultra-fast build times, strict typing for receipt state interfaces. |
| **Styling** | Tailwind CSS | 3.4+ | Utility-first, strict anti-slop color tokens, zero runtime CSS bloat. |
| **State Management** | Zustand | 4.5+ | Minimal footprint (<2kB) for active receipt state & dirty form cache. |
| **Backend API** | FastAPI | 0.110+ | High throughput async Python, native Pydantic v2 serialization. |
| **Image Preprocessing** | OpenCV (headless) | 4.9+ | Industrial CLAHE contrast recovery, deskewing, auto-rotation. |
| **OCR Engine** | EasyOCR | 1.7+ | PyTorch-backed, native support for Malay and English characters. |
| **LLM Interface** | `instructor` / Native SDK | Latest | Strict JSON schema extraction, automatic Pydantic retries on error. |
| **Database** | PostgreSQL / SQLite | 15+ / 3.x | Relational consistency, JSONB support for OCR bounding box store. |
| **Containerization** | Docker + Docker Compose | 24+ | Single-command local spin-up for development and demo environments. |
