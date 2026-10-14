# Kenyalang Ledger — Step 2: Product Requirements Document (PRD)

---

## 2.1 Document Control & Scope

* **Product Name:** Kenyalang Ledger (Invoice & Receipt Digitiser)
* **Version:** PRD v1.0.0
* **Target Platforms:** Responsive Web App (Mobile-first for micro-SME photo uploads; Desktop-optimized for accountant bulk-review consoles)
* **Core Scope:** Multi-channel image ingestion, OCR preprocessing, LLM entity extraction, mathematical validation & confidence scoring, human-in-the-loop review interface, multi-client workspace tenancy, and dual-format export (Accounting CSV + LHDN MyInvois v1.1 JSON).

---

## 2.2 Target User Personas

### Primary Persona: The Freelance Accountant / Audit Clerk ("Karen")

* **Role:** Solo freelance bookkeeper or junior audit clerk at a boutique Kuching firm managing 15–35 SME clients.
* **Current Workflow:** Receives unorganized batches of receipt photos via WhatsApp at month-end; manually keys supplier, date, line items, and totals into Excel or SQL Account.
* **Core Frustrations:**
    * Blurry, angled photos from phone cameras.
    * Thermal receipts faded beyond quick recognition.
    * Typos during manual data entry that lead to reconciliation errors at month-end.

* **Success Metric:** Cuts time spent per client from 4 hours down to under 30 minutes.

### Secondary Persona: The Micro-SME Owner ("Ah Teck")

* **Role:** Owner-operator of a Kuching hardware shop, auto workshop, or eatery (1–5 staff).
* **Current Workflow:** Collects physical paper receipts, fuel chits, and supplier slips in a plastic folder or shoebox.
* **Core Frustrations:**
    * Receipts fade or get lost before tax season.
    * No immediate visibility into true monthly operational spend.
    * Constant nagging from the accountant for missing receipts.

* **Success Metric:** Snaps a photo in 3 seconds, closes the phone, and knows the expense is tracked.

---

## 2.3 Objectives & Key Results (OKRs)

* **Objective 1: Accelerate Extraction Throughput with High Accuracy**
    * **KR 1.1:** Achieve $\ge 85\%$ field-level extraction accuracy on standard printed tax invoices and $\ge 70\%$ on thermal/handwritten chits before human verification.
    * **KR 1.2:** Reduce average human review time to $\le 10$ seconds per receipt via keyboard-first split-screen UI.
    * **KR 1.3:** Keep end-to-end processing latency (upload $\rightarrow$ OCR $\rightarrow$ LLM parsing $\rightarrow$ ready for review) under 8 seconds.

* **Objective 2: Enforce Regulatory and Downstream Interoperability**
    * **KR 2.1:** Ensure $100\%$ validation pass rate against LHDN MyInvois v1.1 JSON schema for all mandatory export fields.
    * **KR 2.2:** Produce 1-click batch CSV exports compatible with AutoCount and SQL Account journal entry imports.

---

## 2.4 Functional Requirements Catalog

| Req ID | Feature Name | User Story | Priority | Detailed Acceptance Criteria |
| --- | --- | --- | --- | --- |
| **`REQ-101`** | **Multi-Source Image Ingestion** | As a user, I want to upload receipts via mobile camera or drag-and-drop batches on desktop so that ingestion fits my workflow. | **Must Have** | **Given** an image file (`.jpg`, `.jpeg`, `.png`, `.heic`, `.pdf`) $\le 15\text{MB}$, **When** uploaded, **Then** validate file type, auto-orient/rotate using EXIF data, store original in object storage, and dispatch an asynchronous OCR job. |
| **`REQ-102`** | **OCR & Bounding Box Extraction** | As the system, I need raw text and spatial coordinates from receipts to feed downstream parsing. | **Must Have** | **Given** an ingested image, **When** processed by the OCR engine (EasyOCR/OpenCV), **Then** output normalized text tokens alongside normalized 2D bounding box coordinates `[x_min, y_min, x_max, y_max]`. |
| **`REQ-103`** | **Structured Entity Extraction (LLM)** | As an accountant, I want raw receipt text parsed into standard accounting fields automatically. | **Must Have** | **Given** OCR text tokens, **When** processed by the extraction model, **Then** return structured JSON matching schema: `merchant_name`, `brn_tin`, `date`, `invoice_number`, `line_items: [{desc, qty, unit_price, line_total}]`, `subtotal`, `sst_tax_amount`, `grand_total`. |
| **`REQ-104`** | **Confidence Scoring & Reconciliation** | As the system, I must flag ambiguous fields and calculation mismatches to prevent dirty data entry. | **Must Have** | **Given** parsed entities, **When** evaluating correctness, **Then** calculate field-level confidence ($0.00 - 1.00$) AND verify: $\sum(\text{line\_total}) + \text{sst} == \text{grand\_total}$. If discrepancy > RM 0.02 or any field confidence $< 0.80$, mark receipt as `STATUS_NEEDS_REVIEW`. |
| **`REQ-105`** | **Human-in-the-Loop Review Console** | As an accountant, I want a split-screen interface showing the receipt photo next to editable fields so I can correct data in seconds. | **Must Have** | **Given** a flagged receipt, **When** opened in GUI, **Then** show receipt on left (with pan/zoom) and form on right. Highlight low-confidence fields in amber/red. Support Tab/Enter navigation. Pressing `Cmd+Enter` / `Ctrl+Enter` marks as `STATUS_VERIFIED`. |
| **`REQ-106`** | **Multi-Client Account Console** | As a freelance accountant, I want to switch between different SME client workspaces so I can organize books separately. | **Must Have** | **Given** an authenticated accountant profile, **When** selecting a client from the workspace dropdown, **Then** isolate all receipts, suppliers, and exports strictly to that client's tenant partition. |
| **`REQ-107`** | **Supplier Spend Dashboard** | As an SME owner, I want to see monthly total expenditure grouped by supplier so I know where cash is going. | **Should Have** | **Given** verified receipts in a billing period, **When** loading `/dashboard`, **Then** display total monthly burn, top 5 suppliers by spend, and categorized expense breakdown. |
| **`REQ-108`** | **Dual Export Engine (CSV & MyInvois JSON)** | As an accountant, I need verified records in standard accounting formats and LHDN schema. | **Must Have** | **Given** verified receipts, **When** clicking "Export", **Then** generate: (1) Standard CSV/Excel formatted for AutoCount/SQL Account import, and (2) Validated LHDN MyInvois v1.1 JSON matching `1.1-Invoice-MultiLineItem-Sample.json`. |
| **`REQ-109`** | **Manglish & Local Lexicon Support** | As the parser, I must accurately classify Malaysian business receipts with mixed local dialects. | **Should Have** | **Given** receipt text containing Manglish/Malay terms (*kopi c peng*, *minyak hitam*, *upah pasang*, *cukai jualan*), **When** parsed, **Then** correctly assign them to standard category codes (e.g., F&B, Vehicle Maintenance, Labor) without failure. |
| **`REQ-110`** | **Audit Trail Logging** | As a compliance auditor, I want a history of manual edits made to AI-extracted fields. | **Could Have** | **Given** an accountant modifies an extracted value, **When** saved, **Then** log `user_id`, `field_name`, `original_value`, `new_value`, and `timestamp`. |

---

## 2.5 Field-Level Confidence Scoring & Routing Rules

Every extracted receipt is evaluated through an automated triage pipeline before reaching the user:

```
[Raw Image] ──► [OCR + LLM Extraction] ──► [Rule-Based Validation Engine]
                                                        │
                      ┌─────────────────────────────────┴─────────────────────────────────┐
                      ▼                                                                   ▼
       [Passes All Verification Gates]                                     [Fails Verification Gates]
       • Math check: Total = Lines + Tax                                   • Math check failed (Delta > RM 0.02)
       • Date valid (not in future, valid format)                          • Missing mandatory field (Date/Total/Merchant)
       • Field confidence scores all ≥ 0.80                                • Any field confidence < 0.80
                      │                                                                   │
                      ▼                                                                   ▼
         Status: STATUS_AUTO_VERIFIED                                          Status: STATUS_NEEDS_REVIEW
           (Bypasses manual review)                                            (routes to Human Review GUI)
```

### Mandatory Verification Thresholds

1. **Arithmetic Consistency:** $\left|\sum(\text{line\_total}) + \text{sst} - \text{grand\_total}\right| \le 0.02\text{ RM}$. If line items are missing from a faded receipt, Grand Total must match Subtotal + Tax.
2. **Date Sanity:** Receipt date must be $\le \text{Current Date}$ and $\ge \text{Current Date} - 365\text{ days}$.
3. **Mandatory Fields Present:** `merchant_name`, `date`, `grand_total`. If any of these are null, flag immediately.

---

## 2.6 Non-Functional Requirements (NFRs)

* **Performance & Speed:**
    * Single receipt parsing (OCR + LLM completion): P95 $\le 8.0\text{ seconds}$.
    * Review GUI UI response: Pan/zoom and input field rendering $\le 100\text{ms}$.
    * Dashboard load time: $\le 1.5\text{ seconds}$ for accounts with up to 5,000 historical receipts.

* **Scalability:**
    * Queue architecture supports batch uploads of up to 50 receipt images per batch per user without request timeouts.
    * Database indexing optimized for multi-tenant queries partitioned by `client_id` and `billing_period`.

* **Security & Privacy:**
    * Receipt image files stored in secure S3-compatible buckets with short-lived pre-signed URLs (TTL = 15 minutes).
    * Storage and database comply with Malaysian Personal Data Protection Act (PDPA).
    * No customer financial receipts used for model training without explicit written consent.

* **Storage Footprint:**
    * Original image assets compressed to WebP/JPEG (target $\le 500\text{KB}$ per receipt) before long-term storage to reduce operational costs.
