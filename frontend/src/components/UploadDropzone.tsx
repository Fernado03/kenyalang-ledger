import { useCallback, useRef, useState } from 'react';

interface UploadDropzoneProps {
  disabled?: boolean;
  onFiles: (files: File[]) => void;
}

/** Human-readable size for the per-file list. */
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * SCR-02 batch dropzone (docs/03_appflow.md §3.3 SCR-02). Drop or browse files,
 * review the staged batch, remove single files. Duplicate and batch-size
 * validation is the backend's job; only the count is shown client-side.
 */
export default function UploadDropzone({
  disabled = false,
  onFiles,
}: UploadDropzoneProps): JSX.Element {
  const [staged, setStaged] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const stage = useCallback(
    (incoming: File[]) => {
      if (disabled || incoming.length === 0) return;
      setStaged((current) => [...current, ...incoming]);
      onFiles(incoming);
    },
    [disabled, onFiles],
  );

  const label = disabled
    ? 'Uploading batch…'
    : 'Drop receipts here, or click to browse. Max 50 files per batch.';

  return (
    <section className="border border-border bg-surface p-3" aria-label="Upload receipts">
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
            ? 'border border-dashed border-brand-500 bg-brand-50 transition-colors duration-100 ease-out'
            : 'border border-dashed border-border bg-surface-subtle transition-colors duration-100 ease-out'
        }
      >
        <button
          type="button"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          className="flex min-h-11 w-full items-center justify-center px-4 py-6 text-sm focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none"
        >
          <span
            className={
              dragging ? 'text-center text-xs text-text-primary' : 'text-center text-xs text-text-secondary'
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
        disabled={disabled}
        aria-label="Upload receipts (JPEG, PNG, HEIC, or PDF)"
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          stage(files);
          event.target.value = '';
        }}
      />

      {staged.length > 0 && (
        <ul className="mt-2 border border-border">
          {staged.map((file, index) => (
            <li
              key={`${file.name}-${index}`}
              className="flex h-dense-row items-center justify-between gap-2 border-b border-border px-2 last:border-b-0"
            >
              <span className="truncate text-xs text-text-primary">{file.name}</span>
              <span className="flex shrink-0 items-center gap-2">
                <span className="font-mono-numbers text-xs text-text-secondary">
                  {formatFileSize(file.size)}
                </span>
                <button
                  type="button"
                  aria-label={`Remove ${file.name}`}
                  onClick={() =>
                    setStaged((current) => current.filter((_unused, i) => i !== index))
                  }
                  className="inline-flex min-h-11 w-11 items-center justify-center border border-border bg-surface text-xs text-text-secondary focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none"
                >
                  ✕
                </button>
              </span>
            </li>
          ))}
          <li className="flex h-dense-row items-center px-2 text-xs text-text-secondary">
            {staged.length} file{staged.length === 1 ? '' : 's'} selected
          </li>
        </ul>
      )}
    </section>
  );
}
