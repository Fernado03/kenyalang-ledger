/**
 * Wire contracts for the receipt routes (docs/06_schema_api.md §6.3.1–§6.3.4).
 *
 * Money and decimal fields are decimal STRINGS on the wire ("99.50"); bounding
 * boxes are [x_min, y_min, x_max, y_max] floats normalized to 0..1; dates are
 * ISO "YYYY-MM-DD". Never accumulate Ringgit in floats — use lib/format.ts.
 */

/** Pipeline + verification lifecycle states (§6.1.2), exactly 13 values. */
export type ReceiptStatus =
  | 'PENDING_UPLOAD'
  | 'UPLOADED'
  | 'PROCESSING_OCR'
  | 'PROCESSING_LLM'
  | 'VALIDATING_MATH'
  | 'STATUS_NEEDS_REVIEW'
  | 'STATUS_AUTO_VERIFIED'
  | 'STATUS_VERIFIED'
  | 'STATUS_EXPORTED'
  | 'ERR_UNREADABLE'
  | 'ERR_TIMEOUT'
  | 'ERR_FILE_CORRUPT';

/** Inbox filter values; passed verbatim as the `status` query parameter. */
export type ReceiptListStatus = 'ALL' | 'NEEDS_REVIEW' | 'VERIFIED' | 'EXPORTED';

/** One row of the SCR-02 batch inbox. */
export interface ReceiptListItem {
  id: string;
  filename: string;
  merchant_name: string | null;
  invoice_date: string | null;
  subtotal: string | null;
  tax_amount: string | null;
  grand_total: string | null;
  status: ReceiptStatus;
  validation_flags: string[];
  overall_confidence: number;
  math_discrepancy: string;
  image_url: string;
  line_item_count: number;
}

/** Envelope returned by `GET /api/v1/clients/{client_id}/receipts`. */
export interface ReceiptListResponse {
  total: number;
  limit: number;
  offset: number;
  items: ReceiptListItem[];
}

/** Per-field provenance: confidence plus (optional) normalized bbox. */
export interface FieldProvenance {
  name: string;
  confidence: number;
  bbox: number[] | null;
}

/** One OCR token, used for hover tooltips and bbox overlays in SCR-03. */
export interface OcrToken {
  text: string;
  confidence: number;
  bbox: number[] | null;
  line_num: number;
}

/** A line item as stored, with server id and provenance. */
export interface ReceiptLineItem {
  id: string;
  line_index: number;
  description: string;
  quantity: string;
  unit_price: string;
  line_total: string;
  confidence: number;
  bbox: number[] | null;
}

/** Full receipt payload for the SCR-03 review console. */
export interface ReceiptDetail {
  id: string;
  client_id: string;
  filename: string;
  status: ReceiptStatus;
  processing_error: string | null;
  image_url: string;
  merchant_name: string | null;
  merchant_brn: string | null;
  merchant_sst: string | null;
  invoice_date: string | null;
  invoice_number: string | null;
  subtotal: string | null;
  tax_amount: string | null;
  grand_total: string | null;
  math_discrepancy: string;
  overall_confidence: number;
  validation_flags: string[];
  created_at: string;
  verified_at: string | null;
  fields: FieldProvenance[];
  line_items: ReceiptLineItem[];
  ocr_tokens: OcrToken[];
}

/** Body of `PUT /api/v1/clients/{client_id}/receipts/{receipt_id}`. */
export interface ReceiptUpdateRequest {
  merchant_name: string | null;
  merchant_brn: string | null;
  merchant_sst: string | null;
  invoice_date: string | null;
  invoice_number: string | null;
  subtotal: string | null;
  tax_amount: string | null;
  grand_total: string | null;
  line_items: ReceiptUpdateLineItem[];
}

/** One replaced line-item row; the server re-sequences line_index 0..n-1. */
export interface ReceiptUpdateLineItem {
  description: string;
  quantity: string;
  unit_price: string;
  line_total: string;
}

/** Ack returned by the verify/update route. */
export interface ReceiptUpdateResponse {
  id: string;
  status: ReceiptStatus;
  updated_at: string;
  verified_by: string;
  math_discrepancy: string;
}

/** One file inside the batch upload response (§6.3.1). */
export interface ReceiptUploadResult {
  id: string;
  filename: string;
  status: ReceiptStatus;
  error?: string;
}

/** Envelope returned by `POST /api/v1/clients/{client_id}/receipts/upload`. */
export interface ReceiptUploadResponse {
  batch_id: string;
  total_received: number;
  receipts: ReceiptUploadResult[];
}

/** An editable line-item row; `key` is local React/edit identity only. */
export interface DraftLineItem {
  key: string;
  description: string;
  quantity: string;
  unit_price: string;
  line_total: string;
}

/** Editable SCR-03 form state: header fields as strings plus line rows. */
export interface ReceiptDraft {
  merchant_name: string;
  merchant_brn: string;
  merchant_sst: string;
  invoice_date: string;
  invoice_number: string;
  subtotal: string;
  tax_amount: string;
  grand_total: string;
  line_items: DraftLineItem[];
}

/** Header draft keys that map 1:1 onto a form input. */
export type DraftHeaderField =
  | 'merchant_name'
  | 'merchant_brn'
  | 'merchant_sst'
  | 'invoice_date'
  | 'invoice_number'
  | 'subtotal'
  | 'tax_amount'
  | 'grand_total';

/** Line-item draft keys that map 1:1 onto a table input. */
export type DraftLineField = 'description' | 'quantity' | 'unit_price' | 'line_total';
