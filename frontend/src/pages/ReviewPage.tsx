import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import LineItemsEditor from '../components/LineItemsEditor';
import MathBanner from '../components/MathBanner';
import ReceiptCanvas from '../components/ReceiptCanvas';
import StatusPill from '../components/StatusPill';
import { auditMath } from '../lib/audit';
import { formatCents, formatConfidence } from '../lib/format';
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

const FIELD_CLASS =
  'mt-1 h-9 w-full border border-border bg-surface px-2 text-sm text-text-primary focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none';

const NUMERIC_FIELD_CLASS = `${FIELD_CLASS} text-right font-mono-numbers`;

const ACTION_BUTTON_CLASS =
  'inline-flex h-11 items-center border border-border bg-surface px-3 text-sm font-medium text-text-primary transition-colors duration-100 ease-out hover:bg-surface-subtle focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-text-muted';

const PRIMARY_BUTTON_CLASS =
  'inline-flex h-11 items-center border border-brand-900 bg-brand-900 px-3 text-sm font-semibold text-white transition-colors duration-100 ease-out hover:bg-brand-700 focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-text-muted';

const SECTION_CLASS = 'border-b border-border px-4 py-3';

const LABEL_CLASS = 'block text-xs uppercase tracking-wide text-text-muted';

/** `line_items[2]` matches the canvas's active-row convention. */
function lineFieldNameFor(index: number): string {
  return `line_items[${index}]`;
}

interface LabelledInputProps {
  label: string;
  field: DraftHeaderField;
  value: string;
  type?: 'text' | 'date';
  onChange: (field: DraftHeaderField, value: string) => void;
  onFocus: (field: string) => void;
  onBlur: () => void;
}

function LabelledInput({
  label,
  field,
  value,
  type = 'text',
  onChange,
  onFocus,
  onBlur,
}: LabelledInputProps): JSX.Element {
  const inputId = `header-field-${field}`;
  return (
    <div className="block">
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
 * keyboard workflow (⌘↵ save, Alt+A add line, Alt+Backspace delete, Esc out).
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

  const [scale, setScale] = useState(1);
  const [activeField, setActiveField] = useState<string | null>(null);
  const [focusedLineKey, setFocusedLineKey] = useState<string | null>(null);
  const [flash, setFlash] = useState(false);
  const [baseline, setBaseline] = useState<string | null>(null);

  const audit = useMemo(() => auditMath(draft ?? EMPTY_DRAFT), [draft]);

  const mismatchFields = useMemo(
    () => (draft !== null && !audit.matches ? ['grand_total', 'subtotal', 'tax_amount'] : []),
    [audit.matches, draft],
  );

  // Dirty = the current draft differs from the one the receipt shipped with.
  const isDirty =
    draft !== null && baseline !== null && JSON.stringify(draft) !== baseline;

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

  // Load the receipt and capture the clean baseline once per receipt; the
  // async continuation is the right place for the reset (not the effect body).
  useEffect(() => {
    let active = true;
    if (clientId === undefined || clientId === '' || receiptId === undefined || receiptId === '') {
      return;
    }
    loadReceipt(receiptId)
      .then(() => {
        if (!active) {
          return;
        }
        const loaded = useReceiptStore.getState().draft;
        setBaseline(loaded === null ? null : JSON.stringify(loaded));
      })
      .catch(() => {
        // Load failures surface through the store's error state.
      });
    return () => {
      active = false;
    };
  }, [clientId, receiptId, loadReceipt]);

  // Saved confirmation: one-shot flash, cleared on unmount as well.
  useEffect(() => {
    if (!flash) {
      return undefined;
    }
    const timer = window.setTimeout(() => setFlash(false), 1200);
    return () => window.clearTimeout(timer);
  }, [flash]);

  const saveAndNext = useCallback(async (): Promise<void> => {
    if (clientId === undefined || receiptId === undefined) {
      return;
    }
    try {
      await saveReceipt();
      setFlash(true);
      const next = receipts.find((item) => item.status === 'STATUS_NEEDS_REVIEW' && item.id !== receiptId);
      navigate(next !== undefined ? `/clients/${clientId}/review/${next.id}` : `/clients/${clientId}/inbox`);
    } catch {
      // saveState already holds the error message.
    }
  }, [clientId, receiptId, receipts, saveReceipt, navigate]);

  // One window listener for the whole workflow.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      const target = event.target;
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable);

      if (event.metaKey || event.ctrlKey) {
        if (event.key === 'Enter') {
          event.preventDefault();
          void saveAndNext();
        }
        return;
      }

      if (event.altKey) {
        if (event.key === 'a' || event.key === 'A') {
          event.preventDefault();
          addDraftLine();
          return;
        }
        if (event.key === 'Backspace') {
          if (focusedLineKey !== null) {
            event.preventDefault();
            removeDraftLine(focusedLineKey);
            setFocusedLineKey(null);
          }
          return;
        }
      }

      if (event.key === 'Escape') {
        event.preventDefault();
        if (clientId !== undefined) {
          navigate(`/clients/${clientId}/inbox`);
        }
        return;
      }

      if (typing) {
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
    clientId,
    focusedLineKey,
    navigate,
    onReset,
    onZoomIn,
    onZoomOut,
    removeDraftLine,
    saveAndNext,
  ]);

  if (receiptLoading) {
    return (
      <div className="grid h-dvh grid-cols-2" role="status" aria-busy="true">
        <div className="animate-pulse bg-surface-subtle" />
        <div className="animate-pulse bg-surface-subtle" />
      </div>
    );
  }

  if (activeReceipt === null) {
    const message = receiptsError ?? 'Receipt not found or it may belong to another client.';
    return (
      <div className="grid h-dvh place-items-center bg-canvas p-6">
        <div className="w-full max-w-md border border-mismatch-border bg-mismatch-bg px-4 py-6 text-center">
          <p className="text-sm font-medium text-mismatch-text">{message}</p>
          <Link
            to={clientId === undefined ? '/clients' : `/clients/${clientId}/inbox`}
            className={`${ACTION_BUTTON_CLASS} mt-4`}
          >
            Back to inbox
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="grid h-dvh grid-cols-2">
      <div className="min-w-0 border-r border-border">
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

      <div className="min-h-0 min-w-0 overflow-y-auto">
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-border bg-surface px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="font-mono-numbers text-xs text-text-muted">
              ID: {activeReceipt.id.slice(0, 8)}
            </span>
            <StatusPill
              status={activeReceipt.status}
              flags={activeReceipt.validation_flags}
              confidence={activeReceipt.overall_confidence}
            />
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              className={ACTION_BUTTON_CLASS}
              onClick={() =>
                navigate(clientId === undefined ? '/clients' : `/clients/${clientId}/inbox`)
              }
            >
              Reject (Esc)
            </button>
            {saveState === 'error' ? (
              <div className="border border-mismatch-border bg-mismatch-bg px-2 py-1 text-xs text-mismatch-text">
                {saveError}
              </div>
            ) : null}
            {saveState === 'saved' && flash ? (
              <span className="inline-flex h-11 items-center border border-verified-border bg-verified-bg px-2 text-xs font-medium text-verified-text">
                <span aria-hidden="true">✓</span> Verified
              </span>
            ) : null}
            <button
              type="button"
              className={PRIMARY_BUTTON_CLASS}
              disabled={saveState === 'saving'}
              onClick={() => void saveAndNext()}
            >
              {saveState === 'saving' ? 'Saving…' : 'Verify & Next (⌘↵)'}
            </button>
          </div>
        </div>

        <section className={SECTION_CLASS}>
          <h2 className="mb-2 text-sm font-semibold text-text-primary">Merchant &amp; Date</h2>
          <div className="grid grid-cols-2 gap-3">
            <LabelledInput
              label="Supplier Name"
              field="merchant_name"
              value={draft?.merchant_name ?? ''}
              onChange={setDraftField}
              onFocus={setActiveField}
              onBlur={() => setActiveField(null)}
            />
            <LabelledInput
              label="BRN / SST Number"
              field="merchant_sst"
              value={draft?.merchant_sst ?? ''}
              onChange={setDraftField}
              onFocus={setActiveField}
              onBlur={() => setActiveField(null)}
            />
            <LabelledInput
              label="Invoice Date"
              field="invoice_date"
              type="date"
              value={draft?.invoice_date ?? ''}
              onChange={setDraftField}
              onFocus={setActiveField}
              onBlur={() => setActiveField(null)}
            />
            <LabelledInput
              label="Invoice Number"
              field="invoice_number"
              value={draft?.invoice_number ?? ''}
              onChange={setDraftField}
              onFocus={setActiveField}
              onBlur={() => setActiveField(null)}
            />
            <LabelledInput
              label="Merchant BRN"
              field="merchant_brn"
              value={draft?.merchant_brn ?? ''}
              onChange={setDraftField}
              onFocus={setActiveField}
              onBlur={() => setActiveField(null)}
            />
          </div>
        </section>

        <section className={SECTION_CLASS}>
          <h2 className="mb-2 text-sm font-semibold text-text-primary">Line Items</h2>
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

        <section className={SECTION_CLASS}>
          <h2 className="mb-2 text-sm font-semibold text-text-primary">Totals &amp; Tax Audit</h2>
          <div className="grid grid-cols-3 gap-3">
            <label className="block">
              <span className={LABEL_CLASS}>Subtotal</span>
              <input
                type="text"
                inputMode="decimal"
                value={draft?.subtotal ?? ''}
                onChange={(event) => setDraftField('subtotal', event.target.value)}
                onFocus={() => setActiveField('subtotal')}
                onBlur={() => setActiveField(null)}
                className={NUMERIC_FIELD_CLASS}
              />
            </label>
            <label className="block">
              <span className={LABEL_CLASS}>SST (6%)</span>
              <input
                type="text"
                inputMode="decimal"
                value={draft?.tax_amount ?? ''}
                onChange={(event) => setDraftField('tax_amount', event.target.value)}
                onFocus={() => setActiveField('tax_amount')}
                onBlur={() => setActiveField(null)}
                className={NUMERIC_FIELD_CLASS}
              />
            </label>
            <label className="block">
              <span className={LABEL_CLASS}>Grand Total</span>
              <input
                type="text"
                inputMode="decimal"
                value={draft?.grand_total ?? ''}
                onChange={(event) => setDraftField('grand_total', event.target.value)}
                onFocus={() => setActiveField('grand_total')}
                onBlur={() => setActiveField(null)}
                className={NUMERIC_FIELD_CLASS}
              />
            </label>
          </div>

          <dl className="mt-3 flex items-center justify-between border border-border bg-surface-subtle px-3 py-2">
            <dt className="text-xs uppercase tracking-wide text-text-muted">Line Items Total</dt>
            <dd className="font-mono-numbers text-sm text-text-primary">
              RM {formatCents(audit.lineCents)}
            </dd>
          </dl>

          <p className="mt-2 font-mono-numbers text-xs text-text-muted">
            Confidence {formatConfidence(activeReceipt.overall_confidence)} · Lines{' '}
            {formatCents(audit.lineCents)} + Tax {formatCents(audit.taxCents)} = Total{' '}
            {formatCents(audit.totalCents)}
          </p>

          <div className="mt-2">
            <MathBanner audit={audit} missingSst={audit.missingSstOnRegisteredMerchant} dirty={isDirty} />
          </div>
        </section>
      </div>
    </div>
  );
}
