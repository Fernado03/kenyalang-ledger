# Kenyalang Ledger — Step 7: Requirements Traceability Matrix (RTM)

---

## 7.1 The Traceability Engine

The **Requirements Traceability Matrix (RTM)** binds every requirement from the PRD (`REQ-101` through `REQ-110`) to its corresponding screen, technical pipeline module, database entity, API contract, and automated test suite.

This ensures:

1. **Zero Dead Code:** Your AI agent will not write endpoints or database columns that have no functional home.
2. **Zero Missing Features:** No requirement from Step 2 will be forgotten during coding sprints.
3. **Automated Verification:** Every row defines the exact passing criteria for testing before shipping.

---

## 7.2 Comprehensive Traceability Matrix

| Req ID | Feature Name | Appflow View (Step 3) | UI Component (Step 4) | TRD Engine (Step 5) | Backend Entity & API (Step 6) | Sprint Task | Verification Test Case |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **`REQ-101`** | **Multi-Source Ingestion** | `SCR-02` (Inbox)<br>`SCR-04` (Mobile) | `DropzoneArea.tsx`<br>`MobileCamera.tsx` | `pipeline/preprocessor.py`<br>(OpenCV CLAHE / EXIF) | `receipts` table<br>`POST /api/v1/clients/{id}/receipts/upload` | **Sprint 1** | `test_ingest_exif_rotation()`<br>`test_file_size_limit_15mb()` |
| **`REQ-102`** | **Spatial OCR Token Extraction** | Background Worker | N/A (Headless) | `pipeline/ocr_engine.py`<br>(EasyOCR + PyTorch) | `receipts.ocr_raw_tokens` (JSONB) | **Sprint 1** | `test_easyocr_returns_bboxes()`<br>`test_coords_normalized_0_to_1()` |
| **`REQ-103`** | **Structured Entity Extraction** | Background Worker | N/A (Headless) | `pipeline/extractor.py`<br>(Instructor + LLM) | `receipts`<br>`receipt_line_items`<br>`ExtractedReceiptData` | **Sprint 2** | `test_llm_json_schema_compliance()`<br>`test_sroie_thermal_extraction()` |
| **`REQ-104`** | **Confidence & Reconciliation** | `SCR-02` (Inbox)<br>`SCR-03` (Review) | `StatusPill.tsx`<br>`MathAlert.tsx` | `services/reconciler.py`<br>(Deterministic Rules) | `receipts.status`<br>`receipts.validation_flags`<br>`receipts.math_discrepancy` | **Sprint 2** | `test_math_reconciliation_pass()`<br>`test_math_delta_triggers_review()` |
| **`REQ-105`** | **Split-Screen Review Console** | `SCR-03` (Review) | `ReviewConsole.tsx`<br>`ReceiptCanvas.tsx`<br>`LineItemTable.tsx` | Canvas 60fps pan/zoom<br>Active bbox highlighting | `GET /receipts/{id}`<br>`PUT /receipts/{id}`<br>`ReceiptUpdateRequest` | **Sprint 3** | `test_keyboard_cmd_enter_saves()`<br>`test_bbox_syncs_with_focused_input()` |
| **`REQ-106`** | **Multi-Client Workspace** | `SCR-01` (Switcher) | `ClientSelector.tsx`<br>`WorkspaceModal.tsx` | FastAPI Tenant Middleware<br>(Route-level guard) | `clients` table<br>`GET /api/v1/clients`<br>`POST /api/v1/clients` | **Sprint 1** | `test_tenant_isolation_forbidden()`<br>`test_accountant_can_create_client()` |
| **`REQ-107`** | **Supplier Spend Dashboard** | `SCR-02` (Inbox)<br>`/dashboard` | `SpendSummary.tsx`<br>`TopSuppliersTable.tsx` | SQL Aggregation Engine<br>(Sum by supplier/month) | `receipts`<br>`GET /clients/{id}/dashboard/summary` | **Sprint 4** | `test_spend_totals_match_verified_receipts()` |
| **`REQ-108`** | **Dual Export Engine** | `SCR-05` (Exports) | `ExportHub.tsx`<br>`ExportFormatCard.tsx` | `services/export_engine.py`<br>(CSV + LHDN MultiLine) | `GET /exports/accounting-csv`<br>`GET /exports/myinvois-json` | **Sprint 3** | `test_autocount_csv_headers()`<br>`test_lhdn_myinvois_v1_1_schema_diff()` |
| **`REQ-109`** | **Manglish & Local Lexicon** | Background Worker | N/A (Extraction) | System Prompt Lexicon +<br>Local taxonomy dictionary | `pipeline/extractor.py`<br>`receipt_line_items.description` | **Sprint 2** | `test_manglish_food_terms_extracted()`<br>`test_workshop_terms_extracted()` |
| **`REQ-110`** | **Audit Trail Logging** | `SCR-03` (Review) | `AuditLogDrawer.tsx`<br>(Optional inspector) | `services/audit.py`<br>(Change-diff recorder) | `receipt_audit_logs` table<br>`GET /receipts/{id}/audit` | **Sprint 4** | `test_manual_field_edit_creates_log()` |
