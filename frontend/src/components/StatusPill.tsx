import type { ReceiptStatus } from '../types/receipt';

interface StatusPillProps {
  status: ReceiptStatus;
  flags: string[];
  confidence?: number;
  processingError?: string | null;
}

const DELTA_PREFIX = 'MATH_MISMATCH_DELTA_';
const CONFIDENCE_PREFIX = 'LOW_CONFIDENCE_';

const VERIFIED_STATUSES: readonly ReceiptStatus[] = ['STATUS_AUTO_VERIFIED', 'STATUS_VERIFIED'];

const PROCESSING_STATUSES: readonly ReceiptStatus[] = [
  'PENDING_UPLOAD',
  'UPLOADED',
  'PROCESSING_OCR',
  'PROCESSING_LLM',
  'VALIDATING_MATH',
];

const PILL_BASE =
  'inline-flex h-dense-row items-center gap-1 border px-2 text-xs font-medium whitespace-nowrap';

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
      >
        <span aria-hidden="true">●</span> Selesai
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
          title={`Math mismatch: Δ RM ${delta}`}
        >
          <span aria-hidden="true">⚠️</span> Δ RM {delta}
        </span>
      );
    }

    const confidenceFlag = flags.find((flag) => flag.startsWith(CONFIDENCE_PREFIX));
    const flaggedConfidence =
      confidenceFlag === undefined
        ? null
        : Number(confidenceFlag.slice(CONFIDENCE_PREFIX.length));
    const lowScore = flaggedConfidence !== null && Number.isFinite(flaggedConfidence)
      ? flaggedConfidence
      : null;
    // `overall_confidence` is the 0..1 source of truth; the flag may carry a
    // percentage instead, so accept whichever scale the backend wrote.
    const score =
      lowScore === null
        ? (confidence ?? 1)
        : lowScore > 1
          ? lowScore
          : Math.round(lowScore * 100);
    if (lowScore !== null || (confidence !== undefined && confidence < 0.8)) {
      return (
        <span
          className={`${PILL_BASE} bg-warning-bg border-warning-border text-warning-text`}
          data-status={status}
        >
          <span aria-hidden="true">⚡</span> Semak OCR ({score}%)
        </span>
      );
    }

    return (
      <span
        className={`${PILL_BASE} bg-warning-bg border-warning-border text-warning-text`}
        data-status={status}
      >
        <span aria-hidden="true">⚠️</span> Perlu Semak
      </span>
    );
  }

  if (PROCESSING_STATUSES.includes(status)) {
    return (
      <span
        className={`${PILL_BASE} bg-surface-subtle border-border text-text-secondary`}
        data-status={status}
      >
        <span aria-hidden="true">⏳</span> Memproses...
      </span>
    );
  }

  const errorLabel =
    status === 'ERR_UNREADABLE'
      ? 'Tidak Boleh Dibaca'
      : status === 'ERR_TIMEOUT'
        ? 'Masa Tamat'
        : 'Fail';

  return (
    <span
      className={`${PILL_BASE} bg-mismatch-bg border-mismatch-border text-mismatch-text`}
      data-status={status}
      title={processingError ?? errorLabel}
    >
      <span aria-hidden="true">✕</span> {errorLabel}
    </span>
  );
}
