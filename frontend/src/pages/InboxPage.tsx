import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { receiptImageUrl } from '../api/client';
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../components/DataStates';
import StatusPill from '../components/StatusPill';
import UploadDropzone from '../components/UploadDropzone';
import { formatDate, formatMoneyDisplay } from '../lib/format';
import { useReceiptStore } from '../store/receiptStore';
import { useSessionStore } from '../store/sessionStore';
import type { ReceiptListItem, ReceiptListStatus } from '../types/receipt';

const FILTER_TABS: readonly { label: string; value: ReceiptListStatus }[] = [
  { label: 'All', value: 'ALL' },
  { label: 'Needs Review', value: 'NEEDS_REVIEW' },
  { label: 'Verified', value: 'VERIFIED' },
  { label: 'Exported', value: 'EXPORTED' },
];

const DELTA_PREFIX = 'MATH_MISMATCH_DELTA_';

/**
 * SCR-02 inbox thumbnail: the image route needs `X-Accountant-Id`, so fetch a
 * blob and revoke the object URL on unmount.
 */
function ReceiptThumb({ clientId, receipt }: { clientId: string; receipt: ReceiptListItem }): JSX.Element {
  const accountantId = useSessionStore((state) => state.accountantId);
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (accountantId === null || accountantId === '') {
      return;
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
        setUrl(URL.createObjectURL(blob));
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setFailed(true);
      });

    return () => {
      revoked = true;
      controller.abort();
      setUrl((current) => {
        if (current !== null) URL.revokeObjectURL(current);
        return null;
      });
    };
  }, [clientId, receipt.id, accountantId]);

  if (accountantId === null || accountantId === '' || failed || url === null) {
    return (
      <div
        className="h-10 w-10 border border-border bg-surface-subtle"
        aria-label={`No preview for ${receipt.filename}`}
        role="img"
      />
    );
  }

  return (
    <img
      src={url}
      alt={receipt.filename}
      loading="lazy"
      className="h-10 w-10 border border-border object-cover"
    />
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
  const [checked, setChecked] = useState<readonly string[]>([]);

  const clients = useReceiptStore((state) => state.clients);
  const currentClientId = useReceiptStore((state) => state.currentClientId);
  const receipts = useReceiptStore((state) => state.receipts);
  const statusFilter = useReceiptStore((state) => state.statusFilter);
  const receiptsLoading = useReceiptStore((state) => state.receiptsLoading);
  const receiptsError = useReceiptStore((state) => state.receiptsError);
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

  const uploading = useReceiptStore((state) => state.uploadState === 'uploading');

  if (clientId === undefined) {
    return (
      <div className="space-y-3 p-4">
        <ErrorBanner message="No client selected." />
      </div>
    );
  }

  const openReview = (receiptId: string): void => {
    navigate(`/clients/${clientId}/review/${receiptId}`);
  };

  return (
    <div className="space-y-3 p-4">
      <header className="flex h-dense-row items-center justify-between gap-3 border border-border bg-surface px-3">
        <h1 className="truncate text-sm font-semibold text-text-primary">
          {client?.business_name ?? 'Inbox'}
        </h1>
        <div className="flex items-center gap-2">
          <Link
            to="/clients"
            className="inline-flex min-h-11 items-center border border-border bg-surface px-3 text-xs font-medium text-text-secondary focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none"
          >
            ← Review Clients
          </Link>
          <Link
            to={`/clients/${clientId}/exports`}
            className="inline-flex min-h-11 items-center border border-border bg-surface-subtle px-3 text-xs font-medium text-text-primary hover:border-brand-900 focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none"
          >
            Exports (SCR-05) →
          </Link>
        </div>
      </header>

      <UploadDropzone
        disabled={uploading}
        onFiles={(files) => {
          void uploadFiles(files).then(() => loadClientReceipts(clientId));
        }}
      />

      <nav aria-label="Status filter" className="flex border border-border bg-surface">
        {FILTER_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            aria-pressed={statusFilter === tab.value}
            onClick={() => void setStatusFilter(tab.value)}
            className={
              statusFilter === tab.value
                ? 'inline-flex min-h-11 items-center border-r border-border bg-brand-900 px-3 text-xs font-medium text-white focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none'
                : 'inline-flex min-h-11 items-center border-r border-border bg-surface px-3 text-xs text-text-secondary focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none'
            }
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {receiptsError !== null && (
        <ErrorBanner
          message={receiptsError}
          onRetry={() => {
            void loadClientReceipts(clientId);
          }}
        />
      )}

      {receiptsLoading ? (
        <LoadingSkeleton rows={5} />
      ) : receipts.length === 0 ? (
        <EmptyState
          title="No receipts yet — drop a batch above."
          hint="JPG, PNG, HEIC or PDF, up to 50 files per batch."
        />
      ) : (
        <div className="overflow-x-auto border border-border bg-surface">
          <table className="w-full border-collapse text-xs" aria-label="Receipt inbox">
            <thead>
              <tr className="h-dense-row border-b border-border bg-surface-subtle text-left text-text-secondary">
                <th className="w-8 px-2">
                  <span className="sr-only">Select</span>
                </th>
                <th className="w-12 px-2">
                  <span className="sr-only">Preview</span>
                </th>
                <th className="px-2">Supplier</th>
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
                const failed =
                  receipt.status === 'ERR_UNREADABLE' ||
                  receipt.status === 'ERR_TIMEOUT' ||
                  receipt.status === 'ERR_FILE_CORRUPT';
                const details = flagDetails(receipt.validation_flags);
                return (
                  <tr
                    key={receipt.id}
                    onClick={() => openReview(receipt.id)}
                    className={`h-dense-row cursor-pointer border-b border-border hover:bg-surface-subtle ${
                      needsReview
                        ? 'border-l-2 border-warning-border'
                        : failed
                          ? 'border-l-2 border-mismatch-border'
                          : ''
                    }`}
                  >
                    <td className="px-2" onClick={(event) => event.stopPropagation()}>
                      <input
                        type="checkbox"
                        className="h-4 w-4 border border-border accent-brand-900"
                        checked={checked.includes(receipt.id)}
                        onChange={(event) =>
                          setChecked((current) =>
                            event.target.checked
                              ? [...current, receipt.id]
                              : current.filter((id) => id !== receipt.id),
                          )
                        }
                        aria-label={`Select ${receipt.filename}`}
                      />
                    </td>
                    <td className="px-2" onClick={(event) => event.stopPropagation()}>
                      <ReceiptThumb clientId={clientId} receipt={receipt} />
                    </td>
                    <td className="max-w-0 px-2">
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
                        onClick={() => openReview(receipt.id)}
                        className="inline-flex h-dense-row w-20 items-center justify-center border border-border bg-surface font-medium text-text-primary focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none"
                      >
                        Review (↵)
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
