import { create } from 'zustand';
import {
  ApiError,
  createClient as createClientRequest,
  getReceipt,
  listClients,
  listReceipts,
  updateReceipt,
  uploadReceipts,
} from '../api/client';
import type { Client, ClientCreate } from '../types/client';
import type {
  DraftHeaderField,
  DraftLineField,
  DraftLineItem,
  ReceiptDetail,
  ReceiptDraft,
  ReceiptListItem,
  ReceiptListStatus,
  ReceiptUpdateLineItem,
  ReceiptUpdateRequest,
  ReceiptUploadResult,
} from '../types/receipt';

/** localStorage key for the selected client workspace. */
const CURRENT_CLIENT_ID_KEY = 'kenyalang.current_client_id';

/** localStorage prefix for an in-progress review draft: `…draft.${receiptId}`. */
const DRAFT_KEY_PREFIX = 'kenyalang.draft.';

/** Default inbox page size (docs/06_schema_api.md §6.3.1). */
const DEFAULT_LIST_LIMIT = 50;

/** Message used when a thrown value carries no usable text. */
const UNKNOWN_ERROR_MESSAGE = 'Unknown error';

/** Error text from an unknown thrown value. */
function errorMessage(error: unknown): string {
  return error instanceof Error && error.message !== '' ? error.message : UNKNOWN_ERROR_MESSAGE;
}

/** Draft key for one receipt. */
function draftKey(receiptId: string): string {
  return `${DRAFT_KEY_PREFIX}${receiptId}`;
}

/** Reads the persisted client id; storage failures yield null. */
function readStoredClientId(): string | null {
  try {
    return window.localStorage.getItem(CURRENT_CLIENT_ID_KEY);
  } catch {
    return null;
  }
}

/** Persists the selected client id; storage failures are swallowed. */
function persistClientId(id: string): void {
  try {
    window.localStorage.setItem(CURRENT_CLIENT_ID_KEY, id);
  } catch {
    // Private-mode storage failures must not block client selection.
  }
}

/** Persists a draft; storage failures are swallowed. */
function persistDraft(draft: PersistedDraft): void {
  try {
    window.localStorage.setItem(draftKey(draft.receipt_id), JSON.stringify(draft));
  } catch {
    // Private-mode storage failures must not block editing.
  }
}

/** Persistent draft shape: the editable draft plus the receipt it belongs to. */
interface PersistedDraft extends ReceiptDraft {
  receipt_id: string;
}

/** Reads a persisted draft; storage failures or bad JSON yield null. */
function readDraft(receiptId: string): PersistedDraft | null {
  try {
    const raw = window.localStorage.getItem(draftKey(receiptId));
    if (raw === null) {
      return null;
    }
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) {
      return null;
    }
    const candidate = parsed as Partial<PersistedDraft>;
    if (candidate.receipt_id !== receiptId || !Array.isArray(candidate.line_items)) {
      return null;
    }
    return {
      receipt_id: receiptId,
      merchant_name: candidate.merchant_name ?? '',
      merchant_brn: candidate.merchant_brn ?? '',
      merchant_sst: candidate.merchant_sst ?? '',
      invoice_date: candidate.invoice_date ?? '',
      invoice_number: candidate.invoice_number ?? '',
      subtotal: candidate.subtotal ?? '',
      tax_amount: candidate.tax_amount ?? '',
      grand_total: candidate.grand_total ?? '',
      line_items: candidate.line_items as DraftLineItem[],
    };
  } catch {
    return null;
  }
}

/** Removes a persisted draft; storage failures are swallowed. */
function clearPersistedDraft(receiptId: string): void {
  try {
    window.localStorage.removeItem(draftKey(receiptId));
  } catch {
    // Nothing to clean up.
  }
}

/** Maps a stored receipt onto a fresh editable draft. */
function draftFromReceipt(receipt: ReceiptDetail): ReceiptDraft {
  return {
    merchant_name: receipt.merchant_name ?? '',
    merchant_brn: receipt.merchant_brn ?? '',
    merchant_sst: receipt.merchant_sst ?? '',
    invoice_date: receipt.invoice_date === null ? '' : receipt.invoice_date.slice(0, 10),
    invoice_number: receipt.invoice_number ?? '',
    subtotal: receipt.subtotal === null ? '' : String(receipt.subtotal),
    tax_amount: receipt.tax_amount === null ? '' : String(receipt.tax_amount),
    grand_total: receipt.grand_total === null ? '' : String(receipt.grand_total),
    line_items: receipt.line_items.map((item) => ({
      key: crypto.randomUUID(),
      description: item.description,
      quantity: String(item.quantity),
      unit_price: String(item.unit_price),
      line_total: String(item.line_total),
    })),
  };
}

/** Header field payload value: blank strings become null. */
function nullIfBlank(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

/** Line money field payload value: blank becomes `0.00`. */
function zeroIfBlank(value: string): string {
  const trimmed = value.trim();
  return trimmed === '' ? '0.00' : trimmed;
}

/** Builds the PUT body from a draft, dropping fully blank line rows. */
function updateRequestFromDraft(draft: ReceiptDraft): ReceiptUpdateRequest {
  const line_items: ReceiptUpdateLineItem[] = draft.line_items
    .filter((item) => item.description.trim() !== '' || item.line_total.trim() !== '')
    .map((item) => ({
      description: item.description.trim(),
      quantity: zeroIfBlank(item.quantity),
      unit_price: zeroIfBlank(item.unit_price),
      line_total: zeroIfBlank(item.line_total),
    }));

  return {
    merchant_name: nullIfBlank(draft.merchant_name),
    merchant_brn: nullIfBlank(draft.merchant_brn),
    merchant_sst: nullIfBlank(draft.merchant_sst),
    invoice_date: nullIfBlank(draft.invoice_date),
    invoice_number: nullIfBlank(draft.invoice_number),
    subtotal: nullIfBlank(draft.subtotal),
    tax_amount: nullIfBlank(draft.tax_amount),
    grand_total: nullIfBlank(draft.grand_total),
    line_items,
  };
}

/** SCR-02 inbox + SCR-03 review console state. */
export interface ReceiptStoreState {
  currentClientId: string | null;
  clients: Client[];
  receipts: ReceiptListItem[];
  receiptsTotal: number;
  statusFilter: ReceiptListStatus;
  activeReceipt: ReceiptDetail | null;
  draft: ReceiptDraft | null;
  receiptsLoading: boolean;
  receiptsError: string | null;
  receiptLoading: boolean;
  saveState: 'idle' | 'saving' | 'saved' | 'error';
  saveError: string | null;
  uploadState: 'idle' | 'uploading' | 'done' | 'error';
  uploadResult: { uploaded: ReceiptUploadResult[]; failed: string | null } | null;

  setCurrentClientId: (id: string) => Promise<void>;
  loadClients: () => Promise<void>;
  createClient: (payload: ClientCreate) => Promise<Client>;
  loadClientReceipts: (clientId: string) => Promise<void>;
  setStatusFilter: (filter: ReceiptListStatus) => Promise<void>;
  loadReceipt: (receiptId: string) => Promise<void>;
  resetDraftFromReceipt: () => void;
  setDraftField: (key: DraftHeaderField, value: string) => void;
  addDraftLine: () => void;
  updateDraftLine: (key: string, field: DraftLineField, value: string) => void;
  removeDraftLine: (key: string) => void;
  saveReceipt: () => Promise<ReceiptDetail>;
  uploadFiles: (files: File[]) => Promise<void>;
}

/** Inbox list fetch shared by `setCurrentClientId` and `loadClientReceipts`. */
async function fetchReceipts(
  clientId: string,
  status: ReceiptListStatus,
): Promise<{ items: ReceiptListItem[]; total: number }> {
  const response = await listReceipts(clientId, {
    status,
    limit: DEFAULT_LIST_LIMIT,
    offset: 0,
  });
  return { items: response.items, total: response.total };
}

/** Failure text for the inbox error slot: ApiError detail or a plain message. */
function receiptsFailure(error: unknown): string {
  return error instanceof ApiError ? error.message : errorMessage(error);
}

/** Applies a fetched inbox page to the store. */
function applyReceiptsPage(
  set: (partial: Partial<ReceiptStoreState>) => void,
  page: { items: ReceiptListItem[]; total: number },
): void {
  set({ receipts: page.items, receiptsTotal: page.total, receiptsLoading: false });
}

/** Persists a draft alongside its receipt id. */
function persistDraftFor(receiptId: string, draft: ReceiptDraft): void {
  persistDraft({ receipt_id: receiptId, ...draft });
}

/**
 * SCR-02 batch inbox plus SCR-03 review console state: client selection, the
 * inbox list with its status filter, and the active receipt's editable draft.
 */
export const useReceiptStore = create<ReceiptStoreState>((set, get) => ({
  currentClientId: readStoredClientId(),
  clients: [],
  receipts: [],
  receiptsTotal: 0,
  statusFilter: 'ALL',
  activeReceipt: null,
  draft: null,
  receiptsLoading: false,
  receiptsError: null,
  receiptLoading: false,
  saveState: 'idle',
  saveError: null,
  uploadState: 'idle',
  uploadResult: null,

  setCurrentClientId: async (id: string) => {
    persistClientId(id);
    set({
      currentClientId: id,
      receipts: [],
      receiptsTotal: 0,
      activeReceipt: null,
      draft: null,
      receiptsLoading: true,
      receiptsError: null,
    });
    try {
      applyReceiptsPage(set, await fetchReceipts(id, get().statusFilter));
    } catch (error) {
      set({ receiptsError: receiptsFailure(error), receiptsLoading: false });
    }
  },

  loadClients: async () => {
    let loaded: Client[];
    try {
      loaded = await listClients();
    } catch (error) {
      set({ clients: [], receiptsError: receiptsFailure(error) });
      return;
    }

    const current = get().currentClientId;
    if (current === null && loaded.length > 0) {
      const adopted = loaded[0].id;
      persistClientId(adopted);
      set({ clients: loaded, currentClientId: adopted, receiptsLoading: true });
      try {
        applyReceiptsPage(set, await fetchReceipts(adopted, get().statusFilter));
      } catch (error) {
        set({
          receipts: [],
          receiptsTotal: 0,
          receiptsError: receiptsFailure(error),
          receiptsLoading: false,
        });
      }
      return;
    }

    set({ clients: loaded });
  },

  createClient: async (payload: ClientCreate) => {
    const created = await createClientRequest(payload);
    set({ clients: [...get().clients, created] });
    if (get().currentClientId === null) {
      persistClientId(created.id);
      set({
        currentClientId: created.id,
        receipts: [],
        receiptsTotal: 0,
        activeReceipt: null,
        draft: null,
      });
    }
    return created;
  },

  loadClientReceipts: async (clientId: string) => {
    set({ receiptsLoading: true, receiptsError: null });
    try {
      applyReceiptsPage(set, await fetchReceipts(clientId, get().statusFilter));
    } catch (error) {
      set({
        receipts: [],
        receiptsTotal: 0,
        receiptsLoading: false,
        receiptsError: receiptsFailure(error),
      });
    }
  },

  setStatusFilter: async (filter: ReceiptListStatus) => {
    set({ statusFilter: filter });
    const current = get().currentClientId;
    if (current !== null) {
      await get().loadClientReceipts(current);
    }
  },

  loadReceipt: async (receiptId: string) => {
    const clientId = get().currentClientId;
    if (clientId === null) {
      return;
    }
    set({ receiptLoading: true });
    try {
      const detail = await getReceipt(clientId, receiptId);
      const base = draftFromReceipt(detail);
      const stored = readDraft(receiptId);
      const draft: ReceiptDraft = stored === null ? base : { ...base, ...stored };
      if (stored !== null) {
        persistDraftFor(receiptId, draft);
      }
      set({ activeReceipt: detail, draft, receiptLoading: false });
    } catch (error) {
      set({ receiptLoading: false });
      throw error instanceof ApiError ? error : new Error(errorMessage(error));
    }
  },

  resetDraftFromReceipt: () => {
    const receipt = get().activeReceipt;
    if (receipt === null) {
      return;
    }
    const draft = draftFromReceipt(receipt);
    set({ draft });
    persistDraftFor(receipt.id, draft);
  },

  setDraftField: (key: DraftHeaderField, value: string) => {
    const draft = get().draft;
    if (draft === null) {
      return;
    }
    const updated: ReceiptDraft = { ...draft, [key]: value };
    set({ draft: updated });
    persistDraftFor(get().activeReceipt?.id ?? "", updated);
  },

  addDraftLine: () => {
    const draft = get().draft;
    if (draft === null) {
      return;
    }
    const line: DraftLineItem = {
      key: crypto.randomUUID(),
      description: '',
      quantity: '1.00',
      unit_price: '0.00',
      line_total: '0.00',
    };
    const updated: ReceiptDraft = { ...draft, line_items: [...draft.line_items, line] };
    set({ draft: updated });
    persistDraftFor(get().activeReceipt?.id ?? "", updated);
  },

  updateDraftLine: (key: string, field: DraftLineField, value: string) => {
    const draft = get().draft;
    if (draft === null) {
      return;
    }
    const updated: ReceiptDraft = {
      ...draft,
      line_items: draft.line_items.map((item) =>
        item.key === key ? { ...item, [field]: value } : item,
      ),
    };
    set({ draft: updated });
    persistDraftFor(get().activeReceipt?.id ?? "", updated);
  },

  removeDraftLine: (key: string) => {
    const draft = get().draft;
    if (draft === null) {
      return;
    }
    const updated: ReceiptDraft = {
      ...draft,
      line_items: draft.line_items.filter((item) => item.key !== key),
    };
    set({ draft: updated });
    persistDraftFor(get().activeReceipt?.id ?? "", updated);
  },

  saveReceipt: async () => {
    const { currentClientId, activeReceipt, draft } = get();
    if (currentClientId === null || activeReceipt === null || draft === null) {
      const message = 'No receipt is open for saving';
      set({ saveState: 'error', saveError: message });
      throw new Error(message);
    }

    set({ saveState: 'saving', saveError: null });
    try {
      await updateReceipt(currentClientId, activeReceipt.id, updateRequestFromDraft(draft));
      clearPersistedDraft(activeReceipt.id);
      const detail = await getReceipt(currentClientId, activeReceipt.id);
      set({
        activeReceipt: detail,
        draft: draftFromReceipt(detail),
        saveState: 'saved',
        saveError: null,
      });
      await get().loadClientReceipts(currentClientId);
      return detail;
    } catch (error) {
      const message = receiptsFailure(error);
      set({ saveState: 'error', saveError: message });
      throw error instanceof ApiError ? error : new Error(message);
    }
  },

  uploadFiles: async (files: File[]) => {
    const clientId = get().currentClientId;
    if (clientId === null || files.length === 0) {
      return;
    }
    set({ uploadState: 'uploading', uploadResult: null });
    try {
      const response = await uploadReceipts(clientId, files);
      set({
        uploadState: 'done',
        uploadResult: { uploaded: response.receipts, failed: null },
      });
      await get().loadClientReceipts(clientId);
    } catch (error) {
      set({
        uploadState: 'error',
        uploadResult: { uploaded: [], failed: `Batch rejected: ${receiptsFailure(error)}` },
      });
    }
  },
}));
