import { formatConfidence } from '../lib/format';
import type { ReceiptStatus } from '../types/receipt';

interface StatusPillProps {
  status: ReceiptStatus;
  flags: string[];
  confidence?: number | null;
  processingError?: string | null;
}

const DELTA_PREFIX = 'MATH_MISMATCH_DELTA_';
const LOW_CONFIDENCE = 0.8;

const VERIFIED_STATUSES: readonly ReceiptStatus[] = ['STATUS_AUTO_VERIFIED', 'STATUS_VERIFIED'];

const PROCESSING_STATUSES: readonly ReceiptStatus[] = [
  'PENDING_UPLOAD',
  'UPLOADED',
  'PROCESSING_OCR',
  'PROCESSING_LLM',
  'VALIDATING_MATH',
];

const PILL_BASE =
  'inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium whitespace-nowrap';

/**
 * SCR-02 status pill (docs/04_ui_specs.md §4.3 matrix): verified → emerald,
 * needs-review math mismatch → red delta, low confidence → amber, processing →
 * neutral, terminal pipeline errors → red with the backend message as a tooltip.
 */
export default function StatusPill({
  status,
  flags,
  confidence,
  processingError,
}: StatusPillProps): JSX.Element {
  if (VERIFIED_STATUSES.includes(status)) {
    return (
      <span
        className={`${PILL_BASE} bg-verified-bg border-verified-border text-verified-text`}
        data-status={status}
        lang="ms"
      >
        <span aria-hidden="true">●</span> Selesai
      </span>
    );
  }

  if (status === 'STATUS_EXPORTED') {
    return (
      <span
        className={`${PILL_BASE} bg-surface-subtle border-border text-brand-900 font-medium`}
        data-status={status}
        lang="ms"
      >
        <span aria-hidden="true">→</span> Dieksport
      </span>
    );
  }

  if (status === 'STATUS_REJECTED') {
    return (
      <span
        className={`${PILL_BASE} bg-mismatch-bg border-mismatch-border text-mismatch-text`}
        data-status={status}
        lang="ms"
      >
        <span aria-hidden="true">✕</span> Ditolak
      </span>
    );
  }

  if (status === 'STATUS_NEEDS_REVIEW') {
    const mismatchFlag = flags.find((flag) => flag.startsWith(DELTA_PREFIX));
    if (mismatchFlag !== undefined) {
      const delta = mismatchFlag.slice(DELTA_PREFIX.length);
      return (
        <span
          className={`${PILL_BASE} bg-mismatch-bg border-mismatch-border text-mismatch-text`}
          data-status={status}
          lang="ms"
          title={`Math mismatch: Δ RM ${delta}`}
        >
          <span aria-hidden="true">!</span> Δ RM {delta}
        </span>
      );
    }

    // `overall_confidence` is the 0..1 source of truth; anything absent (null /
    // undefined), non-finite, or negative is unknown rather than a score.
    const score = typeof confidence === 'number' && Number.isFinite(confidence) && confidence >= 0
      ? confidence
      : null;
    if (score !== null && score < LOW_CONFIDENCE) {
      return (
        <span
          className={`${PILL_BASE} bg-warning-bg border-warning-border text-warning-text`}
          data-status={status}
          lang="ms"
          title="Low OCR confidence"
        >
          <span aria-hidden="true">?</span> Semak OCR ({formatConfidence(score)})
        </span>
      );
    }

    return (
      <span
        className={`${PILL_BASE} bg-warning-bg border-warning-border text-warning-text`}
        data-status={status}
        lang="ms"
      >
        <span aria-hidden="true">!</span> Perlu Semak
      </span>
    );
  }

  if (PROCESSING_STATUSES.includes(status)) {
    return (
      <span
        className={`${PILL_BASE} bg-surface-subtle border-border text-text-secondary`}
        data-status={status}
        lang="ms"
      >
        Memproses...
      </span>
    );
  }

  const errorLabel =
    status === 'ERR_UNREADABLE'
      ? 'Tidak Boleh Dibaca'
      : status === 'ERR_TIMEOUT'
        ? 'Masa Tamat'
        : status === 'ERR_EXTRACTION'
          ? 'Ekstraksi Gagal'
          : 'Fail';

  return (
    <span
      className={`${PILL_BASE} bg-mismatch-bg border-mismatch-border text-mismatch-text`}
      data-status={status}
      lang="ms"
      title={processingError ?? errorLabel}
    >
      <span aria-hidden="true">✕</span> {errorLabel}
    </span>
  );
}
