import { useSessionStore } from '../store/sessionStore';
import type { Client, ClientCreate } from '../types/client';
import type {
  ReceiptDetail,
  ReceiptListResponse,
  ReceiptUpdateRequest,
  ReceiptUpdateResponse,
  ReceiptUploadResponse,
} from '../types/receipt';

/** API base prefix: '' (same origin) unless VITE_API_BASE_URL overrides it. */
const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '';

/** Header the backend reads the acting accountant UUID from. */
const ACCOUNTANT_HEADER = 'X-Accountant-Id';

/** Shape of a FastAPI-style error payload. */
interface ApiErrorBody {
  detail?: unknown;
}

/** Error thrown by `request`; carries HTTP status plus the backend detail text. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function parseDetail(payload: unknown): string {
  if (typeof payload === 'string') return payload;
  if (payload && typeof payload === 'object') {
    const body = payload as ApiErrorBody;
    const detail = body.detail;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object') {
      return JSON.stringify(detail);
    }
  }
  return '';
}

/**
 * Fetch wrapper: attaches the accountant header, throws an ApiError carrying
 * status + parsed detail on any non-2xx response.
 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const accountantId = useSessionStore.getState().accountantId;
  const headers = new Headers(init?.headers);
  headers.set('Accept', 'application/json');
  if (accountantId) {
    headers.set(ACCOUNTANT_HEADER, accountantId);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    let parsed: unknown;
    const text = await response.text();
    if (text) {
      try {
        parsed = JSON.parse(text) as unknown;
      } catch {
        parsed = text;
      }
    }
    const detail = parseDetail(parsed) || `Request failed with status ${response.status}`;
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

/** `ClientRead` plus the aggregates carried by `GET /api/clients`. */
export interface ClientSummary extends Client {
  unreviewed_count: number;
  verified_count: number;
}

/** One dashboard supplier aggregate. */
export interface TopSupplier {
  supplier_name: string;
  total_spend: string;
  receipt_count: number;
}

/** One dashboard category aggregate (pre-tax line totals). */
export interface CategoryBreakdown {
  category: string;
  total_spend: string;
}

/** `GET /api/v1/clients/{clientId}/dashboard/summary` response. */
export interface DashboardSummary {
  month: string;
  total_spend: string;
  top_suppliers: TopSupplier[];
  category_breakdown: CategoryBreakdown[];
}

/** One receipt audit-log row. `id` is a UUID, not a numeric sequence. */
export interface ReceiptAuditEntry {
  id: string;
  user_id: string;
  field_name: string;
  old_value: string | null;
  new_value: string | null;
  created_at: string;
}

/** `GET /api/v1/clients/{clientId}/receipts/{receiptId}/audit` response. */
export interface ReceiptAuditResponse {
  items: ReceiptAuditEntry[];
}

/** `GET /api/clients` — all workspaces owned by the session accountant. */
export async function listClients(): Promise<ClientSummary[]> {
  const body = await request<{ items: ClientSummary[] }>('/api/clients');
  return body.items;
}

/** `POST /api/clients` — create a workspace. */
export async function createClient(payload: ClientCreate): Promise<Client> {
  return request<Client>('/api/clients', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

/** `GET /api/v1/clients/{clientId}/receipts` — paginated inbox list. */
export async function listReceipts(
  clientId: string,
  options: { status?: string; limit?: number; offset?: number } = {},
): Promise<ReceiptListResponse> {
  const params = new URLSearchParams();
  if (options.status) params.set('status', options.status);
  params.set('limit', String(options.limit ?? 50));
  params.set('offset', String(options.offset ?? 0));
  const query = params.toString();
  const path = `/api/v1/clients/${clientId}/receipts${query ? `?${query}` : ''}`;
  return request<ReceiptListResponse>(path);
}

/** `GET /api/v1/clients/{clientId}/receipts/{receiptId}` — full detail. */
export async function getReceipt(
  clientId: string,
  receiptId: string,
): Promise<ReceiptDetail> {
  return request<ReceiptDetail>(
    `/api/v1/clients/${clientId}/receipts/${receiptId}`,
  );
}

/** `PUT /api/v1/clients/{clientId}/receipts/{receiptId}` — save & verify. */
export async function updateReceipt(
  clientId: string,
  receiptId: string,
  payload: ReceiptUpdateRequest,
): Promise<ReceiptUpdateResponse> {
  return request<ReceiptUpdateResponse>(
    `/api/v1/clients/${clientId}/receipts/${receiptId}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  );
}

/** `POST /api/v1/clients/{clientId}/receipts/{receiptId}/reject` — mark rejected. */
export async function rejectReceipt(
  clientId: string,
  receiptId: string,
): Promise<ReceiptUpdateResponse> {
  return request<ReceiptUpdateResponse>(
    `/api/v1/clients/${clientId}/receipts/${receiptId}/reject`,
    {
      method: 'POST',
    },
  );
}

/**
 * `POST /api/v1/clients/{clientId}/receipts/upload` — single multipart request
 * with one repeated `files` field per file (max 50 per batch).
 */
export async function uploadReceipts(
  clientId: string,
  files: File[],
): Promise<ReceiptUploadResponse> {
  const form = new FormData();
  for (const file of files) {
    form.append('files', file, file.name);
  }
  return request<ReceiptUploadResponse>(
    `/api/v1/clients/${clientId}/receipts/upload`,
    {
      method: 'POST',
      body: form,
    },
  );
}

/** Relative image path for a receipt (no origin; same-origin fetch). */
export function receiptImageUrl(clientId: string, receiptId: string): string {
  return `${API_BASE_URL}/api/v1/clients/${clientId}/receipts/${receiptId}/image`;
}

/**
 * Triggers a browser file download using authenticated fetch with X-Accountant-Id.
 */
export async function downloadExport(
  path: string,
  fallbackFilename: string,
): Promise<void> {
  const accountantId = useSessionStore.getState().accountantId;
  const headers = new Headers();
  if (accountantId) {
    headers.set(ACCOUNTANT_HEADER, accountantId);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { headers });
  if (!response.ok) {
    let detail = `Download failed with status ${response.status}`;
    try {
      const text = await response.text();
      const parsed = JSON.parse(text) as unknown;
      detail = parseDetail(parsed) || detail;
    } catch {
      // ignore
    }
    throw new ApiError(response.status, detail);
  }

  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition');
  let filename = fallbackFilename;
  if (disposition && disposition.includes('filename=')) {
    const match = /filename=["']?([^"';]+)["']?/.exec(disposition);
    if (match && match[1]) {
      filename = match[1];
    }
  }

  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

export async function downloadAccountingCsv(
  clientId: string,
  month?: string,
): Promise<void> {
  const query = month ? `?month=${encodeURIComponent(month)}` : '';
  const suffix = month ? month.replace('-', '') : 'all';
  return downloadExport(
    `/api/v1/clients/${clientId}/exports/accounting-csv${query}`,
    `Kenyalang_PurJournal_${suffix}.csv`,
  );
}

export async function downloadMyInvoisJson(
  clientId: string,
  month?: string,
): Promise<void> {
  const query = month ? `?month=${encodeURIComponent(month)}` : '';
  const suffix = month ? month.replace('-', '') : 'all';
  return downloadExport(
    `/api/v1/clients/${clientId}/exports/myinvois-json${query}`,
    `Kenyalang_MyInvois_${suffix}.json`,
  );
}

export async function downloadBothExports(
  clientId: string,
  month?: string,
): Promise<void> {
  await downloadAccountingCsv(clientId, month);
  const { promise, resolve } = Promise.withResolvers<void>();
  setTimeout(resolve, 200);
  await promise;
  await downloadMyInvoisJson(clientId, month);
}

/** `GET /api/v1/clients/{clientId}/dashboard/summary` — month defaults server-side. */
export async function getDashboardSummary(
  clientId: string,
  month?: string,
): Promise<DashboardSummary> {
  const query = month ? `?month=${encodeURIComponent(month)}` : '';
  return request<DashboardSummary>(
    `/api/v1/clients/${clientId}/dashboard/summary${query}`,
  );
}

/** `POST /api/v1/clients/{clientId}/exports/mark` — verified → exported. */
export async function markExported(
  clientId: string,
  month?: string,
): Promise<{ updated: number }> {
  const query = month ? `?month=${encodeURIComponent(month)}` : '';
  return request<{ updated: number }>(
    `/api/v1/clients/${clientId}/exports/mark${query}`,
    { method: 'POST' },
  );
}

/** `GET /api/v1/clients/{clientId}/receipts/{receiptId}/audit` — newest first. */
export async function getReceiptAudit(
  clientId: string,
  receiptId: string,
): Promise<ReceiptAuditResponse> {
  return request<ReceiptAuditResponse>(
    `/api/v1/clients/${clientId}/receipts/${receiptId}/audit`,
  );
}
