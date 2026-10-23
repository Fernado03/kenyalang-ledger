import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  downloadAccountingCsv,
  downloadBothExports,
  downloadMyInvoisJson,
  getDashboardSummary,
  markExported,
} from '../api/client';
import AppShell from '../components/AppShell';
import { Icon } from '../components/Icon';
import PageHeader, { PageMeta } from '../components/PageHeader';
import { useReceiptStore } from '../store/receiptStore';
import type { Client } from '../types/client';

function getCurrentMonthString(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  return `${year}-${month}`;
}

const CSV_COLUMNS =
  'DocDate, DocNo, SupplierCode, SupplierName, Description, ItemCode, Qty, UnitPrice, TaxCode, TaxAmount, TotalAmount';

export default function ExportsPage(): JSX.Element {
  const { clientId } = useParams<{ clientId: string }>();
  const [selectedMonth, setSelectedMonth] = useState<string>(getCurrentMonthString());
  const [isExportingCsv, setIsExportingCsv] = useState(false);
  const [isExportingJson, setIsExportingJson] = useState(false);
  const [isExportingBoth, setIsExportingBoth] = useState(false);
  const [isMarking, setIsMarking] = useState(false);
  const [confirmingMark, setConfirmingMark] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const markTriggerRef = useRef<HTMLButtonElement | null>(null);
  const markStripRef = useRef<HTMLDivElement | null>(null);
  const markWasOpen = useRef(false);
  const clients = useReceiptStore((state) => state.clients);
  const loadClients = useReceiptStore((state) => state.loadClients);
  const loadClientReceipts = useReceiptStore((state) => state.loadClientReceipts);
  const client: Client | null = clients.find((c) => c.id === clientId) ?? null;

  useEffect(() => {
    if (!clientId) return;
    // Aggregates shown elsewhere must be fresh on entry, like the dashboard.
    void loadClients();
  }, [clientId, loadClients]);

  // Opening on the calendar month exports nothing for a client whose books are
  // older, and the page gives no sign that the empty batch is a month problem
  // rather than a missing-receipt problem. Ask the API which month it would
  // default to and adopt that, so the first view matches the data.
  //
  // Guarded by "has the user chosen a month yet", not by a ran-once ref: React
  // StrictMode mounts twice, and a ref guard would swallow the first (cancelled)
  // mount's request and never issue a second one.
  const [monthTouched, setMonthTouched] = useState(false);
  useEffect(() => {
    if (!clientId || monthTouched) return undefined;
    let cancelled = false;
    void getDashboardSummary(clientId)
      .then((summary) => {
        if (!cancelled && !monthTouched) setSelectedMonth(summary.month);
      })
      .catch(() => {
        // Leave the calendar month in place: an unreachable API is reported by
        // the export actions themselves, not by a silent month swap.
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, monthTouched]);

  useEffect(() => {
    if (confirmingMark) {
      markWasOpen.current = true;
      markStripRef.current?.focus();
    } else if (markWasOpen.current && !isMarking) {
      markWasOpen.current = false;
      markTriggerRef.current?.focus();
    }
  }, [confirmingMark, isMarking]);

  useEffect(() => {
    if (!confirmingMark) return undefined;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      setConfirmingMark(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [confirmingMark]);

  if (!clientId) {
    return (
      <AppShell>
        <div className="page-shell">
          <div
            role="alert"
            className="border-l-[3px] border-l-mismatch-text bg-mismatch-bg py-3 pl-4 pr-3 text-ui text-mismatch-text"
          >
            No workspace client selected.
          </div>
        </div>
      </AppShell>
    );
  }

  const handleDownloadCsv = async () => {
    setError(null);
    setSuccessMessage(null);
    setIsExportingCsv(true);
    try {
      await downloadAccountingCsv(clientId, selectedMonth || undefined);
      setSuccessMessage('Accounting CSV downloaded successfully.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to download accounting CSV');
    } finally {
      setIsExportingCsv(false);
    }
  };

  const handleDownloadJson = async () => {
    setError(null);
    setSuccessMessage(null);
    setIsExportingJson(true);
    try {
      await downloadMyInvoisJson(clientId, selectedMonth || undefined);
      setSuccessMessage('LHDN MyInvois JSON downloaded successfully.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to download MyInvois JSON');
    } finally {
      setIsExportingJson(false);
    }
  };

  const handleDownloadBoth = async () => {
    setError(null);
    setSuccessMessage(null);
    setIsExportingBoth(true);
    try {
      await downloadBothExports(clientId, selectedMonth || undefined);
      setSuccessMessage('Both accounting CSV and LHDN MyInvois JSON downloaded successfully.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to download exports');
    } finally {
      setIsExportingBoth(false);
    }
  };

  const handleMarkExported = async () => {
    setError(null);
    setSuccessMessage(null);
    setIsMarking(true);
    try {
      const { updated } = await markExported(clientId, selectedMonth || undefined);
      await Promise.all([loadClientReceipts(clientId), loadClients()]);
      // The store records refresh failures instead of throwing, so a failed
      // refresh must not be reported as success over stale rows.
      const { receiptsError, clientsError } = useReceiptStore.getState();
      if (receiptsError !== null || clientsError !== null) {
        setError(receiptsError ?? clientsError);
        return;
      }
      setSuccessMessage(
        updated === 0
          ? 'No verified receipts to mark as exported.'
          : `Marked ${updated} receipt${updated === 1 ? '' : 's'} as exported.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to mark receipts as exported');
    } finally {
      setIsMarking(false);
    }
  };

  const markScope = selectedMonth ? `the selected month (${selectedMonth})` : 'all billing dates';

  return (
    <AppShell clientId={clientId}>
      <div className="page-shell">
        <PageHeader
          eyebrow={
            client?.registration_number
              ? `Workspace ${client.registration_number}`
              : 'Workspace'
          }
          title="Exports"
          meta={
            <PageMeta
              name={client?.business_name ?? 'Client workspace'}
              back={{ to: `/clients/${clientId}/inbox`, label: 'Inbox' }}
            />
          }
          actions={
            <div className="flex flex-wrap items-end justify-end gap-2">
              <div>
                <label htmlFor="month-picker" id="period-selection" className="field-label">
                  Accounting billing period
                </label>
                <input
                  id="month-picker"
                  type="month"
                  value={selectedMonth}
                  onChange={(event) => {
                    // An explicit choice must win over the default-month fetch.
                    setMonthTouched(true);
                    setSelectedMonth(event.target.value);
                  }}
                  className="field-input w-auto font-mono-numbers"
                />
              </div>
              <button
                type="button"
                onClick={() => {
                  setMonthTouched(true);
                  setSelectedMonth('');
                }}
                aria-pressed={selectedMonth === ''}
                title="Export all verified receipts without month filter"
                className={`btn btn-secondary ${
                  selectedMonth === '' ? 'border-brand-900 text-brand-900' : ''
                }`}
              >
                All time
              </button>
            </div>
          }
        />

        {error !== null && (
          <div
            role="alert"
            className="mt-6 flex flex-wrap items-center justify-between gap-2 border-l-[3px] border-l-mismatch-text bg-mismatch-bg py-2 pl-3 pr-2"
          >
            <p className="flex min-w-0 items-center gap-2 text-ui text-mismatch-text">
              <Icon name="alert" size={16} />
              <span>{error}</span>
            </p>
            <button
              type="button"
              onClick={() => setError(null)}
              className="btn btn-ghost btn-sm text-mismatch-text"
            >
              Dismiss
            </button>
          </div>
        )}

        {successMessage !== null && (
          <div
            role="status"
            className="mt-6 flex flex-wrap items-center justify-between gap-2 border-l-[3px] border-l-verified-text bg-verified-bg py-2 pl-3 pr-2"
          >
            <p className="flex min-w-0 items-center gap-2 text-ui text-verified-text">
              <Icon name="check" size={16} />
              <span>{successMessage}</span>
            </p>
            <button
              type="button"
              onClick={() => setSuccessMessage(null)}
              className="btn btn-ghost btn-sm text-verified-text"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* No top rule: PageHeader already closes with one, and two parallel
            rules 24px apart read as a misaligned double border. */}
        <section aria-label="Export dispatch" className="mt-6 border-b border-border">
          <div className="border-b border-border py-4">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <p className="text-label text-text-muted">
                {selectedMonth ? (
                  <>
                    Filtering verified receipts for{' '}
                    <span className="font-mono-numbers text-text-secondary">{selectedMonth}</span>
                  </>
                ) : (
                  'Exporting all verified receipts across all billing dates'
                )}
              </p>

              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end">
                <button
                  type="button"
                  onClick={() => void handleDownloadBoth()}
                  disabled={isExportingBoth || isExportingCsv || isExportingJson}
                  className="btn btn-primary w-full sm:w-auto"
                >
                  {isExportingBoth ? (
                    'Generating bundle...'
                  ) : (
                    <>
                      <Icon name="download" size={16} />
                      Download both
                    </>
                  )}
                </button>

                <div className="flex flex-col gap-1 sm:border-l sm:border-border sm:pl-4">
                  <button
                    ref={markTriggerRef}
                    type="button"
                    onClick={() => setConfirmingMark(true)}
                    disabled={
                      confirmingMark || isMarking || isExportingBoth || isExportingCsv || isExportingJson
                    }
                    aria-expanded={confirmingMark}
                    aria-controls="mark-export-confirmation"
                    aria-describedby="mark-export-note"
                    className="btn btn-ghost w-full justify-start border-border-strong sm:w-auto"
                  >
                    {isMarking ? 'Marking...' : 'Mark exported'}
                  </button>
                </div>
              </div>
            </div>
            {/* The warning stays below the controls so the header row keeps its baseline. */}
            <p id="mark-export-note" className="mt-2 text-micro text-text-muted lg:text-right">
              Downloads leave receipt statuses unchanged. Marking is separate and permanent: it
              locks every verified receipt for {markScope} from further edits.
            </p>
            {confirmingMark ? (
              <div
                id="mark-export-confirmation"
                ref={markStripRef}
                tabIndex={-1}
                role="group"
                aria-labelledby="mark-export-confirmation-heading"
                className="mt-3 flex flex-wrap items-center justify-between gap-3 border-l-[3px] border-l-mismatch-text bg-mismatch-bg py-3 pl-3 pr-2"
              >
                <p
                  id="mark-export-confirmation-heading"
                  role="alert"
                  className="flex min-w-0 items-center gap-2 text-ui font-semibold text-mismatch-text"
                >
                  <Icon name="alert" size={16} />
                  Mark these receipts as exported? This cannot be undone. Every verified receipt for{' '}
                  {markScope} will become read-only.
                </p>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm text-mismatch-text"
                    onClick={() => setConfirmingMark(false)}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    disabled={isMarking}
                    onClick={() => {
                      setConfirmingMark(false);
                      void handleMarkExported();
                    }}
                  >
                    {isMarking ? 'Marking...' : 'Confirm mark exported'}
                  </button>
                </div>
              </div>
            ) : null}
          </div>

          {/* Accounting CSV */}
          <div className="grid gap-4 border-b border-border py-6 lg:grid-cols-12 lg:items-start">
            <div className="flex min-w-0 items-start gap-3 lg:col-span-8">
              <span className="stamp border-border bg-surface-subtle text-text-secondary">
                CSV
              </span>
              <div className="min-w-0">
                <h2 className="section-title">Accounting batch CSV</h2>
                <p className="mt-1 text-ui text-text-secondary">
                  Purchase journal batch import compatible with AutoCount and SQL Account desktop
                  systems.
                </p>
                <div
                  className="mt-2 overflow-x-auto"
                  tabIndex={0}
                  role="group"
                  aria-label="CSV export metadata"
                >
                  <p className="whitespace-nowrap font-mono text-micro text-text-muted">
                    Purchase journal · 11 columns · DocDate → TotalAmount
                  </p>
                </div>
                <details className="mt-3">
                  <summary className="flex min-h-11 w-fit items-center gap-1 py-2 text-label text-text-secondary hover:text-text-primary lg:min-h-0 lg:py-0">
                    <Icon name="chevron-right" size={14} />
                    Column mapping
                  </summary>
                  <div
                    className="mt-2 overflow-x-auto border-l-2 border-border pl-3"
                    tabIndex={0}
                    role="group"
                    aria-label="CSV column mapping"
                  >
                    <p className="whitespace-nowrap font-mono text-micro leading-5 text-text-secondary">
                      {CSV_COLUMNS}
                    </p>
                  </div>
                </details>
              </div>
            </div>
            <div className="lg:col-span-4 lg:flex lg:justify-end">
              <button
                type="button"
                onClick={() => void handleDownloadCsv()}
                disabled={isExportingCsv || isExportingBoth}
                className="btn btn-secondary w-full sm:w-auto"
              >
                {isExportingCsv ? 'Downloading CSV...' : 'Download accounting CSV (.csv)'}
              </button>
            </div>
          </div>

          {/* LHDN MyInvois JSON */}
          <div className="grid gap-4 py-6 lg:grid-cols-12 lg:items-start">
            <div className="flex min-w-0 items-start gap-3 lg:col-span-8">
              <span className="stamp border-border bg-surface-subtle text-text-secondary">
                JSON
              </span>
              <div className="min-w-0">
                <h2 className="section-title">LHDN MyInvois multi-line JSON</h2>
                <p className="mt-1 text-ui text-text-secondary">
                  A UBL-shaped draft modelled on the official SDK sample; it is not validated
                  against the LHDN schema, not signed, and never submitted.
                </p>
                <div
                  className="mt-2 overflow-x-auto"
                  tabIndex={0}
                  role="group"
                  aria-label="JSON export metadata"
                >
                  <p className="whitespace-nowrap font-mono text-micro text-text-muted">
                    UBL 2.1 · 1.1-Invoice-MultiLineItem-Sample.json · draft envelope, unsigned
                  </p>
                </div>
                <details className="mt-3">
                  <summary className="flex min-h-11 w-fit items-center gap-1 py-2 text-label text-text-secondary hover:text-text-primary lg:min-h-0 lg:py-0">
                    <Icon name="chevron-right" size={14} />
                    Schema notes
                  </summary>
                  <div
                    className="mt-2 max-h-64 overflow-y-auto border-l-2 border-border pl-3"
                    tabIndex={0}
                    role="group"
                    aria-label="JSON schema notes"
                  >
                    <ul className="space-y-1 text-label leading-5 text-text-secondary">
                      <li>UBL 2.1 CommonBasic and CommonAggregate namespaces</li>
                      <li>PartyIdentification carries the merchant BRN and SST registration number</li>
                      <li>InvoiceLine tax allocated from the document tax total</li>
                      <li>Draft MyInvois envelope — validate before submission.</li>
                    </ul>
                  </div>
                </details>
              </div>
            </div>
            <div className="lg:col-span-4 lg:flex lg:justify-end">
              <button
                type="button"
                onClick={() => void handleDownloadJson()}
                disabled={isExportingJson || isExportingBoth}
                className="btn btn-secondary w-full sm:w-auto"
              >
                {isExportingJson ? 'Downloading JSON...' : 'Download MyInvois JSON (.json)'}
              </button>
            </div>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
