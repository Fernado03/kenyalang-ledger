import { useEffect, useId, useState } from 'react';
import { Link } from 'react-router-dom';
import AppShell from '../components/AppShell';
import { useReceiptStore } from '../store/receiptStore';

const FILE_INPUT_ACCEPT = 'image/jpeg,image/png,image/heic,application/pdf';

const UPLOAD_BUTTON_CLASS =
  'inline-flex h-11 cursor-pointer items-center justify-center border border-brand-900 bg-brand-900 px-5 text-sm font-semibold text-white transition-colors hover:bg-brand-700 focus-within:ring-2 focus-within:ring-brand-900 focus-within:ring-offset-2';

/** SCR-02b mobile capture: upload receipts straight from a phone camera. */
export default function UploadPage() {
  const currentClientId = useReceiptStore((state) => state.currentClientId);
  const clients = useReceiptStore((state) => state.clients);
  const loadClients = useReceiptStore((state) => state.loadClients);
  const uploadFiles = useReceiptStore((state) => state.uploadFiles);
  const uploadState = useReceiptStore((state) => state.uploadState);
  const uploadResult = useReceiptStore((state) => state.uploadResult);
  const [inputKey, setInputKey] = useState(0);
  const cameraId = useId();
  const filesId = useId();

  useEffect(() => {
    if (clients.length === 0) {
      void loadClients();
    }
  }, [clients.length, loadClients]);

  const client = clients.find((item) => item.id === currentClientId) ?? null;

  const handleFiles = (files: FileList | null) => {
    if (files === null || files.length === 0) return;
    void uploadFiles(Array.from(files)).finally(() => {
      // Remount inputs so choosing the same file again re-triggers upload.
      setInputKey((key) => key + 1);
    });
  };

  return (
    <AppShell clientId={currentClientId ?? undefined}>
      <div className="mx-auto max-w-2xl space-y-6 p-6">
        <div className="border border-border bg-surface p-4">
          <h1 className="text-lg font-semibold tracking-tight text-text-primary">
            Upload receipts
          </h1>
          <p className="mt-1 text-sm text-text-secondary">
            Workspace:{' '}
            <span className="font-semibold text-text-primary">
              {client?.business_name ?? (currentClientId ? 'Selected client' : 'No client selected')}
            </span>
          </p>
        </div>

        {currentClientId === null ? (
          <div className="border border-border bg-surface p-6 text-center">
            <p className="text-sm font-semibold text-text-primary">
              Select a client workspace first
            </p>
            <p className="mt-1 text-sm text-text-secondary">
              Receipts are uploaded into the selected client.
            </p>
            <Link
              to="/clients"
              className="mt-4 inline-flex h-11 items-center border border-border bg-surface px-4 text-sm font-semibold text-text-primary hover:bg-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-900"
            >
              Choose a client
            </Link>
          </div>
        ) : (
          <div className="space-y-4 border border-border bg-surface p-6">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className={UPLOAD_BUTTON_CLASS}>
                Take photo
                <input
                  key={`camera-${inputKey}`}
                  id={cameraId}
                  type="file"
                  accept="image/*"
                  capture="environment"
                  className="sr-only"
                  disabled={uploadState === 'uploading'}
                  onChange={(event) => handleFiles(event.target.files)}
                />
              </label>
              <label className={UPLOAD_BUTTON_CLASS}>
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

            <p className="text-xs text-text-secondary">
              JPEG, PNG, HEIC or PDF. Up to 50 files per batch, 15 MiB each,
              50 MiB per batch. Processing continues in the background.
            </p>

            <div aria-live="polite" role="status" className="min-h-6 text-sm">
              {uploadState === 'uploading' ? (
                <span className="text-text-secondary">Uploading…</span>
              ) : null}
              {uploadState === 'done' && uploadResult !== null ? (
                <span className="text-verified-text">
                  {uploadResult.uploaded.length} file
                  {uploadResult.uploaded.length === 1 ? '' : 's'} queued for
                  processing.
                </span>
              ) : null}
              {uploadState === 'error' && uploadResult?.failed ? (
                <span className="text-mismatch-text">{uploadResult.failed}</span>
              ) : null}
            </div>

            {uploadResult !== null && uploadResult.uploaded.length > 0 ? (
              <ul className="divide-y divide-border border border-border">
                {uploadResult.uploaded.map((item) => (
                  <li
                    key={item.id}
                    className="flex items-center justify-between gap-3 px-3 py-2 text-xs"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-text-primary">
                        {item.filename}
                      </span>
                      {item.error ? (
                        <span className="block text-mismatch-text">{item.error}</span>
                      ) : null}
                    </span>
                    <span className="font-mono-numbers text-text-secondary">
                      {item.status}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}

            <div className="flex flex-wrap items-center gap-3 pt-2">
              <Link
                to={`/clients/${currentClientId}/inbox`}
                className="inline-flex h-11 items-center border border-border bg-surface px-4 text-sm text-text-primary hover:bg-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-900"
              >
                Go to Inbox
              </Link>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
