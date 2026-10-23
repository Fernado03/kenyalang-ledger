/**
 * Exact Ringgit formatting helpers (docs/05_trd.md §5.4: never accumulate money
 * in JS floats). All parsing/formatting goes through BigInt cents.
 */

/** Unsigned decimal with at most two fraction digits; no signs or exponents. */
const MONEY_PATTERN = /^(\d+)(?:\.(\d{1,2}))?$/;
/** Same grammar, but a leading minus is allowed (rounding lines are signed). */
const SIGNED_MONEY_PATTERN = /^(-?)(\d+)(?:\.(\d{1,2}))?$/;

/** Parses a decimal money string into exact BigInt cents. Invalid → null. */
export function parseMoneyToCents(value: string | number | null): bigint | null {
  if (value === null || value === undefined) {
    return null;
  }
  const match = MONEY_PATTERN.exec(_cleanMoney(value));
  if (match === null) {
    return null;
  }
  return BigInt(match[1]) * 100n + BigInt((match[2] ?? '').padEnd(2, '0'));
}

/**
 * Parses a *signed* money string into exact BigInt cents, or null.
 *
 * Only the rounding line needs this: a printed till adjustment reads
 * "ROUNDING -0.04", and a parser that rejects the sign drops the adjustment and
 * reports the receipt as off by exactly that amount. Every other money field
 * stays unsigned — a negative total or line is a data error, not a value.
 */
export function parseSignedMoneyToCents(
  value: string | number | null,
): bigint | null {
  if (value === null || value === undefined) {
    return null;
  }
  const match = SIGNED_MONEY_PATTERN.exec(_cleanMoney(value));
  if (match === null) {
    return null;
  }
  const magnitude =
    BigInt(match[2]) * 100n + BigInt((match[3] ?? '').padEnd(2, '0'));
  return match[1] === '-' ? -magnitude : magnitude;
}

/** Trims, drops a currency marker and separators, keeping a leading sign. */
function _cleanMoney(value: string | number): string {
  return String(value)
    .trim()
    // Both "-RM 0.04" and "RM -0.04" appear on real receipts.
    .replace(/^(-?)RM/i, '$1')
    .replace(/[\s,]/g, '');
}

/** Formats BigInt cents as a plain 2-decimal string with no currency symbol. */
export function formatCents(cents: bigint): string {
  const negative = cents < 0n;
  const absolute = negative ? -cents : cents;
  const ringgit = absolute / 100n;
  const sen = (absolute % 100n).toString().padStart(2, '0');
  return `${negative ? '-' : ''}${ringgit.toString()}.${sen}`;
}

/** Formats a money value for display as `RM 99.50`, or an em dash when absent. */
export function formatMoneyDisplay(value: string | number | null): string {
  const cents = parseMoneyToCents(value);
  return cents === null ? '—' : `RM ${formatCents(cents)}`;
}

/** Formats an ISO `YYYY-MM-DD` (or datetime) string as `DD/MM/YYYY`. */
export function formatDate(iso: string | null): string {
  if (iso === null || iso === undefined) {
    return '-';
  }
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return match === null ? '-' : `${match[3]}/${match[2]}/${match[1]}`;
}

/**
 * Formats a 0..1 confidence score as a whole percentage. Absent (`null` /
 * `undefined`), non-finite, or negative scores are unknown → `—`; values above
 * 1 clamp to `100%`.
 */
export function formatConfidence(confidence: number | null | undefined): string {
  if (confidence === null || confidence === undefined) {
    return '—';
  }
  if (!Number.isFinite(confidence) || confidence < 0) {
    return '—';
  }
  return `${Math.round(Math.min(confidence, 1) * 100)}%`;
}
