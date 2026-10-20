import { useCallback, useRef, useState } from 'react';

interface UploadDropzoneProps {
  disabled?: boolean;
  onFiles: (files: File[]) => void;
}

/**
 * SCR-02 batch dropzone (docs/03_appflow.md §3.3 SCR-02). Files upload as soon
 * as they are dropped or picked; duplicate and batch-size validation is the
 * backend's job, so there is no client-side staging to cancel.
 */
export default function UploadDropzone({
  disabled = false,
  onFiles,
}: UploadDropzoneProps): JSX.Element {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const stage = useCallback(
    (incoming: File[]) => {
      if (disabled || incoming.length === 0) return;
      onFiles(incoming);
    },
    [disabled, onFiles],
  );

  const label = disabled
    ? 'Uploading batch…'
    : 'Drop receipts here, or click to browse. Max 50 files per batch.';

  return (
    <section className="rounded-xl border border-border bg-surface p-3 shadow-card" aria-label="Upload receipts">
      <div
        onDragOver={(event) => {
          if (disabled) return;
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          if (disabled) return;
          event.preventDefault();
          setDragging(false);
          stage(Array.from(event.dataTransfer.files));
        }}
        className={
          dragging
            ? 'rounded-lg border-2 border-dashed border-brand-700 bg-brand-50/40 transition-colors duration-100 ease-out'
            : 'rounded-lg border-2 border-dashed border-border bg-surface-subtle transition-colors duration-100 ease-out'
        }
      >
        <button
          type="button"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          className="flex min-h-24 w-full items-center justify-center px-6 py-8 text-sm focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none"
        >
          <span
            className={
              dragging ? 'text-center text-sm text-text-primary' : 'text-center text-sm text-text-secondary'
            }
          >
            {label}
          </span>
        </button>
      </div>

      <input
        id="receipt-file-input"
        ref={inputRef}
        type="file"
        multiple
        accept="image/jpeg,image/png,image/heic,.pdf"
        className="sr-only"
        tabIndex={-1}
        disabled={disabled}
        aria-label="Upload receipts (JPEG, PNG, HEIC, or PDF)"
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          stage(files);
          event.target.value = '';
        }}
      />
    </section>
  );
}
