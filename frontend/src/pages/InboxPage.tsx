import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { receiptImageUrl } from '../api/client';
import AppShell from '../components/AppShell';
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../components/DataStates';
import StatusPill from '../components/StatusPill';
import UploadDropzone from '../components/UploadDropzone';
import { formatDate, formatMoneyDisplay } from '../lib/format';
import { useReceiptStore } from '../store/receiptStore';
import { useSessionStore } from '../store/sessionStore';
import type { ReceiptListItem, ReceiptListStatus, ReceiptStatus } from '../types/receipt';

const FILTER_TABS: readonly { label: string; value: ReceiptListStatus }[] = [
  { label: 'All', value: 'ALL' },
  { label: 'Needs Review', value: 'NEEDS_REVIEW' },
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
    <div ref={holderRef} className="h-9 w-9 overflow-hidden rounded border border-border">
      {showPlaceholder ? (
        <div
          className="h-full w-full rounded bg-surface-subtle"
          aria-label={`No preview for ${receipt.filename}`}
          role="img"
        />
      ) : (
        <img
          src={url}
          alt={receipt.filename}
          loading="lazy"
          className="h-full w-full rounded object-cover"
        />
      )}
    </div>
  );
}

/** Flag summaries rendered under the merchant name on flagged rows. */
function flagDetails(flags: string[]): string[] {
  return flags.map((flag) =>
    flag.startsWith(DELTA_PREFIX)
      ? `Math Mismatch: Δ RM ${flag.slice(DELTA_PREFIX.length)}`
      : flag === 'MISSING_DATE'
        ? 'Missing Date'
        : flag,
  );
}

/** SCR-02 Batch Inbox: dropzone, status filter tabs, dense receipt table. */
export default function InboxPage(): JSX.Element {
  const { clientId } = useParams<{ clientId: string }>();
  const navigate = useNavigate();

  const clients = useReceiptStore((state) => state.clients);
  const currentClientId = useReceiptStore((state) => state.currentClientId);
  const receipts = useReceiptStore((state) => state.receipts);
  const receiptsTotal = useReceiptStore((state) => state.receiptsTotal);
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
        <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
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
      <div className="mx-auto max-w-6xl space-y-5 px-4 py-6 sm:px-6">
        <header className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface p-4 shadow-card sm:p-5">
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-tight text-text-primary">
              Inbox
            </h1>
            <p className="mt-1 text-sm text-text-secondary">
              {client?.business_name ?? 'Client workspace'}
            </p>
          </div>
          <Link
            to="/clients"
            className="inline-flex h-9 items-center rounded-lg border border-border bg-surface px-3 text-xs font-medium text-text-secondary transition-colors hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-900"
          >
            ← Clients
          </Link>
        </header>

        <UploadDropzone disabled={uploading} onFiles={(files) => void uploadFiles(files)} />

        <div aria-live="polite" className="min-h-0 text-xs">
          {uploadState === 'uploading' && <p className="text-text-secondary">Uploading…</p>}
          {uploadState === 'done' && uploadResult !== null && (
            <div className="space-y-1">
              <p className="font-medium text-text-primary">
                {uploadResult.uploaded.length} file
                {uploadResult.uploaded.length === 1 ? '' : 's'} queued for processing.
              </p>
              {uploadResult.uploaded.some((item) => item.error !== undefined) && (
                <ul className="space-y-0.5 text-mismatch-text">
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
            <p className="font-medium text-mismatch-text">{uploadResult.failed}</p>
          )}
        </div>

        <div
          role="group"
          aria-label="Status filter"
          className="flex w-full flex-wrap gap-1 rounded-lg border border-border bg-surface-subtle p-1"
        >
          {FILTER_TABS.map((tab) => (
            <button
              key={tab.value}
              type="button"
              aria-pressed={statusFilter === tab.value}
              onClick={() => void setStatusFilter(tab.value)}
              className={`min-h-10 flex-1 rounded-md px-3 text-xs font-medium whitespace-nowrap focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none ${
                statusFilter === tab.value
                  ? 'bg-surface text-text-primary shadow-sm'
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {receiptsError !== null && (
          <ErrorBanner
            message={receiptsError}
            onRetry={() => {
              void loadClientReceipts(clientId, receiptsOffset);
            }}
          />
        )}

        {receiptsLoading && receipts.length === 0 ? (
          <LoadingSkeleton rows={5} />
        ) : receipts.length === 0 ? (
          <EmptyState
            title="No receipts yet — drop a batch above."
            hint="JPG, PNG, HEIC or PDF, up to 50 files per batch."
          />
        ) : (
          <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-card">
            <div className="relative overflow-x-auto">
              <table className="w-full border-collapse text-xs" aria-label="Receipt inbox">
                <thead>
                  <tr className="h-dense-row border-b border-border bg-surface-subtle/70 text-left text-[11px] uppercase tracking-wider text-text-muted">
                    <th className="w-14 pl-3 pr-1">
                      <span className="sr-only">Preview</span>
                    </th>
                    <th className="px-3">Supplier</th>
                    <th className="w-[100px] px-2">Date</th>
                    <th className="w-20 px-2">Items</th>
                    <th className="w-[110px] px-2 text-right">Grand Total</th>
                    <th className="w-[130px] px-2">Status</th>
                    <th className="w-20 px-2">
                      <span className="sr-only">Action</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {receipts.map((receipt) => {
                  const needsReview = receipt.status === 'STATUS_NEEDS_REVIEW';
                  const processing = PROCESSING_STATUSES.includes(receipt.status);
                  const failed =
                    receipt.status === 'ERR_UNREADABLE' ||
                    receipt.status === 'ERR_TIMEOUT' ||
                    receipt.status === 'ERR_FILE_CORRUPT' ||
                    receipt.status === 'ERR_EXTRACTION';
                  const details = flagDetails(receipt.validation_flags);
                  return (
                    <tr
                      key={receipt.id}
                      onClick={() => {
                        if (!processing) openReview(receipt.id);
                      }}
                      className={`h-dense-row border-b border-border hover:bg-surface-subtle ${
                        processing ? '' : 'cursor-pointer'
                      } ${
                        needsReview
                          ? 'border-l-2 border-warning-border'
                          : failed
                            ? 'border-l-2 border-mismatch-border'
                            : ''
                      }`}
                    >
                      <td className="pl-3 pr-1 align-middle" onClick={(event) => event.stopPropagation()}>
                        <ReceiptThumb clientId={clientId} receipt={receipt} />
                      </td>
                      <td className="max-w-0 px-3">
                        <span className="block truncate font-semibold text-text-primary">
                          {receipt.merchant_name ?? receipt.filename}
                        </span>
                        {details.length > 0 && (
                          <span className="block truncate text-[11px] text-warning-text">
                            {details.join(' · ')}
                          </span>
                        )}
                      </td>
                      <td className="px-2 font-mono-numbers text-text-secondary">
                        {formatDate(receipt.invoice_date)}
                      </td>
                      <td className="px-2 font-mono-numbers text-text-secondary">
                        {receipt.line_item_count}
                      </td>
                      <td className="px-2 text-right font-mono-numbers text-text-primary">
                        {formatMoneyDisplay(receipt.grand_total)}
                      </td>
                      <td className="px-2">
                        <StatusPill
                          status={receipt.status}
                          flags={receipt.validation_flags}
                          confidence={receipt.overall_confidence}
                        />
                      </td>
                      <td className="px-2" onClick={(event) => event.stopPropagation()}>
                        <button
                          type="button"
                          disabled={processing}
                          onClick={() => openReview(receipt.id)}
                          className="inline-flex h-8 w-20 items-center justify-center rounded-md border border-border bg-surface font-medium text-text-primary focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-text-muted"
                        >
                          Review
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
          </div>
        )}

        {receiptsTotal > 0 && (
          <div className="flex min-h-11 items-center justify-between gap-3 rounded-xl border border-border bg-surface px-4 py-2 text-xs shadow-card">
            <span role="status" className="text-text-secondary">
              Showing {pageStart}–{pageEnd} of {receiptsTotal}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={!hasPrevious}
                onClick={() => void loadClientReceipts(clientId, Math.max(0, receiptsOffset - PAGE_SIZE))}
                className="inline-flex min-h-11 items-center border border-border bg-surface px-3 font-medium text-text-primary focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none disabled:cursor-not-allowed disabled:text-text-muted"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={!hasNext}
                onClick={() => void loadClientReceipts(clientId, receiptsOffset + PAGE_SIZE)}
                className="inline-flex min-h-11 items-center border border-border bg-surface px-3 font-medium text-text-primary focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none disabled:cursor-not-allowed disabled:text-text-muted"
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
