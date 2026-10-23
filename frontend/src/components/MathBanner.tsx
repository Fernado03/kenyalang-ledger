import { Icon } from './Icon';
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

/** Cardless ruled strip: the 3px left rule carries the state. */
const MATCH_STRIP = 'flex flex-wrap items-center gap-x-3 gap-y-1 border-l-[3px] border-verified-border px-3 py-2 text-verified-text';

const MISMATCH_STRIP = 'flex flex-wrap items-center gap-x-3 gap-y-1 border-l-[3px] border-mismatch-border px-3 py-2 text-mismatch-text';

const WARNING_STRIP = 'flex flex-wrap items-center gap-x-3 gap-y-1 border-l-[3px] border-warning-border px-3 py-2 text-text-secondary';

/**
 * SCR-03 §3.5 math audit strip: verified green vs. mismatch red, the
 * "missing SST on a registered merchant" warning stamp, and an unsaved-changes
 * hint. `role="status"` + `aria-live="polite"` announce each recalculation as
 * the accountant types.
 */
export default function MathBanner({ audit, missingSst, dirty }: MathBannerProps): JSX.Element {
  const stateClass = !audit.valid || !audit.matches
    ? MISMATCH_STRIP
    : missingSst
      ? WARNING_STRIP
      : MATCH_STRIP;

  return (
    <div role="status" aria-live="polite" className={stateClass}>
      <span className="section-label">Math check</span>

      {!audit.valid ? (
        <p className="text-ui font-semibold">
          <Icon name="close" size={12} className="mr-1 inline align-[-2px]" />
          Invalid amount:{' '}
          <span className="font-mono-numbers">{audit.invalidFields.join(', ')}</span>
        </p>
      ) : audit.matches ? (
        <p className="text-ui font-semibold">
          <Icon name="check" size={12} className="mr-1 inline align-[-2px]" />
          <span className="font-mono-numbers">{matchBreakdown(audit.message)}</span>
        </p>
      ) : (
        <p className="text-ui font-semibold">
          Math Mismatch:{' '}
          <span className="font-mono-numbers">{audit.message}</span>
        </p>
      )}

      {missingSst && (
        <span className="stamp bg-warning-bg border-warning-border text-warning-text">
          <Icon name="alert" size={12} /> Missing SST on registered merchant
        </span>
      )}

      {dirty && <span className="ml-auto text-label text-text-muted">Unsaved changes</span>}
    </div>
  );
}
