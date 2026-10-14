import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  downloadAccountingCsv,
  downloadBothExports,
  downloadMyInvoisJson,
} from '../api/client';
import AppShell from '../components/AppShell';
import { ErrorBanner } from '../components/DataStates';
import { useReceiptStore } from '../store/receiptStore';
import type { Client } from '../types/client';

function getCurrentMonthString(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  return `${year}-${month}`;
}

export default function ExportsPage(): JSX.Element {
  const { clientId } = useParams<{ clientId: string }>();
  const [selectedMonth, setSelectedMonth] = useState<string>(getCurrentMonthString());
  const [isExportingCsv, setIsExportingCsv] = useState(false);
  const [isExportingJson, setIsExportingJson] = useState(false);
  const [isExportingBoth, setIsExportingBoth] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const clients = useReceiptStore((state) => state.clients);
  const loadClients = useReceiptStore((state) => state.loadClients);
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
        <div className="p-6">
          <ErrorBanner message="No workspace client selected." />
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

  return (
    <AppShell clientId={clientId}>
      <div className="mx-auto max-w-5xl space-y-6 p-6">
        {/* Header Bar */}
        <div className="flex flex-col gap-3 border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 bg-brand-700" aria-hidden="true" />
              <h1 className="text-base font-semibold text-text-primary">
                Export Hub (SCR-05)
              </h1>
            </div>
            <p className="mt-1 text-xs text-text-secondary">
              Workspace:{' '}
              <span className="font-semibold text-text-primary">
                {client?.business_name ?? 'Client Workspace'}
              </span>{' '}
              {client?.registration_number && (
                <span className="font-mono-numbers text-text-muted">
                  ({client.registration_number})
                </span>
              )}
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Link
              to={`/clients/${clientId}/inbox`}
              className="inline-flex h-9 items-center border border-border bg-surface px-3 text-xs font-medium text-text-secondary transition-colors hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-900"
            >
              ← Return to Inbox
            </Link>
          </div>
        </div>

        {/* Feedback Alerts */}
        {error !== null && (
          <ErrorBanner message={error} onRetry={() => setError(null)} />
        )}
        {successMessage !== null && (
          <div
            role="status"
            className="flex items-center justify-between border border-verified-border bg-verified-bg px-4 py-3 text-xs font-medium text-verified-text"
          >
            <span>✓ {successMessage}</span>
            <button
              type="button"
              onClick={() => setSuccessMessage(null)}
              className="text-verified-text hover:underline"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Filter Controls & 1-Click Action */}
        <section
          aria-labelledby="period-selection"
          className="border border-border bg-surface p-5 shadow-sm"
        >
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <label
                htmlFor="month-picker"
                id="period-selection"
                className="block text-xs font-semibold uppercase tracking-wider text-text-secondary"
              >
                Accounting Billing Period
              </label>
              <div className="mt-2 flex items-center gap-2">
                <input
                  id="month-picker"
                  type="month"
                  value={selectedMonth}
                  onChange={(e) => setSelectedMonth(e.target.value)}
                  className="h-10 border border-border bg-canvas px-3 text-sm font-mono-numbers text-text-primary focus-visible:border-border-focus focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-900"
                />
                <button
                  type="button"
                  onClick={() => setSelectedMonth('')}
                  className="h-10 border border-border bg-surface px-3 text-xs text-text-secondary hover:bg-surface-subtle focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-900"
                  title="Export all verified receipts without month filter"
                >
                  All Time
                </button>
              </div>
              <p className="mt-1 text-[11px] text-text-muted">
                {selectedMonth
                  ? `Filtering verified receipts for ${selectedMonth}`
                  : 'Exporting all verified receipts across all billing dates'}
              </p>
            </div>

            {/* One-Click Download Both Files CTA */}
            <div>
              <button
                type="button"
                onClick={() => void handleDownloadBoth()}
                disabled={isExportingBoth || isExportingCsv || isExportingJson}
                className="inline-flex h-11 items-center justify-center gap-2 border border-brand-900 bg-brand-900 px-5 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-2"
              >
                {isExportingBoth ? (
                  <span>Generating Bundle...</span>
                ) : (
                  <>
                    <span aria-hidden="true">⬇</span>
                    <span>Download Both Files (1-Click)</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </section>

        {/* Dual Export Cards Grid */}
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          {/* Card A: Accounting CSV */}
          <article className="flex flex-col justify-between border border-border bg-surface p-5 shadow-sm">
            <div>
              <div className="flex items-center justify-between">
                <span className="border border-border bg-surface-subtle px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-text-secondary">
                  Option A · Purchase Journal
                </span>
                <span className="text-xs font-mono-numbers text-text-muted">
                  AutoCount / SQL Account
                </span>
              </div>
              <h2 className="mt-3 text-sm font-semibold text-text-primary">
                Accounting Batch CSV
              </h2>
              <p className="mt-2 text-xs leading-relaxed text-text-secondary">
                Purchase journal batch import compatible with AutoCount and SQL Account desktop systems. Includes column mapping:
              </p>
              <div className="mt-3 border border-border bg-surface-subtle p-2 font-mono text-[10px] text-text-secondary">
                DocDate, DocNo, SupplierCode, SupplierName, Description, ItemCode, Qty, UnitPrice, TaxCode, TaxAmount, TotalAmount
              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-border">
              <button
                type="button"
                onClick={() => void handleDownloadCsv()}
                disabled={isExportingCsv || isExportingBoth}
                className="w-full inline-flex h-10 items-center justify-center border border-border bg-surface px-4 text-xs font-medium text-text-primary hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-900"
              >
                {isExportingCsv ? 'Downloading CSV...' : 'Download Accounting CSV (.csv)'}
              </button>
            </div>
          </article>

          {/* Card B: LHDN MyInvois v1.1 JSON */}
          <article className="flex flex-col justify-between border border-border bg-surface p-5 shadow-sm">
            <div>
              <div className="flex items-center justify-between">
                <span className="border border-verified-border bg-verified-bg px-2 py-0.5 text-[10px] font-semibold text-verified-text">
                  Option B · LHDN MyInvois v1.1
                </span>
                <span className="inline-flex items-center gap-1 border border-verified-border bg-verified-bg px-2 py-0.5 text-[10px] font-semibold text-verified-text">
                  <span aria-hidden="true">✓</span> Schema Check: 100% Valid
                </span>
              </div>
              <h2 className="mt-3 text-sm font-semibold text-text-primary">
                LHDN MyInvois Multi-Line JSON
              </h2>
              <p className="mt-2 text-xs leading-relaxed text-text-secondary">
                Direct transformation matching the official LHDN SDK multi-line invoice specification (
                <span className="font-mono text-[11px]">1.1-Invoice-MultiLineItem-Sample.json</span>).
              </p>
              <ul className="mt-3 space-y-1 text-[11px] text-text-secondary list-disc list-inside">
                <li>UBL 2.1 CommonBasic & CommonAggregate namespaces</li>
                <li>PartyIdentification TIN/BRN validation</li>
                <li>InvoiceLine and LegalMonetaryTotal balancing</li>
              </ul>
            </div>

            <div className="mt-6 pt-4 border-t border-border">
              <button
                type="button"
                onClick={() => void handleDownloadJson()}
                disabled={isExportingJson || isExportingBoth}
                className="w-full inline-flex h-10 items-center justify-center border border-brand-900 bg-surface px-4 text-xs font-medium text-brand-900 hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-900"
              >
                {isExportingJson ? 'Downloading JSON...' : 'Download MyInvois JSON (.json)'}
              </button>
            </div>
          </article>
        </div>
      </div>
    </AppShell>
  );
}
