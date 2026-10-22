import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { receiptImageUrl } from '../api/client';
import AppShell from '../components/AppShell';
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../components/DataStates';
import { Icon } from '../components/Icon';
import PageHeader from '../components/PageHeader';
import StatusPill from '../components/StatusPill';
import UploadDropzone from '../components/UploadDropzone';
import { formatDate, formatMoneyDisplay } from '../lib/format';
import { useReceiptStore } from '../store/receiptStore';
import { useSessionStore } from '../store/sessionStore';
import type { ReceiptListItem, ReceiptListStatus, ReceiptStatus } from '../types/receipt';

const FILTER_TABS: readonly { label: string; value: ReceiptListStatus }[] = [
  { label: 'All', value: 'ALL' },
  { label: 'Needs review', value: 'NEEDS_REVIEW' },
  { label: 'Verified', value: 'VERIFIED' },
  { label: 'Exported', value: 'EXPORTED' },
  { label: 'Rejected', value: 'REJECTED' },
];

const DELTA_PREFIX = 'MATH_MISMATCH_DELTA_';
const PAGE_SIZE = 50;
const POLL_INTERVAL_MS = 3_000;
const PROCESSING_STATUSES: readonly ReceiptStatus[] = [
  'PROCESSING_OCR',
  'PROCESSING_LLM',
  'VALIDATING_MATH',
];

/**
 * SCR-02 inbox thumbnail: the image route needs `X-Accountant-Id`, so fetch a
 * blob and revoke the object URL on unmount.
 */
function ReceiptThumb({ clientId, receipt }: { clientId: string; receipt: ReceiptListItem }): JSX.Element {
  const accountantId = useSessionStore((state) => state.accountantId);
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [visible, setVisible] = useState(() => typeof IntersectionObserver === 'undefined');
  const holderRef = useRef<HTMLDivElement | null>(null);
  const urlRef = useRef<string | null>(null);

  // Fetch full-size blobs only once the row is actually on screen.
  useEffect(() => {
    const node = holderRef.current;
    if (node === null || visible) return undefined;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setVisible(true);
        observer.disconnect();
      }
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [visible]);

  useEffect(() => {
    if (!visible || accountantId === null || accountantId === '') {
      return undefined;
    }
    let revoked = false;
    const controller = new AbortController();

    fetch(receiptImageUrl(clientId, receipt.id), {
      headers: { 'X-Accountant-Id': accountantId },
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error(`Image request failed: ${response.status}`);
        return response.blob();
      })
      .then((blob) => {
        if (revoked) return;
        const next = URL.createObjectURL(blob);
        urlRef.current = next;
        setUrl(next);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setFailed(true);
      });

    return () => {
      revoked = true;
      controller.abort();
      if (urlRef.current !== null) {
        URL.revokeObjectURL(urlRef.current);
        urlRef.current = null;
      }
    };
  }, [clientId, receipt.id, accountantId, visible]);

  const showPlaceholder = accountantId === null || accountantId === '' || failed || url === null;

  return (
    <div ref={holderRef} className="h-8 w-8 overflow-hidden rounded-[1px] border border-border">
      {showPlaceholder ? (
        <div
          className="h-full w-full bg-surface-subtle"
          aria-label={`No preview for ${receipt.filename}`}
          role="img"
        />
      ) : (
        <img
          src={url}
          alt={receipt.filename}
          loading="lazy"
          className="h-full w-full object-cover"
        />
      )}
    </div>
  );
}

const FLAG_LABELS: Record<string, string> = {
  MISSING_MERCHANT_NAME: 'Missing merchant name',
  MISSING_DATE: 'Missing date',
  INVALID_GRAND_TOTAL: 'Invalid grand total',
  DATE_IN_FUTURE: 'Date in the future',
  DATE_EXCEEDS_1_YEAR: 'Date older than a year',
  MISSING_SUBTOTAL: 'Missing subtotal',
  MISSING_SST_ON_REGISTERED_MERCHANT: 'Missing SST on registered merchant',
};

const FIELD_LABELS: Record<string, string> = {
  merchant_name: 'merchant name',
  merchant_brn: 'BRN',
  merchant_sst: 'SST',
  invoice_date: 'invoice date',
  invoice_number: 'invoice number',
  subtotal: 'subtotal',
  tax_amount: 'tax',
  grand_total: 'grand total',
};

function humanizeField(field: string): string {
  return FIELD_LABELS[field] ?? field.replace(/_/g, ' ');
}

/** Flag summaries rendered under the merchant name on flagged rows. */
function flagDetails(flags: string[]): string[] {
  return flags.map((flag) => {
    if (flag.startsWith(DELTA_PREFIX)) {
      return `Math mismatch: Δ RM ${flag.slice(DELTA_PREFIX.length)}`;
    }
    if (flag.startsWith('LOW_CONFIDENCE_')) {
      return `Low OCR confidence: ${humanizeField(flag.slice('LOW_CONFIDENCE_'.length))}`;
    }
    if (flag.startsWith('MISSING_CRITICAL_EVIDENCE_')) {
      return `No OCR evidence: ${humanizeField(flag.slice('MISSING_CRITICAL_EVIDENCE_'.length))}`;
    }
    return FLAG_LABELS[flag] ?? humanizeField(flag);
  });
}

/** Splits the formatted money string so "RM" can sit as its own label. */
function moneyParts(value: string | null): { currency: string | null; amount: string } {
  const text = formatMoneyDisplay(value);
  return text.startsWith('RM ')
    ? { currency: 'RM', amount: text.slice(3) }
    : { currency: null, amount: text };
}

/** SCR-02 Batch Inbox: dropzone, status filter tabs, dense receipt table. */
export default function InboxPage(): JSX.Element {
  const { clientId } = useParams<{ clientId: string }>();
  const navigate = useNavigate();

  const clients = useReceiptStore((state) => state.clients);
  const currentClientId = useReceiptStore((state) => state.currentClientId);
  const receipts = useReceiptStore((state) => state.receipts);
  const receiptsTotal = useReceiptStore((state) => state.receiptsTotal);
  const statusCounts = useReceiptStore((state) => state.statusCounts);
  const receiptsOffset = useReceiptStore((state) => state.receiptsOffset);
  const statusFilter = useReceiptStore((state) => state.statusFilter);
  const receiptsLoading = useReceiptStore((state) => state.receiptsLoading);
  const receiptsError = useReceiptStore((state) => state.receiptsError);
  const uploadState = useReceiptStore((state) => state.uploadState);
  const uploadResult = useReceiptStore((state) => state.uploadResult);
  const loadClients = useReceiptStore((state) => state.loadClients);
  const loadClientReceipts = useReceiptStore((state) => state.loadClientReceipts);
  const setCurrentClientId = useReceiptStore((state) => state.setCurrentClientId);
  const setStatusFilter = useReceiptStore((state) => state.setStatusFilter);
  const uploadFiles = useReceiptStore((state) => state.uploadFiles);

  const client = useMemo(
    () => clients.find((candidate) => candidate.id === clientId),
    [clients, clientId],
  );

  useEffect(() => {
    if (clientId === undefined) return;
    void loadClients();
    if (currentClientId !== clientId) {
      void setCurrentClientId(clientId);
    } else {
      void loadClientReceipts(clientId);
    }
  }, [clientId, currentClientId, loadClients, setCurrentClientId, loadClientReceipts]);

  const hasProcessing = receipts.some((receipt) => PROCESSING_STATUSES.includes(receipt.status));

  useEffect(() => {
    if (clientId === undefined || !hasProcessing) return;
    const interval = window.setInterval(() => {
      void loadClientReceipts(clientId, receiptsOffset);
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [clientId, hasProcessing, receiptsOffset, loadClientReceipts]);

  const uploading = uploadState === 'uploading';

  if (clientId === undefined) {
    return (
      <AppShell>
        <div className="page-shell">
          <ErrorBanner message="No client selected." />
        </div>
      </AppShell>
    );
  }

  const openReview = (receiptId: string): void => {
    navigate(`/clients/${clientId}/review/${receiptId}`);
  };

  const pageStart = receipts.length === 0 ? 0 : receiptsOffset + 1;
  const pageEnd = receiptsOffset + receipts.length;
  const hasPrevious = receiptsOffset > 0;
  const hasNext = receiptsOffset + PAGE_SIZE < receiptsTotal;

  return (
    <AppShell clientId={clientId}>
      <div className="page-shell space-y-7">
        <PageHeader
          eyebrow={client?.registration_number ? `Workspace ${client.registration_number}` : 'Workspace'}
          title="Inbox"
          meta={
            <span className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <span>{client?.business_name ?? 'Client workspace'}</span>
              {receiptsTotal > 0 && (
                <>
                  <span aria-hidden="true" className="text-text-muted">
                    ·
                  </span>
                  <span className="font-mono-numbers text-label text-text-muted">
                    receipts {pageStart}–{pageEnd} of {receiptsTotal}
                  </span>
                </>
              )}
            </span>
          }
          actions={
            <>
              <Link to="/clients" className="link-quiet min-h-11">
                <Icon name="arrow-left" size={16} />
                Clients
              </Link>
              <Link to="/upload" className="btn btn-secondary">
                <Icon name="camera" size={18} />
                Capture
              </Link>
            </>
          }
        />

        <UploadDropzone disabled={uploading} onFiles={(files) => void uploadFiles(files)} />

        <div aria-live="polite" className="min-h-0 text-ui">
          {uploadState === 'uploading' && <p className="text-text-secondary">Uploading…</p>}
          {uploadState === 'done' && uploadResult !== null && (
            <div className="space-y-1">
              <p className="font-semibold text-text-primary">
                {uploadResult.uploaded.length} file
                {uploadResult.uploaded.length === 1 ? '' : 's'} queued for processing.
              </p>
              {uploadResult.uploaded.some((item) => item.error !== undefined) && (
                <ul className="space-y-0.5 text-label text-mismatch-text">
                  {uploadResult.uploaded.map((item) =>
                    item.error === undefined ? null : (
                      <li key={item.id}>
                        {item.filename}: {item.error}
                      </li>
                    ),
                  )}
                </ul>
              )}
            </div>
          )}
          {uploadState === 'error' && uploadResult !== null && uploadResult.failed !== null && (
            <p className="font-semibold text-mismatch-text">{uploadResult.failed}</p>
          )}
        </div>

        <div
          role="group"
          aria-label="Status filter"
          className="-mx-5 overflow-x-auto border-b border-border px-5 sm:mx-0 sm:px-0"
        >
          <div className="flex min-w-max items-end gap-6">
            {FILTER_TABS.map((tab) => (
              <button
                key={tab.value}
                type="button"
                aria-pressed={statusFilter === tab.value}
                onClick={() => void setStatusFilter(tab.value)}
                className={`flex h-10 items-center border-b-2 px-0.5 text-ui whitespace-nowrap transition-colors duration-100 ${
                  statusFilter === tab.value
                    ? 'border-brand-900 font-semibold text-text-primary'
                    : 'border-transparent text-text-muted hover:text-text-primary'
                }`}
              >
                {tab.label}
                {statusCounts[tab.value] !== undefined && statusCounts[tab.value] > 0 && (
                  <span className="ml-1.5 font-mono-numbers text-label text-text-muted">
                    {statusCounts[tab.value]}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {receiptsError !== null && (
          <ErrorBanner
            message={receiptsError}
            onRetry={() => {
              void loadClientReceipts(clientId, receiptsOffset);
            }}
          />
        )}

        {/* A transport failure must not read as an empty inbox; stale rows stay. */}
        {receiptsError === null && receiptsLoading && receipts.length === 0 ? (
          <LoadingSkeleton rows={5} />
        ) : receiptsError === null && receipts.length === 0 ? (
          <EmptyState
            title="No receipts yet — drop a batch above."
            hint="JPG, PNG, HEIC or PDF, up to 50 files per batch."
          />
        ) : receipts.length === 0 ? null : (
          <table className="data-table block md:table" role="table" aria-label="Receipt inbox">
            <thead className="hidden md:table-header-group" role="rowgroup">
              <tr role="row">
                <th scope="col" role="columnheader" className="sticky top-14 z-10 lg:top-0 w-11 border-b border-border bg-canvas py-2 pl-0 pr-2">
                  <span className="sr-only">Preview</span>
                </th>
                <th scope="col" role="columnheader" className="sticky top-14 z-10 lg:top-0 border-b border-border bg-canvas px-2 py-2">
                  Supplier
                </th>
                <th scope="col" role="columnheader" className="sticky top-14 z-10 lg:top-0 w-24 border-b border-border bg-canvas px-2 py-2">
                  Date
                </th>
                <th scope="col" role="columnheader" className="sticky top-14 z-10 lg:top-0 w-16 border-b border-border bg-canvas px-2 py-2 text-right">
                  Items
                </th>
                <th scope="col" role="columnheader" className="sticky top-14 z-10 lg:top-0 w-32 border-b border-border bg-canvas px-2 py-2 text-right">
                  Grand total
                </th>
                <th scope="col" role="columnheader" className="sticky top-14 z-10 lg:top-0 w-32 border-b border-border bg-canvas px-2 py-2">
                  Status
                </th>
                <th scope="col" role="columnheader" className="sticky top-14 z-10 lg:top-0 w-24 border-b border-border bg-canvas px-2 py-2">
                  <span className="sr-only">Action</span>
                </th>
              </tr>
            </thead>
            <tbody className="block md:table-row-group" role="rowgroup">
              {receipts.map((receipt) => {
                const processing = PROCESSING_STATUSES.includes(receipt.status);
                const details = flagDetails(receipt.validation_flags);
                const money = moneyParts(receipt.grand_total);
                return (
                  <tr
                    key={receipt.id}
                    role="row"
                    onClick={() => {
                      if (!processing) openReview(receipt.id);
                    }}
                    className={`grid grid-cols-[32px_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2 border-b border-border py-3 transition-colors duration-100 hover:bg-surface md:table-row md:border-b-0 md:py-0 ${
                      processing ? '' : 'cursor-pointer'
                    }`}
                  >
                    <td
                      role="cell"
                      className="row-span-2 self-start border-b-0 px-0 py-0 align-middle md:row-span-1 md:table-cell md:border-b md:pl-0 md:pr-2"
                      onClick={(event) => event.stopPropagation()}
                    >
                      <ReceiptThumb clientId={clientId} receipt={receipt} />
                    </td>
                    <td role="cell" className="col-span-2 min-w-0 border-b-0 px-0 py-0 align-middle md:col-span-1 md:table-cell md:max-w-0 md:border-b md:px-2">
                      <span className="block truncate text-ui font-semibold text-text-primary">
                        {receipt.merchant_name ?? '—'}
                      </span>
                      {receipt.merchant_name === null && (
                        // A file with no extracted supplier is identified by its
                        // name, but the name is not a supplier: keep it subdued.
                        <span className="mt-0.5 block truncate text-label text-text-muted">
                          {receipt.filename}
                        </span>
                      )}
                      {details.length > 0 && (
                        <span
                          className="mt-0.5 block truncate text-label text-warning-text"
                          title={details.join(' · ')}
                        >
                          {details.join(' · ')}
                        </span>
                      )}
                    </td>
                    <td role="cell" className="border-b-0 px-0 py-0 align-middle font-mono-numbers text-label text-text-secondary md:table-cell md:border-b md:px-2 md:text-ui">
                      {formatDate(receipt.invoice_date)}
                    </td>
                    <td role="cell" className="hidden border-b-0 px-0 py-0 align-middle font-mono-numbers text-label text-text-secondary md:table-cell md:border-b md:px-2 md:text-ui">
                      {receipt.line_item_count}
                    </td>
                    <td role="cell" className="border-b-0 px-0 py-0 text-right align-middle md:table-cell md:border-b md:px-2">
                      {money.currency !== null && (
                        <span className="mr-1 text-label text-text-muted">{money.currency}</span>
                      )}
                      <span className="font-mono-numbers text-body text-text-primary md:text-ui">
                        {money.amount}
                      </span>
                    </td>
                    <td role="cell" className="col-span-3 border-b-0 px-0 py-0 align-middle md:col-span-1 md:table-cell md:border-b md:px-2">
                      <StatusPill
                        status={receipt.status}
                        flags={receipt.validation_flags}
                        confidence={receipt.overall_confidence}
                      />
                    </td>
                    <td
                      role="cell"
                      className="col-span-3 border-b-0 px-0 py-0 align-middle md:col-span-1 md:table-cell md:border-b md:px-2"
                      onClick={(event) => event.stopPropagation()}
                    >
                      <button
                        type="button"
                        disabled={processing}
                        onClick={() => openReview(receipt.id)}
                        className="inline-flex min-h-11 w-full items-center justify-center gap-1 border border-border-strong bg-surface px-3 text-ui font-semibold text-text-primary transition-colors duration-100 hover:bg-surface-subtle disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-subtle disabled:text-text-muted md:w-24"
                      >
                        Open
                        <Icon name="chevron-right" size={14} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {receiptsTotal > 0 && (
          <div className="rule-total flex flex-wrap items-center justify-between gap-3 pt-3">
            <span role="status" className="font-mono-numbers text-label text-text-secondary">
              Showing {pageStart}–{pageEnd} of {receiptsTotal}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={!hasPrevious}
                onClick={() => void loadClientReceipts(clientId, Math.max(0, receiptsOffset - PAGE_SIZE))}
                className="btn btn-secondary btn-sm"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={!hasNext}
                onClick={() => void loadClientReceipts(clientId, receiptsOffset + PAGE_SIZE)}
                className="btn btn-secondary btn-sm"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
