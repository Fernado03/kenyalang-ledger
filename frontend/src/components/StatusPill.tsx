import { Icon } from './Icon';
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

const STAMP_VERIFIED = 'stamp bg-verified-bg border-verified-border text-verified-text';
const STAMP_EXPORTED = 'stamp bg-surface-subtle border-border-strong text-brand-900';
const STAMP_MISMATCH = 'stamp bg-mismatch-bg border-mismatch-border text-mismatch-text';
const STAMP_WARNING = 'stamp bg-warning-bg border-warning-border text-warning-text';
const STAMP_NEUTRAL = 'stamp bg-surface-subtle border-border text-text-secondary';

/**
 * SCR-02 status stamp (docs/04_ui_specs.md §4.3 matrix): verified → green,
 * needs-review math mismatch → red delta, low confidence → amber, processing →
 * neutral, terminal pipeline errors → red with the backend message as a tooltip.
 * Status is icon + text, never colour alone.
 */
export default function StatusPill({
  status,
  flags,
  confidence,
  processingError,
}: StatusPillProps): JSX.Element {
  if (VERIFIED_STATUSES.includes(status)) {
    return (
      <span className={STAMP_VERIFIED} data-status={status}>
        <Icon name="check" size={12} /> Verified
      </span>
    );
  }

  if (status === 'STATUS_EXPORTED') {
    return (
      <span className={STAMP_EXPORTED} data-status={status}>
        <Icon name="exports" size={12} /> Exported
      </span>
    );
  }

  if (status === 'STATUS_REJECTED') {
    return (
      <span className={STAMP_MISMATCH} data-status={status}>
        <Icon name="close" size={12} /> Rejected
      </span>
    );
  }

  if (status === 'STATUS_NEEDS_REVIEW') {
    const mismatchFlag = flags.find((flag) => flag.startsWith(DELTA_PREFIX));
    if (mismatchFlag !== undefined) {
      const delta = mismatchFlag.slice(DELTA_PREFIX.length);
      return (
        <span
          className={STAMP_MISMATCH}
          data-status={status}
          title={`Math mismatch: off by RM ${delta}`}
        >
          {/* Spelled out, not "Δ RM 0.04". At 10px in the mono stack the delta
              glyph *is* a triangle: side by side with the alert icon it read as
              two warnings, and once that icon was removed it read as a broken
              icon on its own. Words cannot be mistaken for a glyph. */}
          Off by RM {delta}
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
        <span className={STAMP_WARNING} data-status={status} title="Low OCR confidence">
          <Icon name="alert" size={12} /> OCR check {formatConfidence(score)}
        </span>
      );
    }

    return (
      <span className={STAMP_WARNING} data-status={status}>
        <Icon name="alert" size={12} /> Needs review
      </span>
    );
  }

  if (PROCESSING_STATUSES.includes(status)) {
    return (
      <span className={STAMP_NEUTRAL} data-status={status}>
        <Icon name="clock" size={12} /> Processing
      </span>
    );
  }

  const errorLabel =
    status === 'ERR_UNREADABLE'
      ? 'Unreadable'
      : status === 'ERR_TIMEOUT'
        ? 'Timed out'
        : status === 'ERR_EXTRACTION'
          ? 'Extraction failed'
          : 'File error';

  return (
    <span
      className={STAMP_MISMATCH}
      data-status={status}
      title={processingError ?? errorLabel}
    >
      <Icon name="close" size={12} /> {errorLabel}
    </span>
  );
}
