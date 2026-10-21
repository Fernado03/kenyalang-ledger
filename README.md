# Kenyalang Ledger

> **Receipt digitizer and accounting review workspace for Malaysian micro-SMEs and freelance accountants.**
> Upload phone photos of thermal receipts, review OCR-extracted fields side by side with the scan, and export a purchase journal CSV or a MyInvois-shaped draft JSON.

This repository is a **portfolio demo**, not a production service. It runs locally with a
forged demo identity, stores files on the local disk, and processes uploads in-process.
Sections below state exactly where those demo boundaries are.

---

## Overview

Malaysian micro-SMEs — hardware shops, workshops, and kopitiams — hand their accountants
shoeboxes of thermal receipts. Kenyalang Ledger digitizes that flow:

- **Bounded async ingestion:** JPEG, PNG, HEIC, and PDF receipts upload in batches and are
  processed in the background while the inbox shows their progress.
- **Spatial OCR:** EasyOCR tokens keep normalized bounding boxes, which the review console
  overlays on the scan so a field can be traced back to the pixels it came from.
- **LLM structured extraction:** an OpenAI-compatible chat model turns OCR text into the
  receipt header and line items.
- **Deterministic reconciliation:** line totals plus tax are compared against the grand total
  with a two-cent tolerance; low-confidence or unreconciled receipts route to human review.
- **Fixed expense taxonomy:** line items are classified into `F&B`, `HARDWARE`, `WORKSHOP`,
  `RETAIL`, or `OTHER` by keyword, with `OTHER` as the fallback.
- **Export:** an AutoCount / SQL Account purchase journal CSV, and a MyInvois-shaped JSON
  **draft** that has not been validated against the LHDN schema and is never submitted.
- **Dashboard:** monthly spend, top five suppliers, and category breakdown over verified
  receipts.

```mermaid
flowchart LR
    A[Upload: JPEG / PNG / HEIC / PDF] --> B[Stored blob<br/>local disk]
    B --> C[Preprocess<br/>EXIF, CLAHE, 40 MP cap, PDF page 1 @ 200 DPI]
    C --> D[EasyOCR<br/>normalized bboxes]
    D --> E[LLM extraction<br/>header + line items]
    E --> F[Reconciler<br/>math, confidence, date, SST]
    F --> G[(SQLAlchemy<br/>PostgreSQL or SQLite)]
    G --> H[Review console<br/>React + canvas]
    H --> I1[Accounting CSV]
    H --> I2[MyInvois-shaped draft JSON]
```

---

## Demo boundaries

| Area | What this repository does | What a production system would need |
|---|---|---|
| Identity | `X-Accountant-Id` UUID header, accepted only when `KENYALANG_ENV` is `local` or `test` | A real IdP, signed sessions, per-user authorization |
| Processing | FastAPI `BackgroundTasks` in the API process | A durable queue and worker with retries and a dead-letter path |
| Schema evolution | `create_all` plus additive guards for the two fields added after launch | Alembic migrations and a reviewed migration history |
| Storage | Local filesystem under `KENYALANG_STORAGE_ROOT` | Object storage with encryption and short-lived signed URLs |
| MyInvois | A JSON envelope shaped like the LHDN sample | Schema validation and submission through LHDN's API |
| Compliance | No claim of PDPA, WCAG, or LHDN certification | Legal and accessibility audits, data-processing agreements |

The `X-Accountant-Id` header is a **forgeable demo identity, not authentication**: any caller
who knows a UUID can act as that accountant. `KENYALANG_ENV` gates the header to `local` and
`test`, and setting `KENYALANG_ENV=production` makes application startup raise
`RuntimeError("Kenyalang Ledger demo auth must not run in production")`. Never expose this
service on a public network.

---

## Architecture & tech stack

| Layer | Technologies | Notes |
|---|---|---|
| **Frontend** | React 18, TypeScript 6, Vite 8, Tailwind CSS 3, Zustand 5, React Router 6 | High-density keyboard UI, canvas zoom/pan, object-URL image display |
| **Backend API** | Python 3.11, FastAPI 0.115, Pydantic 2.11, SQLAlchemy 2.0, Uvicorn | Routers for clients, receipts, exports, and dashboard |
| **CV & OCR** | OpenCV (headless), EasyOCR, Pillow, Pillow-HEIF, PyMuPDF | HEIC through `pillow-heif`, PDF page 1 rendered at 200 DPI |
| **LLM extraction** | OpenAI SDK against any OpenAI-compatible base URL | Default model `gpt-4o-mini`, overridable with `KENYALANG_LLM_MODEL` |
| **Persistence** | PostgreSQL 15 or SQLite | Portable column types (`GUID`, `JSONBType`, `UTCDateTime`) |
| **Testing** | pytest, Vitest, Testing Library, ruff, ESLint | 229 backend tests, 37 frontend tests |
| **Containerization** | Docker, Docker Compose | Non-root backend image; PostgreSQL 15 + API Compose stack |

---

## Repository structure

```text
kenyalang-ledger/
├── backend/
│   ├── app/
│   │   ├── api/            # clients + health, receipts, exports, dashboard routers
│   │   ├── core/           # engine/session, tenancy guards, storage, demo auth
│   │   ├── models/         # Client, Receipt, ReceiptLineItem, ReceiptAuditLog
│   │   ├── pipeline/       # preprocessor, EasyOCR engine, LLM extractor
│   │   ├── schemas/        # Pydantic v2 request/response contracts
│   │   ├── services/       # reconciler, classifier, export engine
│   │   └── main.py         # app factory, lifespan, CORS, router mounting
│   ├── tests/              # 229 pytest tests
│   ├── sql/                # pgcrypto extension for the Compose database
│   ├── Dockerfile
│   ├── pyproject.toml      # package metadata and pytest config
│   ├── requirements.txt    # runtime dependencies
│   ├── requirements-dev.txt# runtime + pytest, httpx, ruff
│   └── constraints.txt     # OpenCV-headless pin (numpy 2.x ABI)
├── frontend/
│   ├── src/
│   │   ├── api/            # typed fetch wrapper
│   │   ├── components/     # AppShell, canvas, line editor, banners, pills, gate
│   │   ├── lib/            # money/date formatting, math audit, shortcut resolution
│   │   ├── pages/          # Clients, Inbox, Review, Exports, Dashboard, Upload
│   │   ├── store/          # Zustand session and receipt stores
│   │   └── test/           # Vitest setup
│   ├── package.json
│   └── vite.config.ts      # Vite dev server with /api proxy + Vitest config
├── dataset/                # SROIE/FUNSD/CORU references and LHDN sample JSON
├── docs/                   # PRD, appflow, UI specs, TRD, schema/API, RTM
└── docker-compose.yml      # PostgreSQL 15 + backend
```

---

## Prerequisites

- **Python:** 3.11+
- **Node.js:** 20+ with npm 10+
- **Docker & Docker Compose** (optional, for the PostgreSQL stack)
- **OpenAI-compatible API key** (required for LLM extraction; without it uploads end in
  `ERR_EXTRACTION` rather than fabricating fields)

---

## Quick start (local development)

### 1. Backend

```bash
cd backend

python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Runtime dependencies, with the OpenCV constraint that avoids the numpy 2.x ABI clash
pip install -c constraints.txt -r requirements.txt

# Required: demo auth is disabled unless the environment is local or test
# Linux/macOS:
export KENYALANG_ENV=local
# Windows (PowerShell):
$env:KENYALANG_ENV="local"

# Required for extraction. Nothing loads .env for you, so export the values
# (or source the file: `set -a && . ./.env && set +a`) before starting uvicorn.
export OPENAI_API_KEY="your-api-key"
# Optional: any OpenAI-compatible relay, plus the model it serves.
export OPENAI_BASE_URL="https://api.example.com/v1"
export KENYALANG_LLM_MODEL="deepseek-v4.1-flash-1017"

uvicorn app.main:app --reload --port 8000
```

Check the API:

```bash
curl http://127.0.0.1:8000/api/health/live
curl http://127.0.0.1:8000/api/health/ready
```

`/api/health/live` returns `200` whenever the process is up. `/api/health/ready` runs
`SELECT 1` and returns `503 {"detail": "database unavailable"}` when the database does not
answer.

Database default: when `DATABASE_URL` is unset the backend uses local SQLite at
`backend/kenyalang.db`. For PostgreSQL:

```bash
export DATABASE_URL=postgresql+psycopg2://kenyalang:kenyalang@localhost:5432/kenyalang
```

Schema bootstrap is `create_all` plus additive guards in `init_db()`; there are no migration
files. Pointing the backend at an older demo database adds the `ERR_EXTRACTION` enum value and
the `expense_category` column in place.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to `http://127.0.0.1:8000`; override with
`VITE_API_PROXY`. Setting `VITE_API_BASE_URL` makes the client call a different origin
directly.

On the gate, enter any UUID (for example `00000000-0000-4000-8000-000000000001`) as the demo
accountant id. It is stored in the session store and sent as `X-Accountant-Id`.

---

## Running with Docker Compose

```bash
docker compose up -d
docker compose logs -f backend
```

- Backend API: `http://localhost:8000` (Compose sets `KENYALANG_ENV=local`)
- PostgreSQL: `localhost:5432`, user/password/database `kenyalang`
- Receipt blobs: named volume `kenyalang_storage` mounted at `/data/storage`

The backend image copies only `app/`, runs as the non-root `app` user, and health-checks
`/api/health/ready`.

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `KENYALANG_ENV` | *(unset)* | Must be `local` or `test` for demo auth to work; unset or any other value returns `401`, and `production` refuses startup |
| `DATABASE_URL` | `sqlite:///./kenyalang.db` | SQLAlchemy URL; PostgreSQL 15 is the Compose default |
| `KENYALANG_STORAGE_ROOT` | `storage` | Root directory for tenant receipt blobs |
| `KENYALANG_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000` | Comma-separated allowed browser origins |
| `OPENAI_API_KEY` | *(empty)* | Provider key; absent means extraction ends in `ERR_EXTRACTION` |
| `OPENAI_BASE_URL` | *(SDK default)* | OpenAI-compatible endpoint (OpenRouter, Azure, vLLM) |
| `KENYALANG_LLM_MODEL` | `gpt-4o-mini` | Chat model used for extraction |
| `EASYOCR_USE_GPU` | *(auto-detect)* | `1`/`true` forces CUDA, `0`/`false` forces CPU, unset checks `torch.cuda` |
| `KENYALANG_OCR_MIN_CONFIDENCE` | `0.10` | Drops OCR tokens below this confidence |
| `VITE_API_PROXY` | `http://127.0.0.1:8000` | Vite dev-server proxy target |
| `VITE_API_BASE_URL` | *(same origin)* | Absolute API base for the frontend build |

Management of these values is your responsibility; `.env.example` contains placeholders only,
and the backend does not autoload a dotenv file. Export the variables in the shell or pass
them through Compose.

---

## Upload contract and limits

`POST /api/v1/clients/{client_id}/receipts/upload` accepts a multipart batch and returns
`202 Accepted` immediately, with each new receipt in `PROCESSING_OCR`. Work continues in a
FastAPI background task and settles into `STATUS_AUTO_VERIFIED`, `STATUS_NEEDS_REVIEW`, or a
terminal `ERR_*` state.

| Limit | Value | Failure |
|---|---|---|
| Files per batch | 50 | `413` |
| File size | 15 MiB | `413` |
| Batch size | 50 MiB | `413` |
| Decoded image pixels | 40 MP | `ERR_FILE_CORRUPT` after acceptance |
| Accepted formats | JPEG, PNG, HEIC, PDF (magic-byte detection) | `415` |
| Empty file | — | `422` |

Every file passes preflight before any blob is written; a rejected batch leaves no rows or
files behind. A re-upload whose safe filename and byte length match an existing receipt
returns that receipt's id and status instead of storing a second copy.

Processing is in-process and best-effort: **restarting the API strands in-flight rows in a
`PROCESSING_*` state, and there is no retry queue.** A duplicate upload returns the stranded
row. Reset the row or the demo database to recover.

---

## Key API endpoints

All accountant endpoints expect `X-Accountant-Id`. Tenant-scoped routes return `404` for a
missing, foreign, or soft-deleted client.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health/live` | Liveness; no database access |
| `GET` | `/api/health/ready` | Readiness; `SELECT 1`, `503` when unavailable |
| `GET` | `/api/clients` | Client workspaces with `unreviewed_count` / `verified_count` |
| `POST` | `/api/clients` | Create a client workspace |
| `GET/PUT/DELETE` | `/api/clients/{client_id}` | Read, update, soft-delete (`204`) |
| `POST` | `/api/v1/clients/{client_id}/receipts/upload` | Batch upload; `202` + background processing |
| `GET` | `/api/v1/clients/{client_id}/receipts` | Inbox page: `status`, `limit` (max 200), `offset` |
| `GET` | `/api/v1/clients/{client_id}/receipts/{receipt_id}` | Full detail: header, fields, line items, OCR tokens |
| `GET` | `/api/v1/clients/{client_id}/receipts/{receipt_id}/image` | Stored bytes, tenancy-checked |
| `GET` | `/api/v1/clients/{client_id}/receipts/{receipt_id}/audit` | Manual-edit history, newest first |
| `PUT` | `/api/v1/clients/{client_id}/receipts/{receipt_id}` | Update and verify; writes audit rows |
| `POST` | `/api/v1/clients/{client_id}/receipts/{receipt_id}/reject` | Reject with an audit row |
| `GET` | `/api/v1/clients/{client_id}/exports/accounting-csv?month=YYYY-MM` | Purchase journal CSV (read-only) |
| `GET` | `/api/v1/clients/{client_id}/exports/myinvois-json?month=YYYY-MM` | MyInvois-shaped draft JSON (read-only) |
| `POST` | `/api/v1/clients/{client_id}/exports/mark?month=YYYY-MM` | Move verified receipts to `EXPORTED` |
| `GET` | `/api/v1/clients/{client_id}/dashboard/summary?month=YYYY-MM` | Monthly total, top suppliers, categories |

Export downloads never change receipt state. `POST .../exports/mark` is the only transition;
it moves `STATUS_VERIFIED` and `STATUS_AUTO_VERIFIED` receipts to `STATUS_EXPORTED`, writes one
audit row per receipt, and returns `{"updated": n}`. A second call returns `0`.

CSV columns: `DocDate`, `DocNo`, `SupplierCode`, `SupplierName`, `Description`, `ItemCode`,
`Qty`, `UnitPrice`, `TaxCode`, `TaxAmount`, `TotalAmount`. Tax is allocated across lines in
integer cents by largest remainder so the line taxes sum exactly to the receipt tax, and any
text cell beginning with `=`, `+`, `-`, `@`, tab, or carriage return is prefixed with a single
quote to neutralize spreadsheet formula injection.

---

## Expense categories and reconciliation

Line items are classified by keyword into `F&B`, `HARDWARE`, `WORKSHOP`, `RETAIL`, or `OTHER`
(`backend/app/services/classifier.py`). Unknown or blank descriptions fall back to `OTHER`.
The dashboard always returns all five categories, including zeros.

Reconciliation (`backend/app/services/reconciler.py`):

- **Math:** `|sum(line_total) + tax_amount - grand_total| <= RM 0.02`. Missing line items fall
  back to comparing `subtotal + tax`.
- **Confidence:** any critical field below `0.80` routes the receipt to `STATUS_NEEDS_REVIEW`.
- **Date sanity:** invoice dates in the future or older than 365 days are flagged.
- **SST:** an SST-registered merchant with no tax amount is flagged.
- **Critical fields:** `merchant_name`, `invoice_date`, `grand_total`.

Failing any gate produces `STATUS_NEEDS_REVIEW`; passing all gates produces
`STATUS_AUTO_VERIFIED`.

---

## Testing and quality gates

### Backend

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest
ruff check app tests
```

The suite runs 229 tests over auth, tenancy, health, uploads, receipt updates, exports,
dashboard, pipeline formats, and end-to-end export flows. It uses SQLite and a temporary
storage root, so no Docker or network access is required. Tests that would need EasyOCR
weights skip with an explicit reason.

### Frontend

```bash
cd frontend
npm test        # vitest run
npm run lint
npm run build   # tsc -b && vite build
```

37 Vitest tests cover money and date formatting, math auditing, keyboard shortcut resolution,
and the status pill. Testing Library runs in jsdom with globals disabled, so tests import
`describe`/`it`/`expect` from `vitest` explicitly.

### End-to-end

```bash
cd frontend
npx playwright install chromium   # once
npm run test:e2e
```

Playwright drives the real browser against a throwaway stack it starts itself: `backend/seed_e2e.py`
rebuilds `backend/kenyalang-e2e.db` and `backend/storage-e2e/`, then uvicorn serves that database on
`:8010` and Vite serves the frontend on `:5183` with the API proxy pointed at it. The demo database
is never touched. With `reuseExistingServer: false`, every run (including a single spec) starts from
a fresh seed, so the specs that mutate receipts cannot pollute each other. The suite covers the
accountant gate, client workspaces, inbox filtering and stamps, the review console, exports,
dashboard, upload limits, review deep links, and the UI standards (reflow sweep, focus, reduced
motion, WCAG AA contrast, axe WCAG 2.2 AA, security headers). `09-evidence.spec.ts` is excluded from the gate because it writes
platform-dependent PNGs; regenerate the screenshots in `docs/e2e-evidence/` on demand with
`npm run test:e2e:evidence` and see that directory's README for the audit findings.

---

## Dataset & benchmarking references

The `dataset/` directory holds reference material, not a benchmark harness:

- **`official_lhdn_sample/`** — LHDN MyInvois v1.1 sample JSON used as the shape reference for
  the draft export.
- **`sroie/`** — SROIE thermal receipt dataset.
- **`funsd/`** — Key-value layout extraction for noisy forms and chits.
- **`coru/`** — Line-item parsing schema reference.
- **`hand_captured_receipts/`** — Phone-captured receipts with angle, blur, and uneven light.

No accuracy figure in this repository has been measured against these datasets; nothing here
is a published benchmark result. See [`dataset/README.md`](dataset/README.md) for provenance.

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/02_prd.md`](docs/02_prd.md) | Product requirements and acceptance criteria (`REQ-101` – `REQ-110`) |
| [`docs/03_appflow.md`](docs/03_appflow.md) | Screen flow, status machine, error handling |
| [`docs/04_ui_specs.md`](docs/04_ui_specs.md) | Design tokens, screens, keyboard and accessibility behaviour |
| [`docs/05_trd.md`](docs/05_trd.md) | Pipeline, extraction contract, reconciliation, export architecture |
| [`docs/06_schema_api.md`](docs/06_schema_api.md) | Database schema and HTTP contract |
| [`docs/07_rtm.md`](docs/07_rtm.md) | Requirement-to-code-to-test traceability |

---

## License

MIT. See [LICENSE](LICENSE).
