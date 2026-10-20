import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useBeforeUnload, useBlocker, useNavigate, useParams } from 'react-router-dom';
import AppShell from '../components/AppShell';
import { Icon } from '../components/Icon';
import LineItemsEditor from '../components/LineItemsEditor';
import MathBanner from '../components/MathBanner';
import ReceiptCanvas from '../components/ReceiptCanvas';
import StatusPill from '../components/StatusPill';
import { getReceiptAudit } from '../api/client';
import type { ReceiptAuditEntry } from '../api/client';
import { auditMath } from '../lib/audit';
import { formatCents, formatConfidence, formatDate } from '../lib/format';
import { resolveReviewShortcut } from '../lib/reviewShortcuts';
import { useReceiptStore } from '../store/receiptStore';
import type { DraftHeaderField, ReceiptDraft } from '../types/receipt';

/** Zoom bounds mirrored by the canvas; the page owns the lifted scale value. */
const MIN_SCALE = 0.2;
const MAX_SCALE = 8;
const ZOOM_STEP = 1.25;

const EMPTY_DRAFT: ReceiptDraft = {
  merchant_name: '',
  merchant_brn: '',
  merchant_sst: '',
  invoice_date: '',
  invoice_number: '',
  subtotal: '',
  tax_amount: '',
  grand_total: '',
  line_items: [],
};

const FIELD_CLASS = 'field-input';

const NUMERIC_FIELD_CLASS = 'field-input mt-0 w-36 text-right font-mono-numbers';

const ACTION_BUTTON_CLASS = 'btn btn-secondary';

const PRIMARY_BUTTON_CLASS = 'btn btn-primary';

const DANGER_BUTTON_CLASS = 'btn btn-danger';

const SECTION_CLASS = 'border-b border-border px-5 py-6 lg:px-8';

const LABEL_CLASS = 'field-label';

/** `line_items[2]` matches the canvas's active-row convention. */
function lineFieldNameFor(index: number): string {
  return `line_items[${index}]`;
}

/** Draft identity without the generated line keys, for the dirty comparison. */
function draftSignature(draft: ReceiptDraft): string {
  return JSON.stringify({
    ...draft,
    line_items: draft.line_items.map((item) => [
      item.description,
      item.quantity,
      item.unit_price,
      item.line_total,
    ]),
  });
}

interface LabelledInputProps {
  label: string;
  field: DraftHeaderField;
  value: string;
  type?: 'text' | 'date';
  className?: string;
  onChange: (field: DraftHeaderField, value: string) => void;
  onFocus: (field: string) => void;
  onBlur: () => void;
}

function LabelledInput({
  label,
  field,
  value,
  type = 'text',
  className,
  onChange,
  onFocus,
  onBlur,
}: LabelledInputProps): JSX.Element {
  const inputId = `header-field-${field}`;
  return (
    <div className={`block ${className ?? ''}`}>
      <label htmlFor={inputId} className={LABEL_CLASS}>
        {label}
      </label>
      <input
        id={inputId}
        name={field}
        type={type}
        value={value}
        onChange={(event) => onChange(field, event.target.value)}
        onFocus={() => onFocus(field)}
        onBlur={onBlur}
        className={FIELD_CLASS}
      />
    </div>
  );
}

/**
 * SCR-03 split-screen review console: receipt viewport on the left, the
 * correction form and math audit on the right, with the accountant-only
 * keyboard workflow (Ctrl+↵ save, Alt+A add line, Alt+Backspace delete, Esc out).
 */
export default function ReviewPage(): JSX.Element {
  const { clientId, receiptId } = useParams<{ clientId: string; receiptId: string }>();
  const navigate = useNavigate();

  const activeReceipt = useReceiptStore((state) => state.activeReceipt);
  const draft = useReceiptStore((state) => state.draft);
  const receipts = useReceiptStore((state) => state.receipts);
  const receiptLoading = useReceiptStore((state) => state.receiptLoading);
  const receiptsError = useReceiptStore((state) => state.receiptsError);
  const saveState = useReceiptStore((state) => state.saveState);
  const saveError = useReceiptStore((state) => state.saveError);
  const loadReceipt = useReceiptStore((state) => state.loadReceipt);
  const setDraftField = useReceiptStore((state) => state.setDraftField);
  const addDraftLine = useReceiptStore((state) => state.addDraftLine);
  const updateDraftLine = useReceiptStore((state) => state.updateDraftLine);
  const removeDraftLine = useReceiptStore((state) => state.removeDraftLine);
  const saveReceipt = useReceiptStore((state) => state.saveReceipt);
  const rejectReceipt = useReceiptStore((state) => state.rejectReceipt);
  const draftBaseline = useReceiptStore((state) => state.draftBaseline);

  const [scale, setScale] = useState(1);
  const [activeField, setActiveField] = useState<string | null>(null);
  const clearActiveField = useCallback(() => setActiveField(null), []);
  const [focusedLineKey, setFocusedLineKey] = useState<string | null>(null);
  const [flash, setFlash] = useState(false);
  const [confirmingReject, setConfirmingReject] = useState(false);
  const [auditState, setAuditState] = useState<{
    receiptId: string | null;
    entries: ReceiptAuditEntry[];
    error: string | null;
  }>({ receiptId: null, entries: [], error: null });
  // Entries belong to the receipt that produced them; never show a previous
  // receipt's history while the next one loads.
  const auditEntries = auditState.receiptId === receiptId ? auditState.entries : [];
  const auditError = auditState.receiptId === receiptId ? auditState.error : null;
  const rejectStripRef = useRef<HTMLDivElement | null>(null);
  const rejectTriggerRef = useRef<HTMLButtonElement | null>(null);
  const rejectWasOpen = useRef(false);
  const leaveDialogRef = useRef<HTMLDialogElement | null>(null);
  const leaveTriggerRef = useRef<HTMLElement | null>(null);

  const audit = useMemo(() => auditMath(draft ?? EMPTY_DRAFT), [draft]);

  const mismatchFields = useMemo(
    () => (draft !== null && !audit.matches ? ['grand_total', 'subtotal', 'tax_amount'] : []),
    [audit.matches, draft],
  );

  // Dirty = the draft differs from server truth. A restored localStorage draft
  // is therefore correctly dirty, and a fresh load is not.
  const isDirty =
    draft !== null &&
    draftBaseline !== null &&
    draftSignature(draft) !== draftSignature(draftBaseline);

  // The navigation guards read a ref so a save can clear dirtiness right before
  // navigating, without waiting for a re-render to re-register the blocker.
  const dirtyRef = useRef(false);
  useEffect(() => {
    dirtyRef.current = isDirty;
  }, [isDirty]);

  const blocker = useBlocker(useCallback(() => dirtyRef.current, []));

  useBeforeUnload(
    useCallback((event: BeforeUnloadEvent): void => {
      if (!dirtyRef.current) {
        return;
      }
      event.preventDefault();
      event.returnValue = '';
    }, []),
  );

  const clampScale = useCallback((value: number): number => {
    return Math.min(MAX_SCALE, Math.max(MIN_SCALE, value));
  }, []);

  const onZoomIn = useCallback((): void => {
    setScale((current) => clampScale(current * ZOOM_STEP));
  }, [clampScale]);

  const onZoomOut = useCallback((): void => {
    setScale((current) => clampScale(current / ZOOM_STEP));
  }, [clampScale]);

  const onReset = useCallback((): void => {
    setScale(1);
  }, []);

  const refreshAudit = useCallback(async (): Promise<void> => {
    if (clientId === undefined || receiptId === undefined) {
      return;
    }
    try {
      const response = await getReceiptAudit(clientId, receiptId);
      setAuditState({ receiptId, entries: response.items, error: null });
    } catch (error) {
      setAuditState({
        receiptId,
        entries: [],
        error: error instanceof Error ? error.message : 'Audit history unavailable',
      });
    }
  }, [clientId, receiptId]);

  // Load the receipt; the store resets the draft and its baseline from server truth.
  useEffect(() => {
    let active = true;
    if (clientId === undefined || clientId === '' || receiptId === undefined || receiptId === '') {
      return;
    }
    loadReceipt(receiptId)
      .then(() => {
        if (active) {
          void refreshAudit();
        }
      })
      .catch(() => {
        // Load failures surface through the store's error state.
      });
    return () => {
      active = false;
    };
  }, [clientId, receiptId, loadReceipt, refreshAudit]);

  // The confirmation strip takes focus when it opens, so Escape lands on it.
  useEffect(() => {
    if (confirmingReject) {
      rejectWasOpen.current = true;
      rejectStripRef.current?.focus();
    } else if (rejectWasOpen.current) {
      rejectWasOpen.current = false;
      rejectTriggerRef.current?.focus();
    }
  }, [confirmingReject]);

  // Native modal: focus containment, inert background and Escape for free.
  useEffect(() => {
    const dialog = leaveDialogRef.current;
    if (dialog === null || blocker.state !== 'blocked') {
      return undefined;
    }
    leaveTriggerRef.current = document.activeElement as HTMLElement | null;
    if (!dialog.open) {
      dialog.showModal();
    }
    return () => {
      if (dialog.open) {
        dialog.close();
      }
      leaveTriggerRef.current?.focus();
      leaveTriggerRef.current = null;
    };
  }, [blocker.state]);

  // Saved confirmation: one-shot flash, cleared on unmount as well.
  useEffect(() => {
    if (!flash) {
      return undefined;
    }
    const timer = window.setTimeout(() => setFlash(false), 1200);
    return () => window.clearTimeout(timer);
  }, [flash]);

  const saveAndNext = useCallback(async (): Promise<void> => {
    if (clientId === undefined || receiptId === undefined || !audit.valid) {
      return;
    }
    try {
      await saveReceipt();
      dirtyRef.current = false;
      setFlash(true);
      const next = receipts.find((item) => item.status === 'STATUS_NEEDS_REVIEW' && item.id !== receiptId);
      navigate(next !== undefined ? `/clients/${clientId}/review/${next.id}` : `/clients/${clientId}/inbox`);
    } catch {
      // saveState already holds the error message.
    }
  }, [audit.valid, clientId, receiptId, receipts, saveReceipt, navigate]);

  const rejectAndNext = useCallback(async (): Promise<void> => {
    if (clientId === undefined || receiptId === undefined) {
      return;
    }
    try {
      await rejectReceipt();
      setConfirmingReject(false);
      dirtyRef.current = false;
      const next = receipts.find(
        (item) => item.status === 'STATUS_NEEDS_REVIEW' && item.id !== receiptId,
      );
      navigate(next !== undefined ? `/clients/${clientId}/review/${next.id}` : `/clients/${clientId}/inbox`);
    } catch {
      // saveState already holds the error message.
    }
  }, [clientId, receiptId, receipts, rejectReceipt, navigate]);

  // One window listener for the whole workflow; the resolver owns the bindings.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      const target = event.target;
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable);

      // The native modal owns Escape and focus while it is open.
      if (blocker.state === 'blocked') {
        return;
      }

      // An open reject confirmation owns Escape: the first press cancels it.
      if (event.key === 'Escape' && confirmingReject) {
        event.preventDefault();
        setConfirmingReject(false);
        return;
      }

      const action = resolveReviewShortcut(event, { typing, focusedLine: focusedLineKey });

      if (action === 'blur') {
        (target as HTMLElement).blur();
        return;
      }
      if (action === 'save') {
        event.preventDefault();
        void saveAndNext();
        return;
      }
      if (action === 'reject') {
        event.preventDefault();
        setConfirmingReject(true);
        return;
      }
      if (action === 'add-line') {
        event.preventDefault();
        addDraftLine();
        return;
      }
      if (action === 'delete-line') {
        event.preventDefault();
        if (focusedLineKey !== null) {
          removeDraftLine(focusedLineKey);
          setFocusedLineKey(null);
        }
        return;
      }

      if (typing || event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }

      if (event.key === '[') {
        event.preventDefault();
        onZoomOut();
      } else if (event.key === ']') {
        event.preventDefault();
        onZoomIn();
      } else if (event.key === 'r' || event.key === 'R') {
        event.preventDefault();
        onReset();
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [
    addDraftLine,
    blocker,
    confirmingReject,
    focusedLineKey,
    onReset,
    onZoomIn,
    onZoomOut,
    removeDraftLine,
    saveAndNext,
  ]);

  if (receiptLoading) {
    return (
      <AppShell clientId={clientId}>
        <div className="grid lg:h-dvh lg:grid-cols-[46fr_54fr]" role="status" aria-busy="true">
          <div className="skeleton h-[40dvh] lg:h-auto" />
          <div className="space-y-4 border-b border-border bg-surface px-5 py-6 lg:px-8">
            <div className="skeleton h-5 w-44" />
            <div className="skeleton h-10 w-full" />
            <div className="skeleton h-10 w-full" />
            <div className="skeleton h-10 w-2/3" />
          </div>
        </div>
      </AppShell>
    );
  }

  if (activeReceipt === null) {
    const message = receiptsError ?? 'Receipt not found or it may belong to another client.';
    return (
      <AppShell clientId={clientId}>
        <div className="grid min-h-[60dvh] place-items-center px-5 py-12">
          <div className="w-full max-w-md border-l-2 border-mismatch-text pl-4">
            <p className="section-label flex items-center gap-1.5 text-mismatch-text">
              <Icon name="alert" size={14} />
              Receipt unavailable
            </p>
            <p className="mt-2 text-body text-text-primary">{message}</p>
            <Link
              to={clientId === undefined ? '/clients' : `/clients/${clientId}/inbox`}
              className={`${ACTION_BUTTON_CLASS} mt-5`}
            >
              Back to inbox
            </Link>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell clientId={clientId}>
      <div className="grid lg:h-dvh lg:grid-cols-[46fr_54fr]">
        <div className="h-[40dvh] min-h-0 min-w-0 border-b border-border lg:h-auto lg:border-b-0 lg:border-r">
          {clientId !== undefined && receiptId !== undefined ? (
            <ReceiptCanvas
              clientId={clientId}
              receiptId={receiptId}
              fields={activeReceipt.fields}
              lineItems={activeReceipt.line_items}
              tokens={activeReceipt.ocr_tokens}
              activeField={activeField}
              onHoverToken={() => {}}
              mismatchFields={mismatchFields}
              processingError={activeReceipt.processing_error}
              scale={scale}
              setScale={setScale}
              onZoomIn={onZoomIn}
              onZoomOut={onZoomOut}
              onReset={onReset}
            />
          ) : null}
        </div>

        <div className="min-w-0 bg-surface lg:min-h-0 lg:overflow-y-auto">
          <div className="sticky top-14 z-10 border-b border-border bg-surface lg:top-0">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-2.5 lg:px-8">
              <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1.5">
                <Link
                  to={clientId === undefined ? '/clients' : `/clients/${clientId}/inbox`}
                  className="link-quiet"
                  title="Back to inbox without saving"
                >
                  <Icon name="arrow-left" size={15} />
                  Inbox
                </Link>
                <span className="h-4 w-px bg-border" aria-hidden="true" />
                <h1 className="font-mono-numbers text-label font-normal text-text-muted">
                  <span className="sr-only">Review receipt </span>ID: {activeReceipt.id.slice(0, 8)}
                </h1>
                <StatusPill
                  status={activeReceipt.status}
                  flags={activeReceipt.validation_flags}
                  confidence={activeReceipt.overall_confidence}
                />
              </div>
              <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
                {saveState === 'error' ? (
                  <p className="flex items-center gap-1.5 text-label text-mismatch-text">
                    <Icon name="alert" size={14} />
                    {saveError}
                  </p>
                ) : null}
                {saveState === 'saved' && flash ? (
                  <span className="stamp border-verified-border bg-verified-bg text-verified-text">
                    <Icon name="check" size={12} />
                    VERIFIED
                  </span>
                ) : null}
                {!audit.valid ? (
                  <span className="text-label text-mismatch-text" role="status">
                    Fix {audit.invalidFields[0]} before verifying.
                  </span>
                ) : null}
                <button
                  ref={rejectTriggerRef}
                  type="button"
                  className={ACTION_BUTTON_CLASS}
                  disabled={saveState === 'saving'}
                  onClick={() => setConfirmingReject(true)}
                >
                  {saveState === 'saving' ? 'Rejecting…' : 'Reject'}
                  <span className="font-mono text-micro text-text-muted" aria-hidden="true">
                    Esc
                  </span>
                </button>
                <button
                  type="button"
                  className={PRIMARY_BUTTON_CLASS}
                  disabled={saveState === 'saving' || !audit.valid}
                  onClick={() => void saveAndNext()}
                  aria-keyshortcuts="Control+Enter"
                >
                  {saveState === 'saving' ? 'Saving…' : 'Verify & Next'}
                  <span
                    className="hidden font-mono text-micro text-brand-100 sm:inline"
                    aria-hidden="true"
                  >
                    Ctrl+↵
                  </span>
                </button>
              </div>
            </div>
          </div>

          {confirmingReject ? (
            <div
              ref={rejectStripRef}
              tabIndex={-1}
              role="alertdialog"
              aria-label="Confirm rejection"
              className="flex flex-wrap items-center justify-between gap-3 border-b border-mismatch-border bg-mismatch-bg px-5 py-3 lg:px-8"
            >
              <p className="flex items-center gap-2 text-ui font-semibold text-mismatch-text">
                <Icon name="alert" size={16} />
                Reject this receipt? This cannot be undone.
              </p>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  className={ACTION_BUTTON_CLASS}
                  onClick={() => setConfirmingReject(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className={DANGER_BUTTON_CLASS}
                  disabled={saveState === 'saving'}
                  onClick={() => void rejectAndNext()}
                >
                  {saveState === 'saving' ? 'Rejecting…' : 'Reject'}
                </button>
              </div>
            </div>
          ) : null}

          <section className={SECTION_CLASS}>
            <div className="mb-4 flex items-baseline gap-3">
              <span className="section-label">01</span>
              <h2 className="section-title">Supplier &amp; date</h2>
            </div>
            <div className="grid grid-cols-1 gap-x-5 gap-y-4 sm:grid-cols-2">
              <LabelledInput
                className="sm:col-span-2"
                label="Supplier Name"
                field="merchant_name"
                value={draft?.merchant_name ?? ''}
                onChange={setDraftField}
                onFocus={setActiveField}
                onBlur={clearActiveField}
              />
              <LabelledInput
                label="Merchant SST"
                field="merchant_sst"
                value={draft?.merchant_sst ?? ''}
                onChange={setDraftField}
                onFocus={setActiveField}
                onBlur={clearActiveField}
              />
              <LabelledInput
                label="Invoice Date"
                field="invoice_date"
                type="date"
                value={draft?.invoice_date ?? ''}
                onChange={setDraftField}
                onFocus={setActiveField}
                onBlur={clearActiveField}
              />
              <LabelledInput
                label="Invoice Number"
                field="invoice_number"
                value={draft?.invoice_number ?? ''}
                onChange={setDraftField}
                onFocus={setActiveField}
                onBlur={clearActiveField}
              />
              <LabelledInput
                label="Merchant BRN"
                field="merchant_brn"
                value={draft?.merchant_brn ?? ''}
                onChange={setDraftField}
                onFocus={setActiveField}
                onBlur={clearActiveField}
              />
            </div>
          </section>

          <section className={SECTION_CLASS}>
            <div className="mb-4 flex items-baseline gap-3">
              <span className="section-label">02</span>
              <h2 className="section-title">Line items</h2>
            </div>
            <LineItemsEditor
              items={draft?.line_items ?? []}
              serverLineItems={activeReceipt.line_items}
              activeKey={focusedLineKey}
              onChange={updateDraftLine}
              onRemove={removeDraftLine}
              onAdd={addDraftLine}
              onFocusRow={(key) => {
                setFocusedLineKey(key);
                const index = draft?.line_items.findIndex((item) => item.key === key) ?? -1;
                if (index >= 0) {
                  setActiveField(lineFieldNameFor(index));
                }
              }}
            />
          </section>

          <section className="px-5 py-6 lg:px-8">
            <div className="mb-4 flex items-baseline gap-3">
              <span className="section-label">03</span>
              <h2 className="section-title">Totals &amp; audit</h2>
            </div>

            <div className="ml-auto grid w-full max-w-md gap-2">
              <label className="flex items-center justify-between gap-3">
                <span className={LABEL_CLASS}>Subtotal</span>
                <span className="flex items-center gap-1.5">
                  <span className="font-mono text-micro text-text-muted" aria-hidden="true">
                    RM
                  </span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={draft?.subtotal ?? ''}
                    onChange={(event) => setDraftField('subtotal', event.target.value)}
                    onFocus={() => setActiveField('subtotal')}
                    onBlur={clearActiveField}
                    className={NUMERIC_FIELD_CLASS}
                  />
                </span>
              </label>
              <label className="flex items-center justify-between gap-3">
                <span className={LABEL_CLASS}>SST (6%)</span>
                <span className="flex items-center gap-1.5">
                  <span className="font-mono text-micro text-text-muted" aria-hidden="true">
                    RM
                  </span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={draft?.tax_amount ?? ''}
                    onChange={(event) => setDraftField('tax_amount', event.target.value)}
                    onFocus={() => setActiveField('tax_amount')}
                    onBlur={clearActiveField}
                    className={NUMERIC_FIELD_CLASS}
                  />
                </span>
              </label>
              <label className="rule-total flex items-center justify-between gap-3 pt-2">
                <span className={LABEL_CLASS}>Grand Total</span>
                <span className="flex items-center gap-1.5">
                  <span className="font-mono text-micro text-text-muted" aria-hidden="true">
                    RM
                  </span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={draft?.grand_total ?? ''}
                    onChange={(event) => setDraftField('grand_total', event.target.value)}
                    onFocus={() => setActiveField('grand_total')}
                    onBlur={clearActiveField}
                    className="field-input mt-0 w-36 text-right font-mono-numbers text-[22px]"
                  />
                </span>
              </label>
            </div>

            <dl className="ml-auto mt-4 w-full max-w-md space-y-1 border-t border-border pt-3">
              <div className="flex items-center justify-between gap-3">
                <dt className="text-label text-text-muted">Line Items Total</dt>
                <dd className="font-mono-numbers text-label text-text-secondary">
                  RM {formatCents(audit.lineCents)}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-label text-text-muted">Confidence</dt>
                <dd className="font-mono-numbers text-label text-text-secondary">
                  {formatConfidence(activeReceipt.overall_confidence)}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-label text-text-muted">Lines + Tax = Total</dt>
                <dd className="font-mono-numbers text-label text-text-muted">
                  {formatCents(audit.lineCents)} + {formatCents(audit.taxCents)} ={' '}
                  {formatCents(audit.totalCents)}
                </dd>
              </div>
            </dl>

            <div className="mt-4">
              <MathBanner audit={audit} missingSst={audit.missingSstOnRegisteredMerchant} dirty={isDirty} />
            </div>

            <details className="mt-5 border-t border-border">
              <summary className="section-label cursor-pointer py-3">Audit history</summary>
              {auditError !== null ? (
                <p className="border-t border-border py-2 text-label text-mismatch-text">{auditError}</p>
              ) : auditEntries.length === 0 ? (
                <p className="border-t border-border py-2 text-label text-text-muted">
                  No changes recorded yet.
                </p>
              ) : (
                <ul className="max-h-64 divide-y divide-border overflow-y-auto border-t border-border">
                  {auditEntries.map((entry) => (
                    <li key={entry.id} className="py-2 text-label text-text-secondary">
                      <span className="font-medium text-text-primary">{entry.field_name}</span>{' '}
                      <span className="font-mono-numbers">
                        {entry.old_value ?? '—'} → {entry.new_value ?? '—'}
                      </span>
                      <span className="mt-0.5 block text-text-muted">
                        {entry.user_id.slice(0, 8)} · {formatDate(entry.created_at)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </details>
          </section>
        </div>

        <dialog
          ref={leaveDialogRef}
          role="alertdialog"
          aria-labelledby="leave-dialog-title"
          className="m-auto w-[calc(100%_-_3rem)] max-w-sm p-5"
          onCancel={(event) => {
            event.preventDefault();
            if (blocker.state === 'blocked') blocker.reset();
          }}
        >
          <h2 id="leave-dialog-title" className="section-title">
            Leave without saving?
          </h2>
          <p className="mt-2 text-ui text-text-secondary">
            Your corrections on this receipt will be lost.
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              className={ACTION_BUTTON_CLASS}
              onClick={() => {
                if (blocker.state === 'blocked') blocker.reset();
              }}
            >
              Stay
            </button>
            <button
              type="button"
              className={PRIMARY_BUTTON_CLASS}
              onClick={() => {
                dirtyRef.current = false;
                if (blocker.state === 'blocked') blocker.proceed();
              }}
            >
              Leave
            </button>
          </div>
        </dialog>
      </div>
    </AppShell>
  );
}
