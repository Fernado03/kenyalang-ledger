import { useEffect, useId, useState } from 'react';
import { Link } from 'react-router-dom';
import AppShell from '../components/AppShell';
import { Icon } from '../components/Icon';
import PageHeader, { PageMeta } from '../components/PageHeader';
import StatusPill from '../components/StatusPill';
import { useReceiptStore } from '../store/receiptStore';

const FILE_INPUT_ACCEPT = 'image/jpeg,image/png,image/heic,application/pdf';

/** How often the accepted batch re-reads its real statuses (M2). */
const POLL_INTERVAL_MS = 3_000;

/** Statuses the pipeline is still working through. */
const SETTLED_STATUSES = new Set([
  'STATUS_NEEDS_REVIEW',
  'STATUS_AUTO_VERIFIED',
  'STATUS_VERIFIED',
  'STATUS_EXPORTED',
  'STATUS_REJECTED',
]);

function isSettled(status: string): boolean {
  return SETTLED_STATUSES.has(status) || status.startsWith('ERR_');
}

const CAPTURE_BUTTON_CLASS =
  'flex h-24 w-full cursor-pointer items-center justify-center gap-3 rounded-sm bg-brand-900 text-ui font-semibold text-brand-50 transition-colors duration-100 focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-brand-50';

const PICK_BUTTON_CLASS =
  'flex h-14 w-full cursor-pointer items-center justify-center gap-2 rounded-sm border border-border-strong bg-surface text-ui font-semibold text-text-primary transition-colors duration-100 focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-brand-700';

/** SCR-02b mobile capture: upload receipts straight from a phone camera. */
export default function UploadPage() {
  const currentClientId = useReceiptStore((state) => state.currentClientId);
  const clients = useReceiptStore((state) => state.clients);
  const loadClients = useReceiptStore((state) => state.loadClients);
  const uploadFiles = useReceiptStore((state) => state.uploadFiles);
  const uploadState = useReceiptStore((state) => state.uploadState);
  const uploadResult = useReceiptStore((state) => state.uploadResult);
  const refreshUploadStatuses = useReceiptStore((state) => state.refreshUploadStatuses);
  const [inputKey, setInputKey] = useState(0);
  const cameraId = useId();
  const filesId = useId();

  useEffect(() => {
    // Always refresh: a persisted id from a previous session must be validated
    // against the accountant's actual workspaces, not trusted blindly.
    void loadClients();
  }, [loadClients]);

  // Poll until every accepted row has settled (M2). The batch response carries
  // a snapshot of the status at upload time, so without this the rows sit on
  // "Processing" forever while the backend has long since finished.
  const hasPendingRows =
    uploadResult !== null &&
    uploadResult.uploaded.some((item) => !isSettled(item.status));

  useEffect(() => {
    if (!hasPendingRows) {
      return;
    }
    let cancelled = false;
    const tick = (): void => {
      if (cancelled) return;
      void refreshUploadStatuses();
    };
    tick();
    const timer = window.setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
    // Deliberately not keyed on `uploadResult`: the object is replaced on every
    // poll, which would tear down and rebuild the interval each tick.
  }, [hasPendingRows, refreshUploadStatuses]);

  const client = clients.find((item) => item.id === currentClientId) ?? null;
  const hasSelectedClient =
    clients.length > 0 && clients.some((item) => item.id === currentClientId);

  const handleFiles = (files: FileList | null) => {
    if (files === null || files.length === 0) return;
    void uploadFiles(Array.from(files)).finally(() => {
      // Remount inputs so choosing the same file again re-triggers upload.
      setInputKey((key) => key + 1);
    });
  };

  return (
    <AppShell clientId={currentClientId ?? undefined}>
      <div className="page-shell">
        <PageHeader
          eyebrow="Capture"
          title="Upload receipts"
          meta={
            <PageMeta
              name={client?.business_name}
              note={
                client?.business_name !== undefined
                  ? undefined
                  : hasSelectedClient
                    ? 'Selected client'
                    : 'Choose a workspace to begin'
              }
              back={
                hasSelectedClient
                  ? { to: `/clients/${currentClientId ?? ''}/inbox`, label: 'Inbox' }
                  : undefined
              }
            />
          }
        />

        {hasSelectedClient ? (
          <div className="mt-6 grid gap-x-10 gap-y-8 lg:grid-cols-12 lg:items-start">
            <div className="space-y-5 lg:col-span-5">
              <div className="space-y-3">
                <label
                  className={`${CAPTURE_BUTTON_CLASS} ${
                    uploadState === 'uploading' ? 'pointer-events-none opacity-40' : 'hover:bg-brand-700'
                  }`}
                >
                  <Icon name="camera" size={24} />
                  Take photo
                  <input
                    key={`camera-${inputKey}`}
                    id={cameraId}
                    type="file"
                    accept={FILE_INPUT_ACCEPT}
                    capture="environment"
                    className="sr-only"
                    disabled={uploadState === 'uploading'}
                    onChange={(event) => handleFiles(event.target.files)}
                  />
                </label>
                <label
                  className={`${PICK_BUTTON_CLASS} ${
                    uploadState === 'uploading' ? 'pointer-events-none opacity-40' : 'hover:bg-surface-subtle'
                  }`}
                >
                  <Icon name="upload" size={18} />
                  Choose files
                  <input
                    key={`files-${inputKey}`}
                    id={filesId}
                    type="file"
                    multiple
                    accept={FILE_INPUT_ACCEPT}
                    className="sr-only"
                    disabled={uploadState === 'uploading'}
                    onChange={(event) => handleFiles(event.target.files)}
                  />
                </label>
              </div>

              <p className="text-label text-text-muted">
                JPEG, PNG, HEIC, PDF · 50 files per batch · 15 MiB each · 50 MiB per batch
              </p>
              <p className="text-label text-text-muted">Processing continues in the background.</p>

              <div aria-live="polite" role="status" className="min-h-5 text-label">
                {uploadState === 'uploading' ? (
                  <span className="text-text-secondary">Uploading…</span>
                ) : null}
                {uploadState === 'done' && uploadResult !== null ? (
                  <span className="text-verified-text">
                    {uploadResult.uploaded.length} file
                    {uploadResult.uploaded.length === 1 ? '' : 's'} accepted.
                  </span>
                ) : null}
                {uploadState === 'error' && uploadResult?.failed ? (
                  <span className="text-mismatch-text">{uploadResult.failed}</span>
                ) : null}
              </div>
            </div>

            <div className="lg:col-span-6 lg:col-start-7">
              {uploadResult !== null && uploadResult.uploaded.length > 0 ? (
                <>
                  <h2 className="section-title">
                    Accepted this batch
                  </h2>
                  <ul
                    aria-label="Accepted this batch"
                    className="mt-3 divide-y divide-border border-y border-border"
                  >
                    {uploadResult.uploaded.map((item) => (
                      <li key={item.id} className="flex items-center justify-between gap-3 py-3">
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-ui text-text-primary">
                            {item.filename}
                          </span>
                          {item.error ? (
                            <span className="mt-1 block text-label text-mismatch-text">
                              {item.error}
                            </span>
                          ) : null}
                        </span>
                        <StatusPill
                          status={item.status}
                          flags={[]}
                          processingError={item.error ?? null}
                        />
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <>
                  <h2 className="section-title">
                    After the upload
                  </h2>
                  <ol className="mt-3 space-y-3 border-t border-border pt-4">
                    <li className="grid grid-cols-[7rem_1fr] gap-3">
                      <span className="text-label font-medium text-text-primary">Queued</span>
                      <span className="text-label text-text-secondary">
                        The file is stored against this workspace and waits for a worker.
                      </span>
                    </li>
                    <li className="grid grid-cols-[7rem_1fr] gap-3">
                      <span className="text-label font-medium text-text-primary">OCR</span>
                      <span className="text-label text-text-secondary">
                        Text and line items are read from the image or PDF.
                      </span>
                    </li>
                    <li className="grid grid-cols-[7rem_1fr] gap-3">
                      <span className="text-label font-medium text-text-primary">Extraction</span>
                      <span className="text-label text-text-secondary">
                        Supplier, dates and totals are filled into a draft receipt.
                      </span>
                    </li>
                    <li className="grid grid-cols-[7rem_1fr] gap-3">
                      <span className="text-label font-medium text-text-primary">Math check</span>
                      <span className="text-label text-text-secondary">
                        Line items are reconciled against the printed grand total.
                      </span>
                    </li>
                    <li className="grid grid-cols-[7rem_1fr] gap-3">
                      <span className="text-label font-medium text-text-primary">Review</span>
                      <span className="text-label text-text-secondary">
                        Clean receipts verify themselves; the rest wait in the inbox for you.
                      </span>
                    </li>
                  </ol>
                </>
              )}
            </div>
          </div>
        ) : (
          <div className="mt-6 border-t border-border pt-6">
            <h2 className="section-title">No workspace selected</h2>
            <p className="mt-2 text-ui text-text-secondary">
              {clients.length === 0
                ? 'Create a client before uploading receipts.'
                : 'Choose a workspace from the client list before uploading.'}
            </p>
            <Link className="btn btn-primary mt-4" to="/clients">
              Go to clients
            </Link>
          </div>
        )}
      </div>
    </AppShell>
  );
}
