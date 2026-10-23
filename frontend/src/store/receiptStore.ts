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
  ReceiptUpdateResponse,
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

/**
 * Monotonic token for inbox fetches. Each fetch captures `++requestSeq` and only
 * paints when it is still the newest, so a late response for a previous
 * workspace or tab can never overwrite the rows currently on screen.
 */
let requestSeq = 0;

/**
 * Monotonic token for client-list fetches. Only the newest `loadClients` may
 * paint, so a slow refresh cannot replace a newer list.
 */
let clientsRequestSeq = 0;

/**
 * Bumped by `resetWorkspace`. Late client-list or client-creation work started
 * in the signed-out workspace must not repopulate it or adopt a client.
 */
let workspaceEpoch = 0;

/**
 * Monotonic token for the active receipt view. A detail load, save, reject or
 * workspace switch bumps it; an async response captured under an older token
 * must not paint over the receipt that is now on screen.
 */
let receiptContextSeq = 0;

/**
 * The review save currently writing, if any. A duplicate save for the same
 * receipt awaits this promise — one PUT, one shared result — while a save for a
 * different receipt is refused instead of queued behind it.
 */
let inFlightSave: {
  receiptId: string;
  clientId: string;
  promise: Promise<ReceiptDetail>;
} | null = null;

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

/** Forgets the persisted client id; storage failures are swallowed. */
function clearStoredClientId(): void {
  try {
    window.localStorage.removeItem(CURRENT_CLIENT_ID_KEY);
  } catch {
    // Sign-out must proceed even when storage is unavailable.
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
      rounding: candidate.rounding ?? '',
      amount_basis: candidate.amount_basis ?? null,
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
    rounding: receipt.rounding === null ? '' : String(receipt.rounding),
    amount_basis: receipt.amount_basis ?? null,
    line_items: receipt.line_items.map((item, index) => ({
      key: crypto.randomUUID(),
      source_index: index,
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
    rounding: nullIfBlank(draft.rounding),
    amount_basis: draft.amount_basis,
    line_items,
  };
}

/** SCR-02 inbox + SCR-03 review console state. */
export interface ReceiptStoreState {
  currentClientId: string | null;
  clients: Client[];
  /** Client list load state, kept separate from the inbox's own flags. */
  clientsLoading: boolean;
  /** Why the last client list load failed; never shared with `receiptsError`. */
  clientsError: string | null;
  receipts: ReceiptListItem[];
  receiptsTotal: number;
  /** Counts per inbox filter bucket, fetched with the list. */
  statusCounts: Record<string, number>;
  receiptsOffset: number;
  /** Page size the current list came back with, as reported by the server. */
  receiptsLimit: number;
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
  /** Clears the workspace (sign-out): persisted id plus all per-client state. */
  resetWorkspace: () => void;
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
  /**
   * Re-read the batch rows' real statuses from the server (M2). The upload page
   * has no pipeline of its own, so without this its rows stayed "Processing"
   * forever even after the backend had settled them.
   */
  refreshUploadStatuses: () => Promise<void>;
}

/** Inbox list fetch shared by `setCurrentClientId` and `loadClientReceipts`. */
async function fetchReceipts(
  clientId: string,
  status: ReceiptListStatus,
  offset: number,
): Promise<{
  items: ReceiptListItem[];
  total: number;
  limit: number;
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
    limit: response.limit,
    status_counts: response.status_counts,
  };
}

/** Failure text for the store's error slots: ApiError detail or a plain message. */
function failureMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : errorMessage(error);
}

/** Applies a fetched inbox page to the store. */
function applyReceiptsPage(
  set: (partial: Partial<ReceiptStoreState>) => void,
  page: {
    items: ReceiptListItem[];
    total: number;
    limit: number;
    status_counts: Record<string, number>;
  },
  offset: number,
): void {
  set({
    receipts: page.items,
    receiptsTotal: page.total,
    statusCounts: page.status_counts,
    receiptsOffset: offset,
    receiptsLimit: page.limit,
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
  clientsLoading: false,
  clientsError: null,
  receipts: [],
  receiptsTotal: 0,
  statusCounts: {},
  receiptsOffset: 0,
  receiptsLimit: DEFAULT_LIST_LIMIT,
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
    // Anything still in flight belongs to the previous workspace.
    const seq = ++requestSeq;
    // A detail load or save for the previous workspace must not paint here.
    receiptContextSeq += 1;
    const status = get().statusFilter;
    set({
      currentClientId: id,
      receipts: [],
      receiptsTotal: 0,
      // The tab counts belong to the previous workspace (L4). Leaving them in
      // place shows the old client's badges against the new client's empty
      // list until the first fetch lands.
      statusCounts: {},
      receiptsOffset: 0,
      activeReceipt: null,
      draft: null,
      draftBaseline: null,
      receiptsLoading: true,
      receiptsError: null,
      receiptLoading: false,
      receiptError: null,
      saveState: 'idle',
      saveError: null,
      flash: false,
      flashFor: null,
      uploadState: 'idle',
      uploadResult: null,
    });
    try {
      const page = await fetchReceipts(id, status, 0);
      if (seq !== requestSeq) {
        return;
      }
      applyReceiptsPage(set, page, 0);
    } catch (error) {
      if (seq !== requestSeq) {
        return;
      }
      set({ receiptsError: failureMessage(error), receiptsLoading: false });
    }
  },

  resetWorkspace: () => {
    clearStoredClientId();
    // Abandon in-flight inbox, client-list and receipt-detail work so a late
    // response cannot repaint or adopt anything after sign-out.
    requestSeq += 1;
    clientsRequestSeq += 1;
    workspaceEpoch += 1;
    receiptContextSeq += 1;
    set({
      currentClientId: null,
      clients: [],
      clientsLoading: false,
      clientsError: null,
      receipts: [],
      receiptsTotal: 0,
      receiptsOffset: 0,
      receiptsLimit: DEFAULT_LIST_LIMIT,
      statusCounts: {},
      statusFilter: 'ALL',
      receiptsLoading: false,
      receiptsError: null,
      activeReceipt: null,
      draft: null,
      draftBaseline: null,
      receiptLoading: false,
      receiptError: null,
      saveState: 'idle',
      saveError: null,
      flash: false,
      flashFor: null,
      uploadState: 'idle',
      uploadResult: null,
    });
  },

  loadClients: async () => {
    const seq = ++clientsRequestSeq;
    const epoch = workspaceEpoch;
    set({ clientsLoading: true, clientsError: null });
    let loaded: Client[];
    try {
      loaded = await listClients();
    } catch (error) {
      if (seq !== clientsRequestSeq || epoch !== workspaceEpoch) {
        return;
      }
      // Keep the last known list: a failed refresh must not look like an empty
      // account, and the inbox's own error slot is none of this call's business.
      set({ clientsLoading: false, clientsError: failureMessage(error) });
      return;
    }
    if (seq !== clientsRequestSeq || epoch !== workspaceEpoch) {
      return;
    }

    const current = get().currentClientId;
    set({ clients: loaded, clientsLoading: false });
    if (current === null && loaded.length > 0) {
      // Adopting the first workspace is a workspace switch: let the one action
      // that owns receipt loading (and its error slot) run it.
      await get().setCurrentClientId(loaded[0].id);
    }
  },

  createClient: async (payload: ClientCreate) => {
    const epoch = workspaceEpoch;
    const created = await createClientRequest(payload);
    if (epoch !== workspaceEpoch) {
      // Signed out while the request was in flight: never adopt into the new
      // (empty) workspace or leak the created client into its list.
      return created;
    }
    set({ clients: [...get().clients, created] });
    if (get().currentClientId === null) {
      persistClientId(created.id);
      // The adoption is a workspace switch: drop any receipt work in flight.
      requestSeq += 1;
      receiptContextSeq += 1;
      set({
        currentClientId: created.id,
        receipts: [],
        receiptsTotal: 0,
        receiptsOffset: 0,
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
      });
    }
    return created;
  },

  loadClientReceipts: async (clientId: string, offset = 0) => {
    const seq = ++requestSeq;
    set({ receiptsLoading: true, receiptsError: null });
    try {
      const page = await fetchReceipts(clientId, get().statusFilter, offset);
      if (seq !== requestSeq) {
        return;
      }
      if (get().currentClientId !== null && get().currentClientId !== clientId) {
        // The workspace switched while this page was in flight: those rows
        // belong to another client and must not paint here. Deep links that
        // have not adopted a workspace yet (`null`) still render.
        set({ receiptsLoading: false });
        return;
      }
      applyReceiptsPage(set, page, offset);
    } catch (error) {
      if (seq !== requestSeq) {
        return;
      }
      if (get().currentClientId !== null && get().currentClientId !== clientId) {
        set({ receiptsLoading: false });
        return;
      }
      // Keep the current page visible; polling retries and the banner reports it.
      set({
        receiptsLoading: false,
        receiptsError: failureMessage(error),
      });
    }
  },

  setStatusFilter: async (filter: ReceiptListStatus) => {
    const current = get().currentClientId;
    if (current === null) {
      set({ statusFilter: filter, receiptsOffset: 0, receiptsLoading: false });
      return;
    }
    const seq = ++requestSeq;
    set({
      statusFilter: filter,
      receiptsOffset: 0,
      receiptsLoading: true,
      receiptsError: null,
    });
    try {
      const page = await fetchReceipts(current, filter, 0);
      if (seq !== requestSeq) {
        return;
      }
      applyReceiptsPage(set, page, 0);
    } catch (error) {
      if (seq !== requestSeq) {
        return;
      }
      // The previous tab's rows belong to a different filter: drop them rather
      // than label them with the tab that just failed. Counts are per-status and
      // stay valid, so they survive.
      set({
        receipts: [],
        receiptsTotal: 0,
        receiptsLoading: false,
        receiptsError: failureMessage(error),
      });
    }
  },

  loadReceipt: async (receiptId: string) => {
    const context = ++receiptContextSeq;
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
      if (context !== receiptContextSeq || get().currentClientId !== clientId) {
        // A newer load, save, reject or workspace switch owns the view now.
        return;
      }
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
      if (context !== receiptContextSeq || get().currentClientId !== clientId) {
        return;
      }
      // Never leave receipt A's fields under receipt B's URL.
      const message = failureMessage(error);
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
    const requestedId = receiptId ?? activeReceipt.id;
    // A duplicate Ctrl+Enter for this receipt joins the write already running;
    // a save for any other receipt is refused rather than queued behind it.
    const running = inFlightSave;
    if (running !== null) {
      if (running.clientId === currentClientId && running.receiptId === requestedId) {
        return running.promise;
      }
      throw new Error('A save is already in progress for another receipt');
    }

    if (activeReceipt.id !== requestedId) {
      const message = 'The open receipt changed before saving';
      set({ saveState: 'error', saveError: message, flash: false, flashFor: null });
      throw new Error(message);
    }

    const savedClientId = currentClientId;
    const savedReceipt = activeReceipt;
    const savedId = activeReceipt.id;
    const submittedDraft = draft;
    // This save owns the receipt view until something newer (a load, another
    // save/reject, or a workspace switch) bumps the token.
    const context = ++receiptContextSeq;

    const operation = (async (): Promise<ReceiptDetail> => {
      set({ saveState: 'saving', saveError: null, flash: false, flashFor: null });
      let ack: ReceiptUpdateResponse;
      try {
        ack = await updateReceipt(savedClientId, savedId, updateRequestFromDraft(submittedDraft));
      } catch (error) {
        const message = failureMessage(error);
        if (
          context === receiptContextSeq &&
          get().currentClientId === savedClientId &&
          get().activeReceipt?.id === savedId
        ) {
          set({ saveState: 'error', saveError: message });
        }
        throw error instanceof ApiError ? error : new Error(message);
      }

      // The PUT committed: from here a failed confirming read must not report
      // the save as failed, and the persisted draft has served its purpose.
      clearPersistedDraft(savedId);
      // The ack carries only status/discrepancy; `verified_at` and the rest of
      // ReceiptDetail stay as loaded, never synthesised from `updated_at`.
      const committed: ReceiptDetail = {
        ...savedReceipt,
        status: ack.status,
        math_discrepancy: ack.math_discrepancy,
      };
      if (
        context !== receiptContextSeq ||
        get().currentClientId !== savedClientId ||
        get().activeReceipt !== savedReceipt
      ) {
        // The view moved on while the PUT was in flight: the write happened,
        // but its state belongs to a receipt/workspace no longer on screen.
        return committed;
      }

      // Keep edits typed after the PUT started; the store's draft object is
      // replaced on every keystroke, so a different reference means newer text.
      const liveDraft = get().draft;
      const editedAfterPut = liveDraft !== null && liveDraft !== submittedDraft ? liveDraft : null;
      const paintedDraft = editedAfterPut ?? submittedDraft;
      set({
        activeReceipt: committed,
        draft: paintedDraft,
        draftBaseline: submittedDraft,
        saveState: 'saved',
        saveError: null,
        flash: true,
        flashFor: committed.id,
      });
      if (editedAfterPut !== null) {
        persistDraftFor(savedId, editedAfterPut);
      }

      let saved = committed;
      try {
        const confirmed = await getReceipt(savedClientId, savedId);
        if (
          context !== receiptContextSeq ||
          get().currentClientId !== savedClientId ||
          get().activeReceipt !== committed
        ) {
          return committed;
        }
        const confirmedDraft = draftFromReceipt(confirmed);
        // Anything typed after the PUT started is still unsaved; the server
        // response must not silently discard it.
        const liveAfterConfirm = get().draft;
        const editedAfterConfirm =
          liveAfterConfirm !== null && liveAfterConfirm !== submittedDraft ? liveAfterConfirm : null;
        set({
          activeReceipt: confirmed,
          draft: editedAfterConfirm ?? confirmedDraft,
          draftBaseline: confirmedDraft,
        });
        if (editedAfterConfirm !== null) {
          persistDraftFor(savedId, editedAfterConfirm);
        }
        saved = confirmed;
      } catch {
        // Keep the committed PUT result rather than inventing detail fields.
      }
      if (context === receiptContextSeq && get().currentClientId === savedClientId) {
        await get().loadClientReceipts(savedClientId, get().receiptsOffset);
      }
      return saved;
    })();

    inFlightSave = {
      clientId: savedClientId,
      receiptId: savedId,
      promise: operation,
    };
    try {
      return await operation;
    } finally {
      if (inFlightSave?.promise === operation) {
        inFlightSave = null;
      }
    }
  },

  rejectReceipt: async () => {
    const { currentClientId, activeReceipt } = get();
    if (currentClientId === null || activeReceipt === null) {
      const message = 'No receipt is open for rejection';
      set({ saveState: 'error', saveError: message });
      throw new Error(message);
    }
    // Rejecting while this receipt's PUT is still writing would race the save's
    // status write and its confirmation read: refuse instead of interleaving.
    const running = inFlightSave;
    if (running !== null && running.clientId === currentClientId && running.receiptId === activeReceipt.id) {
      throw new Error('A save is already in progress for this receipt');
    }

    const rejectedClientId = currentClientId;
    const rejectedReceipt = activeReceipt;
    const rejectedId = activeReceipt.id;
    const context = ++receiptContextSeq;
    set({ saveState: 'saving', saveError: null, flash: false, flashFor: null });

    let ack: ReceiptUpdateResponse;
    try {
      ack = await rejectReceiptRequest(rejectedClientId, rejectedId);
    } catch (error) {
      const message = failureMessage(error);
      if (
        context === receiptContextSeq &&
        get().currentClientId === rejectedClientId &&
        get().activeReceipt?.id === rejectedId
      ) {
        set({ saveState: 'error', saveError: message });
      }
      throw error instanceof ApiError ? error : new Error(message);
    }

    // The POST committed: the persisted draft is obsolete even if the
    // confirming read below fails.
    clearPersistedDraft(rejectedId);
    const committed: ReceiptDetail = {
      ...rejectedReceipt,
      status: ack.status,
      math_discrepancy: ack.math_discrepancy,
    };
    if (
      context !== receiptContextSeq ||
      get().currentClientId !== rejectedClientId ||
      get().activeReceipt !== rejectedReceipt
    ) {
      return committed;
    }
    set({
      activeReceipt: committed,
      saveState: 'saved',
      saveError: null,
      flash: false,
      flashFor: null,
    });

    let saved = committed;
    try {
      const detail = await getReceipt(rejectedClientId, rejectedId);
      if (
        context !== receiptContextSeq ||
        get().currentClientId !== rejectedClientId ||
        get().activeReceipt !== committed
      ) {
        return committed;
      }
      const fresh = draftFromReceipt(detail);
      set({ activeReceipt: detail, draft: fresh, draftBaseline: fresh });
      saved = detail;
    } catch {
      if (
        context === receiptContextSeq &&
        get().currentClientId === rejectedClientId &&
        get().activeReceipt === committed
      ) {
        // The rejection succeeded; drop the stale draft even though the
        // confirming read failed, rather than reporting the reject as failed.
        const fresh = draftFromReceipt(committed);
        set({ draft: fresh, draftBaseline: fresh });
      }
    }
    if (context === receiptContextSeq && get().currentClientId === rejectedClientId) {
      await get().loadClientReceipts(rejectedClientId, get().receiptsOffset);
    }
    return saved;
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
      await get().loadClientReceipts(clientId, get().receiptsOffset);
    } catch (error) {
      set({
        uploadState: 'error',
        uploadResult: { uploaded: [], failed: `Batch rejected: ${failureMessage(error)}` },
      });
    }
  },

  refreshUploadStatuses: async () => {
    const { currentClientId, uploadResult } = get();
    if (currentClientId === null || uploadResult === null) {
      return;
    }
    if (uploadResult.uploaded.length === 0) {
      return;
    }
    try {
      // One list request covers the whole batch: the rows were just created, so
      // they are on the first page. Polling per receipt would multiply the load
      // by the batch size for no extra information.
      const page = await listReceipts(currentClientId, {
        status: 'ALL',
        limit: Math.max(DEFAULT_LIST_LIMIT, uploadResult.uploaded.length),
        offset: 0,
      });
      const byId = new Map(page.items.map((item) => [item.id, item]));
      // Drop the update if the workspace changed while the request was in
      // flight, or the user cleared the result.
      if (get().currentClientId !== currentClientId) {
        return;
      }
      const latest = get().uploadResult;
      if (latest === null) {
        return;
      }
      set({
        uploadResult: {
          ...latest,
          uploaded: latest.uploaded.map((item) => {
            const fresh = byId.get(item.id);
            if (fresh === undefined) {
              return item;
            }
            return {
              ...item,
              status: fresh.status,
              error: fresh.processing_error ?? item.error,
            };
          }),
        },
      });
    } catch {
      // A transient poll failure must not turn a completed upload into an
      // error state; the next tick retries.
    }
  },
}));
