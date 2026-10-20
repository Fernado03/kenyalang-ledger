import type { MathAudit } from '../lib/audit';

interface MathBannerProps {
  audit: MathAudit;
  missingSst: boolean;
  dirty: boolean;
}

/** Verified breakdowns arrive prefixed with this label; strip it once. */
const MATCH_PREFIX = 'Math Matches — ';

/** Renders the breakdown without duplicating the "Math Matches" label. */
function matchBreakdown(message: string): string {
  return message.startsWith(MATCH_PREFIX) ? message.slice(MATCH_PREFIX.length) : message;
}
const MATCH_STRIP =
  'flex flex-wrap items-center gap-x-3 gap-y-1 border bg-verified-bg border-verified-border px-3 py-2 text-verified-text';

const MISMATCH_STRIP =
  'flex flex-wrap items-center gap-x-3 gap-y-1 border bg-mismatch-bg border-mismatch-border px-3 py-2 text-mismatch-text';

const WARNING_CHIP =
  'inline-flex items-center border bg-warning-bg border-warning-border px-2 py-0.5 text-xs font-medium text-warning-text';

/**
 * SCR-03 §3.5 math audit strip: verified emerald vs. mismatch red, the
 * "missing SST on a registered merchant" warning chip, and an unsaved-changes
 * hint. `role="status"` + `aria-live="polite"` announce each recalculation as
 * the accountant types.
 */
export default function MathBanner({ audit, missingSst, dirty }: MathBannerProps): JSX.Element {
  return (
    <div
      role="status"
      aria-live="polite"
      className={audit.valid && audit.matches ? MATCH_STRIP : MISMATCH_STRIP}
    >
      {!audit.valid ? (
        <p className="text-sm font-semibold">
          <span aria-hidden="true">✕</span> Invalid amount:{' '}
          <span className="font-mono-numbers">{audit.invalidFields.join(', ')}</span>
        </p>
      ) : audit.matches ? (
        <p className="text-sm font-semibold">
          <span aria-hidden="true">✓</span>{' '}
          <span className="font-mono-numbers">{matchBreakdown(audit.message)}</span>
        </p>
      ) : (
        <p className="text-sm font-semibold">
          <span aria-hidden="true">!</span> Math Mismatch:{' '}
          <span className="font-mono-numbers">{audit.message}</span>
        </p>
      )}

      {missingSst && (
        <span className={WARNING_CHIP}>Missing SST on Registered Merchant</span>
      )}

      {dirty && <span className="ml-auto text-xs text-text-muted">Unsaved changes</span>}
    </div>
  );
}
