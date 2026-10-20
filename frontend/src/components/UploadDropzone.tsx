import { useCallback, useRef, useState } from 'react';
import { Icon } from './Icon';

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
    <section aria-label="Upload receipts">
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
        className={`flex min-h-[52px] items-center gap-3 border-y px-3 transition-colors duration-100 ease-out ${
          dragging ? 'border-dashed border-brand-700 bg-brand-100' : 'border-border bg-surface'
        }`}
      >
        <Icon name="upload" size={18} className="shrink-0 text-text-muted" />
        <p className="min-w-0 flex-1 text-ui text-text-secondary">{label}</p>
        <button
          type="button"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          className="btn btn-secondary"
        >
          Browse
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
