import { create } from 'zustand';
import {
  ApiError,
  createClient as createClientRequest,
  getReceipt,
  listClients,
  listReceipts,
  rejectReceipt as rejectReceiptRequest,
  updateReceipt,
  uploadReceipts,
} from '../api/client';
import { formatCents, parseMoneyToCents } from '../lib/format';
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

/**
 * Exact `qty × unit price` in cents (qty is a plain count, both sides parsed as
 * hundredths through BigInt). Returns `null` when either side is unparseable or
 * the quantity is not positive, so a bad keystroke never writes a bogus total.
 */
function expectedLineCents(item: DraftLineItem): bigint | null {
  const quantity = parseMoneyToCents(item.quantity);
  const unitPrice = parseMoneyToCents(item.unit_price);
  if (quantity === null || unitPrice === null || quantity <= 0n) {
    return null;
  }
  return (quantity * unitPrice + 50n) / 100n;
}

/**
 * True while the row's total still mirrors its own qty × unit price (or is
 * blank). Once the accountant types a different total — a discount, a printed
 * subtotal — the derived value must never overwrite their number.
 */
function lineTotalIsDerived(item: DraftLineItem): boolean {
  if (item.line_total.trim() === '') {
    return true;
  }
  const printed = parseMoneyToCents(item.line_total);
  const expected = expectedLineCents(item);
  if (expected === null) {
    return printed === null || printed === 0n;
  }
  return printed !== null && printed === expected;
}

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
  /** Counts per inbox filter bucket, fetched with the list. */
  statusCounts: Record<string, number>;
  receiptsOffset: number;
  statusFilter: ReceiptListStatus;
  activeReceipt: ReceiptDetail | null;
  draft: ReceiptDraft | null;
  /** Server truth the draft is compared against to decide if it is dirty. */
  draftBaseline: ReceiptDraft | null;
  receiptsLoading: boolean;
  receiptsError: string | null;
  receiptLoading: boolean;
  /** Why the last receipt load failed; cleared when a load starts or succeeds. */
  receiptError: string | null;
  saveState: 'idle' | 'saving' | 'saved' | 'error';
  saveError: string | null;
  /** One-shot "saved" stamp, paired with `flashFor` so it never paints over the next receipt. */
  flash: boolean;
  flashFor: string | null;
  uploadState: 'idle' | 'uploading' | 'done' | 'error';
  uploadResult: { uploaded: ReceiptUploadResult[]; failed: string | null } | null;

  setCurrentClientId: (id: string) => Promise<void>;
  loadClients: () => Promise<void>;
  createClient: (payload: ClientCreate) => Promise<Client>;
  loadClientReceipts: (clientId: string, offset?: number) => Promise<void>;
  setStatusFilter: (filter: ReceiptListStatus) => Promise<void>;
  loadReceipt: (receiptId: string) => Promise<void>;
  resetDraftFromReceipt: () => void;
  setDraftField: (key: DraftHeaderField, value: string) => void;
  addDraftLine: () => void;
  updateDraftLine: (key: string, field: DraftLineField, value: string) => void;
  removeDraftLine: (key: string) => void;
  /** Optional expected id: a save whose open receipt differs is refused without writing. */
  saveReceipt: (receiptId?: string) => Promise<ReceiptDetail>;
  rejectReceipt: () => Promise<ReceiptDetail>;
  dismissFlash: () => void;
  uploadFiles: (files: File[]) => Promise<void>;
}

/** Inbox list fetch shared by `setCurrentClientId` and `loadClientReceipts`. */
async function fetchReceipts(
  clientId: string,
  status: ReceiptListStatus,
  offset: number,
): Promise<{
  items: ReceiptListItem[];
  total: number;
  status_counts: Record<string, number>;
}> {
  const response = await listReceipts(clientId, {
    status,
    limit: DEFAULT_LIST_LIMIT,
    offset,
  });
  return {
    items: response.items,
    total: response.total,
    status_counts: response.status_counts,
  };
}

/** Failure text for the inbox error slot: ApiError detail or a plain message. */
function receiptsFailure(error: unknown): string {
  return error instanceof ApiError ? error.message : errorMessage(error);
}

/** Applies a fetched inbox page to the store. */
function applyReceiptsPage(
  set: (partial: Partial<ReceiptStoreState>) => void,
  page: { items: ReceiptListItem[]; total: number; status_counts: Record<string, number> },
  offset: number,
): void {
  set({
    receipts: page.items,
    receiptsTotal: page.total,
    statusCounts: page.status_counts,
    receiptsOffset: offset,
    receiptsLoading: false,
  });
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
  statusCounts: {},
  receiptsOffset: 0,
  statusFilter: 'ALL',
  activeReceipt: null,
  draft: null,
  draftBaseline: null,
  receiptsLoading: false,
  receiptsError: null,
  receiptLoading: false,
  receiptError: null,
  saveState: 'idle',
  saveError: null,
  flash: false,
  flashFor: null,
  uploadState: 'idle',
  uploadResult: null,

  setCurrentClientId: async (id: string) => {
    persistClientId(id);
    set({
      currentClientId: id,
      receipts: [],
      receiptsTotal: 0,
      receiptsOffset: 0,
      activeReceipt: null,
      draft: null,
      draftBaseline: null,
      receiptsLoading: true,
      receiptsError: null,
      receiptError: null,
      saveState: 'idle',
      saveError: null,
      flash: false,
      flashFor: null,
    });
    try {
      applyReceiptsPage(set, await fetchReceipts(id, get().statusFilter, 0), 0);
    } catch (error) {
      set({ receiptsError: receiptsFailure(error), receiptsLoading: false });
    }
  },

  loadClients: async () => {
    let loaded: Client[];
    try {
      loaded = await listClients();
    } catch (error) {
      // Keep the last known list: a failed refresh must not look like an empty account.
      set({ receiptsError: receiptsFailure(error) });
      return;
    }

    const current = get().currentClientId;
    if (current === null && loaded.length > 0) {
      const adopted = loaded[0].id;
      persistClientId(adopted);
      set({ clients: loaded, currentClientId: adopted, receiptsLoading: true, receiptsError: null });
      try {
        applyReceiptsPage(set, await fetchReceipts(adopted, get().statusFilter, 0), 0);
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

    set({ clients: loaded, receiptsError: null });
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
        receiptsOffset: 0,
        activeReceipt: null,
        draft: null,
        draftBaseline: null,
        receiptError: null,
        saveState: 'idle',
        saveError: null,
        flash: false,
        flashFor: null,
      });
    }
    return created;
  },

  loadClientReceipts: async (clientId: string, offset = 0) => {
    set({ receiptsLoading: true, receiptsError: null });
    try {
      applyReceiptsPage(
        set,
        await fetchReceipts(clientId, get().statusFilter, offset),
        offset,
      );
    } catch (error) {
      // Keep the current page visible; polling retries and the banner reports it.
      set({
        receiptsLoading: false,
        receiptsError: receiptsFailure(error),
      });
    }
  },

  setStatusFilter: async (filter: ReceiptListStatus) => {
    set({ statusFilter: filter, receiptsOffset: 0 });
    const current = get().currentClientId;
    if (current !== null) {
      await get().loadClientReceipts(current, 0);
    }
  },

  loadReceipt: async (receiptId: string) => {
    const clientId = get().currentClientId;
    if (clientId === null) {
      set({
        activeReceipt: null,
        draft: null,
        draftBaseline: null,
        receiptLoading: false,
        receiptError: 'No client is selected',
        saveState: 'idle',
        saveError: null,
        flash: false,
        flashFor: null,
      });
      return;
    }
    set({ receiptLoading: true, receiptError: null });
    try {
      const detail = await getReceipt(clientId, receiptId);
      const base = draftFromReceipt(detail);
      const stored = detail.status === 'STATUS_NEEDS_REVIEW' ? readDraft(receiptId) : null;
      if (stored === null) {
        clearPersistedDraft(receiptId);
      }
      const draft: ReceiptDraft = stored === null ? base : { ...base, ...stored };
      if (stored !== null) {
        persistDraftFor(receiptId, draft);
      }
      set({
        activeReceipt: detail,
        draft,
        draftBaseline: base,
        receiptLoading: false,
        receiptError: null,
        saveState: 'idle',
        saveError: null,
        flash: false,
        flashFor: null,
      });
    } catch (error) {
      // Never leave receipt A's fields under receipt B's URL.
      const message = receiptsFailure(error);
      set({
        activeReceipt: null,
        draft: null,
        draftBaseline: null,
        receiptLoading: false,
        receiptError: message,
        saveState: 'idle',
        saveError: null,
        flash: false,
        flashFor: null,
      });
      throw error instanceof ApiError ? error : new Error(message);
    }
  },

  resetDraftFromReceipt: () => {
    const receipt = get().activeReceipt;
    if (receipt === null) {
      return;
    }
    const draft = draftFromReceipt(receipt);
    set({ draft, draftBaseline: draft });
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
      line_items: draft.line_items.map((item) => {
        if (item.key !== key) {
          return item;
        }
        const next = { ...item, [field]: value };
        if (field === 'quantity' || field === 'unit_price') {
          // Keep a printed/discounted total the accountant entered; only fill
          // rows whose total still mirrors qty × unit price.
          if (lineTotalIsDerived(item)) {
            const expected = expectedLineCents(next);
            if (expected !== null) {
              next.line_total = formatCents(expected);
            }
          }
        }
        return next;
      }),
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

  saveReceipt: async (receiptId?: string) => {
    const { currentClientId, activeReceipt, draft } = get();
    // A stale caller (URL moved on, receipt closed) writes nothing and never enters 'saving'.
    if (currentClientId === null || activeReceipt === null || draft === null) {
      const message = 'No receipt is open for saving';
      set({ saveState: 'error', saveError: message, flash: false, flashFor: null });
      throw new Error(message);
    }
    if (receiptId !== undefined && activeReceipt.id !== receiptId) {
      const message = 'The open receipt changed before saving';
      set({ saveState: 'error', saveError: message, flash: false, flashFor: null });
      throw new Error(message);
    }

    set({ saveState: 'saving', saveError: null, flash: false, flashFor: null });
    try {
      await updateReceipt(currentClientId, activeReceipt.id, updateRequestFromDraft(draft));
      clearPersistedDraft(activeReceipt.id);
      const detail = await getReceipt(currentClientId, activeReceipt.id);
      const fresh = draftFromReceipt(detail);
      set({
        activeReceipt: detail,
        draft: fresh,
        draftBaseline: fresh,
        saveState: 'saved',
        saveError: null,
        flash: true,
        flashFor: detail.id,
      });
      await get().loadClientReceipts(currentClientId);
      return detail;
    } catch (error) {
      const message = receiptsFailure(error);
      set({ saveState: 'error', saveError: message });
      throw error instanceof ApiError ? error : new Error(message);
    }
  },

  rejectReceipt: async () => {
    const { currentClientId, activeReceipt } = get();
    if (currentClientId === null || activeReceipt === null) {
      const message = 'No receipt is open for rejection';
      set({ saveState: 'error', saveError: message });
      throw new Error(message);
    }

    set({ saveState: 'saving', saveError: null, flash: false, flashFor: null });
    try {
      await rejectReceiptRequest(currentClientId, activeReceipt.id);
      clearPersistedDraft(activeReceipt.id);
      const detail = await getReceipt(currentClientId, activeReceipt.id);
      const fresh = draftFromReceipt(detail);
      set({
        activeReceipt: detail,
        draft: fresh,
        draftBaseline: fresh,
        saveState: 'saved',
        saveError: null,
        flash: false,
        flashFor: null,
      });
      await get().loadClientReceipts(currentClientId);
      return detail;
    } catch (error) {
      const message = receiptsFailure(error);
      set({ saveState: 'error', saveError: message });
      throw error instanceof ApiError ? error : new Error(message);
    }
  },

  dismissFlash: () => {
    set({ flash: false, flashFor: null });
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
