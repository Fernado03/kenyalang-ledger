import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  downloadAccountingCsv,
  downloadBothExports,
  downloadMyInvoisJson,
  markExported,
} from '../api/client';
import AppShell from '../components/AppShell';
import { Icon } from '../components/Icon';
import PageHeader from '../components/PageHeader';
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
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const clients = useReceiptStore((state) => state.clients);
  const loadClients = useReceiptStore((state) => state.loadClients);
  const loadClientReceipts = useReceiptStore((state) => state.loadClientReceipts);
  const client: Client | null = clients.find((c) => c.id === clientId) ?? null;

  useEffect(() => {
    if (!clientId) return;
    if (clients.length === 0) {
      void loadClients();
    }
  }, [clientId, clients.length, loadClients]);

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
      await loadClientReceipts(clientId);
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

  return (
    <AppShell clientId={clientId}>
      <div className="page-shell">
        <PageHeader
          eyebrow={
            client?.registration_number
              ? `WORKSPACE · ${client.registration_number}`
              : 'WORKSPACE'
          }
          title="Exports"
          meta={
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="text-text-primary">
                {client?.business_name ?? 'Client workspace'}
              </span>
              <Link to={`/clients/${clientId}/inbox`} className="link-quiet text-label">
                <Icon name="arrow-left" size={14} />
                Inbox
              </Link>
            </div>
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
                  onChange={(e) => setSelectedMonth(e.target.value)}
                  className="field-input mt-0 w-auto font-mono-numbers"
                />
              </div>
              <button
                type="button"
                onClick={() => setSelectedMonth('')}
                aria-pressed={selectedMonth === ''}
                title="Export all verified receipts without month filter"
                className={`btn btn-secondary btn-sm ${
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
            className="mt-5 flex flex-wrap items-center justify-between gap-2 border-l-[3px] border-l-mismatch-text bg-mismatch-bg py-2 pl-3 pr-2"
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
            className="mt-5 flex flex-wrap items-center justify-between gap-2 border-l-[3px] border-l-verified-text bg-verified-bg py-2 pl-3 pr-2"
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

        <section aria-label="Export dispatch" className="mt-6 border-y border-border">
          <div className="flex flex-col gap-4 border-b border-border py-4 lg:flex-row lg:items-center lg:justify-between">
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

            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-end">
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
                  type="button"
                  onClick={() => void handleMarkExported()}
                  disabled={isMarking || isExportingBoth || isExportingCsv || isExportingJson}
                  className="btn btn-ghost w-full justify-start border-border-strong sm:w-auto"
                >
                  {isMarking ? 'Marking...' : 'Mark exported'}
                </button>
                <p className="max-w-[38ch] text-micro text-text-muted">
                  Downloads leave receipt statuses unchanged. Marking is a separate, explicit
                  action.
                </p>
              </div>
            </div>
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
                <div className="mt-2 overflow-x-auto">
                  <p className="whitespace-nowrap font-mono text-micro text-text-muted">
                    Purchase journal · 11 columns · DocDate → TotalAmount
                  </p>
                </div>
                <details className="mt-3">
                  <summary className="flex w-fit items-center gap-1 text-label text-text-secondary hover:text-text-primary">
                    <Icon name="chevron-right" size={14} />
                    Column mapping
                  </summary>
                  <div className="mt-2 overflow-x-auto border-l-2 border-border pl-3">
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
                <div className="mt-2 overflow-x-auto">
                  <p className="whitespace-nowrap font-mono text-micro text-text-muted">
                    UBL 2.1 · 1.1-Invoice-MultiLineItem-Sample.json · draft envelope, unsigned
                  </p>
                </div>
                <details className="mt-3">
                  <summary className="flex w-fit items-center gap-1 text-label text-text-secondary hover:text-text-primary">
                    <Icon name="chevron-right" size={14} />
                    Schema notes
                  </summary>
                  <ul className="mt-2 space-y-1 border-l-2 border-border pl-3 font-mono text-micro leading-5 text-text-secondary">
                    <li>UBL 2.1 CommonBasic and CommonAggregate namespaces</li>
                    <li>PartyIdentification carries the merchant BRN and SST registration number</li>
                    <li>InvoiceLine tax allocated from the document tax total</li>
                    <li>Draft MyInvois envelope — validate before submission.</li>
                  </ul>
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
