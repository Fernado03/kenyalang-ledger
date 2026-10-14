# Kenyalang Ledger

> **Invoice and receipt digitizer tailored for Malaysian micro-SMEs and freelance accountants.**
> Built to bridge faded thermal receipts, handwritten Kuching chits, and WhatsApp photo dumps with LHDN MyInvois e-invoicing compliance and accounting software exports.

---

## Overview

In Malaysia, the **LHDN MyInvois mandate** requires structured transaction records across business tiers, yet thousands of local hardware stores, automotive workshops, and kopitiams across Sarawak run on cash, thermal paper, and handwritten chits. Micro-SME owners often dump blurry monthly receipt photos into WhatsApp chats with freelance accountants, requiring hours of manual line-item data entry.

**Kenyalang Ledger** provides an end-to-end digitizer and review console:
- **Computer Vision Preprocessing:** Recovers faded thermal receipts using adaptive contrast (CLAHE), EXIF auto-rotation, and bilateral filtering.
- **Localized Spatial Token Extraction:** EasyOCR coupled with Instructor-driven LLM parsing tuned for Malaysian business identifiers (BRN, SST) and local/Manglish terminology (*kopi c peng*, *upah pasang*, *minyak hitam*).
- **Deterministic Math Reconciliation:** Verifies item totals, tax calculations, and grand totals with penny-level precision before human sign-off.
- **Dual Export Engine:** One-click exports to **LHDN MyInvois v1.1 Consolidated JSON** and standard **AutoCount / SQL Account Purchase Journal CSV**.
- **High-Density Review Console:** Split-pane web workspace with pan/zoom receipt canvas, bounding-box highlighting, and keyboard-driven line-item editing.

```mermaid
flowchart LR
    A[Receipt Image / Photo] --> B[OpenCV Normalizer<br/>EXIF, CLAHE, Denoise]
    B --> C[EasyOCR Spatial Tokens<br/>Normalized BBoxes]
    C --> D[Instructor + LLM<br/>Malaysian Lexicon & Schema]
    D --> E[Deterministic Reconciler<br/>Math & SST Audit]
    E --> F[(Database & Blob Storage<br/>PostgreSQL / SQLite)]
    F --> G[Accountant Review Console<br/>React + Canvas Pan/Zoom]
    G --> H1[LHDN MyInvois v1.1 JSON]
    G --> H2[AutoCount / SQL Account CSV]
```

---

## Architecture & Tech Stack

| Layer | Technologies | Details |
|---|---|---|
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS, Zustand | High-density keyboard UI, HTML5 Canvas zoom/pan, client-side session store |
| **Backend API** | FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2.0 | Async ASGI service with multi-tenant workspace isolation (`X-Accountant-Id`) |
| **CV & OCR** | OpenCV (headless), EasyOCR, PyTorch (CPU) | LAB CLAHE contrast enhancement, deskew, normalized bounding boxes |
| **LLM Extraction** | Instructor, OpenAI SDK (`gpt-4o-mini`) | Structured validation, retry logic, Manglish & local Sarawak lexicon parsing |
| **Persistence** | PostgreSQL 15 / SQLite fallback | Portable column types (`GUID`, `JSONBType`, `UTCDateTime`), tenant-scoped storage |
| **Containerization**| Docker, Docker Compose | Minimal Alpine PostgreSQL + Python 3.11 slim backend image |

---

## Repository Structure

```text
kenyalang-ledger/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routes: clients, receipts, exports
│   │   ├── core/           # Database engine, tenancy guards, storage, auth
│   │   ├── models/         # SQLAlchemy ORM models (Client, Receipt, LineItems, Audit)
│   │   ├── pipeline/       # Image preprocessor, EasyOCR engine, LLM extractor
│   │   ├── schemas/        # Pydantic v2 validation contracts
│   │   ├── services/       # Export engine (MyInvois JSON, Accounting CSV), reconciler
│   │   └── main.py         # ASGI app entrypoint and lifecycle
│   ├── tests/              # 130+ test suite (unit, pipeline, API, E2E exports)
│   ├── sql/                # Postgres extensions and migrations
│   ├── Dockerfile          # Multi-stage optimized CPU backend container
│   ├── pyproject.toml      # Build metadata and pytest configuration
│   ├── requirements.txt    # Production dependencies
│   └── constraints.txt     # Pinned OpenCV-headless to prevent ABI conflicts
├── frontend/
│   ├── src/
│   │   ├── api/            # Typed API client wrapper
│   │   ├── components/     # Canvas pan/zoom, line-item editor, math banner, dropzone
│   │   ├── pages/          # Clients, Inbox, Review Console, Exports
│   │   ├── store/          # Zustand receipt & accountant session stores
│   │   └── types/          # TypeScript interfaces for API payloads
│   ├── package.json        # Frontend scripts and dependencies
│   └── vite.config.ts      # Vite dev server with /api proxy
├── dataset/                # Benchmarking catalogs (SROIE, FUNSD, CORU, LHDN samples)
├── docs/                   # Full product specs (PRD, TRD, Schema & APIs, UI specs)
└── docker-compose.yml      # Local orchestration for PostgreSQL + Backend
```

---

## Prerequisites

- **Python:** 3.11+
- **Node.js:** 20+ (with npm 10+)
- **Docker & Docker Compose** (optional, for running with PostgreSQL)
- **OpenAI API Key** (required for the LLM extraction pipeline)

---

## Quick Start (Local Development)

### 1. Backend Setup

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install dependencies with constraints (prevents OpenCV ABI collision)
pip install -c constraints.txt -r requirements.txt

# Set required environment variables
# Windows (PowerShell):
$env:OPENAI_API_KEY="your-openai-api-key"
# Linux/macOS:
export OPENAI_API_KEY="your-openai-api-key"

# Run the FastAPI server
uvicorn app.main:app --reload --port 8000
```

> **Note on Database:** By default, if `DATABASE_URL` is unset, the backend runs seamlessly against local SQLite (`backend/kenyalang.db`). To use PostgreSQL, set:
> `DATABASE_URL=postgresql+psycopg2://kenyalang:kenyalang@localhost:5432/kenyalang`

Check backend health:
```bash
curl http://127.0.0.1:8000/api/health
```

### 2. Frontend Setup

In a separate terminal:

```bash
cd frontend

# Install dependencies
npm install

# Start Vite development server
npm run dev
```

Open `http://localhost:5173` in your browser. The Vite development server automatically proxies all `/api` requests to `http://127.0.0.1:8000`.

---

## Running with Docker Compose

To spin up the containerized backend with PostgreSQL 15:

```bash
# Start PostgreSQL and Backend services
docker compose up -d

# View service logs
docker compose logs -f backend
```

- Backend API: `http://localhost:8000`
- PostgreSQL: `localhost:5432` (`kenyalang` / `kenyalang`)

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./kenyalang.db` | SQLAlchemy database connection string |
| `OPENAI_API_KEY` | *(Required for LLM)* | API key for OpenAI / Instructor extraction |
| `OPENAI_BASE_URL` | `None` | Alternative API base (e.g. OpenRouter, Azure, local vLLM) |
| `KENYALANG_LLM_MODEL` | `gpt-4o-mini` | LLM model for extraction |
| `KENYALANG_READER_GPU` | `0` | Set to `1` or `true` if running EasyOCR with CUDA GPU |
| `KENYALANG_STORAGE_ROOT`| `./data/receipts` | Filesystem root for tenant-scoped receipt blobs |
| `VITE_API_PROXY` | `http://127.0.0.1:8000` | Vite dev proxy target |

---

## Key API Endpoints

All accountant endpoints expect tenant authentication via the `X-Accountant-Id` header (automatically supplied by the frontend session store).

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Healthcheck (database connectivity & version) |
| `GET` | `/api/clients` | List client workspaces for the current accountant |
| `POST` | `/api/clients` | Create a new client workspace (BRN, SST, business name) |
| `POST` | `/api/v1/clients/{client_id}/receipts/upload` | Batch multipart receipt image upload and synchronous pipeline execution |
| `GET` | `/api/v1/clients/{client_id}/receipts` | Paginated inbox of client receipts |
| `GET` | `/api/v1/clients/{client_id}/receipts/{receipt_id}` | Full receipt detail including OCR tokens, bounding boxes, and audit history |
| `GET` | `/api/v1/clients/{client_id}/receipts/{receipt_id}/image` | Stream receipt image file with tenancy validation |
| `PUT` | `/api/v1/clients/{client_id}/receipts/{receipt_id}` | Update, audit-log, and verify receipt line items |
| `GET` | `/api/v1/clients/{client_id}/exports/accounting-csv` | Export AutoCount / SQL Account purchase journal batch CSV |
| `GET` | `/api/v1/clients/{client_id}/exports/myinvois-json` | Export LHDN MyInvois v1.1 compliant JSON format |

---

## Testing & Quality Gates

### Backend Test Suite
The backend contains 130 unit, integration, and E2E export tests covering the image preprocessor, OCR token parser, math reconciler, client workspaces, and export generators:

```bash
cd backend
pytest
```

### Frontend Build & Linting
Type-checking, linting, and production bundling:

```bash
cd frontend
npm run lint
npm run build
```

---

## Dataset & Benchmarking

The `dataset/` directory contains benchmarks and reference schemas used to validate OCR accuracy and regulatory compliance:
- **`official_lhdn_sample/`**: Official LHDN MyInvois v1.1 sample JSON and XML documents for output contract verification.
- **`sroie/`**: SROIE thermal receipt dataset for merchant name, date, and total extraction under faded conditions.
- **`funsd/`**: Key-value layout extraction for noisy forms and chits.
- **`coru/`**: Line-item parsing schema reference from ReceiptSense.
- **`hand_captured_receipts/`**: Phone-captured receipts with angles, blur, and uneven lighting simulating WhatsApp uploads.

For details on dataset provenance, refer to [`dataset/README.md`](dataset/README.md).

---

## License

This project is licensed under the [MIT License](LICENSE).
