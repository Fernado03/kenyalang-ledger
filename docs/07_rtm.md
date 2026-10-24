# Kenyalang Ledger — Step 7: Requirements Traceability Matrix (RTM)

---

## 7.1 How to read this matrix

The matrix binds each product requirement in [`02_prd.md`](02_prd.md) (`REQ-101` – `REQ-110`)
to the code that implements it and to the automated test that proves it.

**Status values**

| Status | Meaning |
|---|---|
| **Implemented** | The requirement is met by the repository as it stands. |
| **Implemented (demo)** | The behaviour exists and is tested, but a production-grade dependency is deliberately replaced by a demo mechanism (local disk instead of object storage, header identity instead of an IdP, in-process background work instead of a queue). |
| **Implemented (draft)** | Output is produced and tested, but it is explicitly not validated or submitted to the external authority. |
| **Not implemented** | No code exists. Listed in §7.4 so the gap is visible rather than implied. |

Every test named below exists in `backend/tests/` or `frontend/src/**/*.test.ts(x)`. Test names
were taken from the source, not from an earlier design document.

Run the evidence:

```bash
cd backend && python -m pytest -q && ruff check app tests
cd frontend && npm test && npm run build && npm run lint
```

---

## 7.2 Requirements traceability

| Req ID | Requirement | Status | Implementation | API / entity | Automated verification |
|---|---|---|---|---|---|
| **`REQ-101`** | Multi-source image ingestion (camera or batch, `.jpg/.jpeg/.png/.heic/.pdf`, ≤15 MB, EXIF orientation, stored original, async OCR) | **Implemented (demo)** — local filesystem storage, in-process background task | `backend/app/api/receipts.py` (`upload_receipts`, `detect_mime_type`, `process_receipt_background`)<br>`backend/app/pipeline/preprocessor.py` (`preprocess_receipt`, `decode_heic`, `decode_pdf`, `_check_pixels`)<br>`backend/app/core/storage.py`<br>`frontend/src/pages/UploadPage.tsx`<br>`frontend/src/pages/InboxPage.tsx` | `receipts` (`stored_path`, `mime_type`, `status`)<br>`POST /api/v1/clients/{client_id}/receipts/upload` → `202` | `test_upload_async.py::test_upload_returns_202_before_the_worker_runs`<br>`test_upload_async.py::test_pdf_upload_is_accepted`<br>`test_pipeline_formats.py::test_decode_heic_returns_expected_shape`<br>`test_pipeline_formats.py::test_auto_orient_swaps_axes_for_orientation_6`<br>`test_pipeline_formats.py::test_preprocess_image_accepts_png_without_exif`<br>`test_pipeline_formats.py::test_preprocess_image_accepts_jpeg_without_exif`<br>`test_upload_async.py::test_batch_over_50_files_is_rejected_before_writing`<br>`test_upload_async.py::test_oversized_file_is_413_and_leaves_no_row`<br>`test_upload_async.py::test_unsupported_magic_bytes_are_415_even_with_an_image_extension`<br>`test_upload_async.py::test_image_route_streams_the_exact_uploaded_bytes` |
| **`REQ-102`** | OCR with normalized 2D bounding boxes `[x_min, y_min, x_max, y_max]` | **Implemented** | `backend/app/pipeline/ocr_engine.py` (`process_receipt_image`, `tokens_to_dicts`)<br>`backend/app/pipeline/preprocessor.py` (CLAHE/deskew/resize)<br>`backend/app/schemas/receipt.py` (`ReceiptOcrToken`)<br>`frontend/src/components/ReceiptCanvas.tsx` | `receipts.ocr_raw_tokens` (JSONB)<br>`GET …/receipts/{receipt_id}` → `ocr_tokens` | `test_ocr_pipeline.py::test_easyocr_returns_bboxes`<br>`test_ocr_pipeline.py::test_coords_normalized_0_to_1`<br>`test_ocr_pipeline.py::test_line_numbers_follow_reading_order`<br>`test_ocr_pipeline.py::test_normalize_bbox_maps_pixels_to_relative`<br>`test_receipt_read_api.py::test_detail_returns_fields_line_items_and_tokens` |
| **`REQ-103`** | LLM extraction of header fields and line items | **Implemented** | `backend/app/pipeline/extractor.py`<br>`backend/app/schemas/receipt.py` (`ParsedReceiptSchema`, `ExtractedReceiptData`)<br>`backend/app/api/receipts.py` (`_extract_stage`, `_apply_outcome`) | `receipts` header columns<br>`receipt_line_items`<br>Provider failure → `ERR_EXTRACTION` | `test_extractor.py` (20 tests: schema enforcement, malformed output, provider errors)<br>`test_upload_async.py::test_provider_outage_becomes_err_extraction_without_fabricated_fields`<br>`test_receipts_upload.py::test_upload_persists_receipt_and_line_items` |
| **`REQ-104`** | Confidence scoring and arithmetic reconciliation; flag ambiguous or unbalanced receipts | **Implemented** | `backend/app/services/reconciler.py` (`MATH_TOLERANCE = 0.02`, `_math_discrepancy` honouring `amount_basis` and printed `rounding`, confidence floor `0.80`, date sanity, SST check)<br>`frontend/src/lib/audit.ts`<br>`frontend/src/components/MathBanner.tsx`<br>`frontend/src/components/StatusPill.tsx` | `receipts.status`, `amount_basis`, `rounding`, `validation_flags`, `math_discrepancy`<br>`GET …/receipts` | `test_reconciliation.py` (63 tests, including tax-basis identity, printed-rounding netting, `test_receipt_older_than_one_year_is_flagged`, `test_low_confidence_field_routes_to_review`, `test_sst_registered_merchant_without_tax_is_flagged`)<br>`test_receipts_upload.py::test_upload_flags_math_mismatch_for_review`<br>`frontend/src/lib/audit.test.ts` (8 tests)<br>`frontend/src/lib/format.test.ts` (confidence clamping) |
| **`REQ-105`** | Split-screen review console: image with pan/zoom, editable fields, low-confidence highlighting, `Cmd/Ctrl+Enter` verification | **Implemented** | `frontend/src/pages/ReviewPage.tsx`<br>`frontend/src/components/ReceiptCanvas.tsx`<br>`frontend/src/components/LineItemsEditor.tsx`<br>`frontend/src/components/MathBanner.tsx`<br>`frontend/src/lib/reviewShortcuts.ts`<br>`backend/app/api/receipts.py` (`update_client_receipt`) | `GET/PUT /api/v1/clients/{client_id}/receipts/{receipt_id}`<br>`ReceiptUpdateRequest` / `ReceiptUpdateResponse` | `frontend/src/lib/reviewShortcuts.test.ts` (7 tests)<br>`test_receipt_read_api.py::test_update_replaces_header_and_line_items`<br>`test_receipt_read_api.py::test_update_writes_audit_log_rows`<br>`test_receipt_update_integrity.py::test_header_only_update_recomputes_discrepancy_from_persisted_lines`<br>`test_receipt_read_api.py::test_detail_returns_fields_line_items_and_tokens` |
| **`REQ-106`** | Multi-client account console with strict tenant partitioning | **Implemented** | `backend/app/core/tenancy.py` (`get_owned_client`, `get_active_owned_client`)<br>`backend/app/api/clients.py`<br>`backend/app/api/receipts.py`, `exports.py`, `dashboard.py`<br>`frontend/src/pages/ClientsPage.tsx`<br>`frontend/src/components/AppShell.tsx` | `clients` table<br>`GET/POST /api/clients`<br>`GET/PUT/DELETE /api/clients/{client_id}` | `test_tenancy.py` (4 tests)<br>`test_clients.py::test_list_clients_returns_only_own_workspaces`<br>`test_clients.py::test_get_client_hides_other_tenants_workspaces`<br>`test_upload_async.py::test_upload_to_a_foreign_workspace_is_404`<br>`test_dashboard.py::test_cross_tenant_summary_is_not_found`<br>`test_audit.py::test_cross_tenant_audit_is_not_found` |
| **`REQ-107`** | Monthly supplier spend dashboard: total burn, top 5 suppliers, category breakdown | **Implemented** | `backend/app/api/dashboard.py`<br>`backend/app/schemas/dashboard.py`<br>`frontend/src/pages/DashboardPage.tsx`<br>`frontend/src/store/receiptStore.ts` | `GET /api/v1/clients/{client_id}/dashboard/summary?month=YYYY-MM` | `test_dashboard.py` (11 tests, including `test_total_excludes_unreviewed_receipts`, `test_top_suppliers_are_spend_descending_and_capped_at_five`, `test_every_expense_category_is_present_with_zeros`, `test_invalid_month_is_422`) |
| **`REQ-108`** | Dual export: accounting CSV and LHDN MyInvois JSON | **CSV implemented; MyInvois implemented (draft)** — not schema-validated, never submitted | `backend/app/services/export_engine.py` (`generate_accounting_csv`, `generate_myinvois_json`, `allocate_tax_cents`, `mark_exported`)<br>`backend/app/api/exports.py`<br>`frontend/src/pages/ExportsPage.tsx` | `GET …/exports/accounting-csv`<br>`GET …/exports/myinvois-json`<br>`POST …/exports/mark` | `test_exports.py::test_csv_neutralises_formula_injection`<br>`test_exports.py::test_allocate_tax_cents_largest_remainder`<br>`test_exports.py::test_myinvois_line_taxes_sum_to_document_total`<br>`test_exports.py::test_export_downloads_do_not_mutate_receipts`<br>`test_exports.py::test_mark_endpoint_is_idempotent_and_exports_stay_visible`<br>`test_exports.py::test_invalid_month_is_422_on_every_export_route`<br>`test_e2e_export.py::test_e2e_export_flow` |
| **`REQ-109`** | Manglish and local-lexicon classification of line items | **Implemented** — fixed five-category taxonomy, keyword classifier | `backend/app/services/classifier.py` (`classify_expense`, `CATEGORY_KEYWORDS`, `DEFAULT_CATEGORY`)<br>`backend/app/api/receipts.py` (classification on persist and update) | `receipt_line_items.expense_category` (`F&B`, `HARDWARE`, `WORKSHOP`, `RETAIL`, `OTHER`) | `test_upload_async.py::test_worker_persists_terminal_status_and_classified_lines`<br>`test_upload_async.py::test_line_items_are_classified_when_the_worker_persists`<br>`test_receipt_update_integrity.py::test_reconciling_line_items_clear_math_flag_and_classify_categories`<br>`test_dashboard.py::test_every_expense_category_is_present_with_zeros` |
| **`REQ-110`** | Audit trail for manual edits | **Implemented** | `backend/app/models/receipt_audit_log.py`<br>`backend/app/api/receipts.py` (`update_client_receipt`, `reject_client_receipt`, `get_client_receipt_audit`)<br>`backend/app/schemas/receipt.py` (`ReceiptAuditRead`)<br>`frontend/src/pages/ReviewPage.tsx` (audit panel)<br>`frontend/src/lib/audit.ts` | `receipt_audit_logs`<br>`GET …/receipts/{receipt_id}/audit` | `test_audit.py::test_successive_updates_log_one_row_per_changed_field`<br>`test_audit.py::test_audit_route_returns_newest_first_with_uuid_ids`<br>`test_audit.py::test_reject_writes_status_audit_row`<br>`test_receipt_read_api.py::test_update_writes_audit_log_rows`<br>`test_reject_and_export_status.py::test_reject_client_receipt_updates_status_and_audit_log` |

---

## 7.3 Field-name adaptations

The PRD and early design documents use names that do not match the shipped schema. The code is
authoritative; the differences are recorded here so the requirement text is not silently
reinterpreted.

| Documented name | Shipped name | Where |
|---|---|---|
| `brn_tin` | `merchant_brn` and `merchant_sst` (separate fields) | `receipts`, `ReceiptDetailResponse` |
| `date` | `invoice_date` | `receipts`, `ReceiptDetailResponse` |
| `sst_tax_amount` | `tax_amount` | `receipts`, `ReceiptDetailResponse` |
| `desc` | `description` | `receipt_line_items` |
| `LineItemRead` | `ReceiptDetailLineItem` | `backend/app/schemas/receipt.py` |
| `reviewed_at` | `verified_at` (no `reviewed_at` column exists) | `receipts` |
| Supplier field in dashboard | `supplier_name` (grouped from `receipts.merchant_name`) | `DashboardSummary` |
| Vehicle Maintenance / Labor categories | `WORKSHOP` (the fixed taxonomy has no separate vehicle or labour category) | `app/services/classifier.py` |

---

## 7.4 Demo boundaries and deliberate non-implementation

These are scope decisions, recorded so they are not mistaken for regressions.

| Capability implied by a document | Status | Reason |
|---|---|---|
| Identity provider, login, signed sessions | **Not implemented** | Demo uses a forgeable `X-Accountant-Id`, gated to `local`/`test`; production startup is refused. |
| Durable queue, worker, retries, dead-letter path | **Not implemented** | `BackgroundTasks` is deliberately in-process; a restart strands `PROCESSING_*` rows. |
| Alembic migrations | **Not implemented** | Additive guards in `init_db()` cover the two post-launch schema additions. |
| S3/MinIO object storage and pre-signed URLs | **Not implemented** | Receipt blobs live on local disk and are streamed through a tenancy-checked route. |
| LHDN schema validation and submission | **Not implemented** | The MyInvois JSON is a labelled draft envelope; it is never submitted. |
| Excel (`.xlsx`) export | **Not implemented** | Only CSV is produced; the CSV opens in AutoCount/SQL Account importers. |
| PDPA / WCAG / LHDN certification | **No claim made** | The repository contains no certification, audit, or compliance evidence. |
| Measured OCR accuracy benchmark | **Not implemented** | `dataset/` holds reference corpora; no accuracy number is published. |

---

## 7.5 Test inventory

| Suite | Files | Tests | Command |
|---|---|---|---|
| Backend | **18** files in `backend/tests/` | **311** | `cd backend && python -m pytest` |
| Frontend | **5** files in `frontend/src/` | **56** | `cd frontend && npm test` |
| Lint | — | — | `ruff check app tests`; `npm run lint` |
| Build | — | — | `npm run build` (`tsc -b && vite build`) |

Backend files: `test_auth.py` (6), `test_health.py` (4), `test_tenancy.py` (4),
`test_clients.py` (13), `test_audit.py` (4), `test_receipt_update_integrity.py` (7),
`test_exports.py` (39), `test_pipeline_formats.py` (13), `test_receipts_upload.py` (24),
`test_upload_async.py` (18), `test_receipt_read_api.py` (17), `test_e2e_export.py` (2),
`test_reject_and_export_status.py` (4), `test_dashboard.py` (22), `test_extractor.py` (38),
`test_ocr_pipeline.py` (27), `test_reconciliation.py` (63), `test_request_limits.py` (6).

Frontend files: `src/lib/format.test.ts`, `src/lib/audit.test.ts`,
`src/lib/reviewShortcuts.test.ts`, `src/components/StatusPill.test.tsx`,
`src/api/client.test.ts`.

Tests that require EasyOCR model weights skip with an explicit reason; no test silently
passes because a dependency is missing. The API and upload suites stub OCR and extraction so
they run offline against SQLite and a temporary storage root.
