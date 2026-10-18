/**
 * Exact Ringgit formatting helpers (docs/05_trd.md §5.4: never accumulate money
 * in JS floats). All parsing/formatting goes through BigInt cents.
 */

/** Parses a decimal money string into exact BigInt cents. Invalid → 0n. */
export function parseMoneyToCents(value: string | number | null): bigint {
  if (value === null || value === undefined) {
    return 0n;
  }
  const cleaned = String(value)
    .trim()
    .replace(/^RM/i, '')
    .replace(/[\s,]/g, '');
  const match = /^(-?)(\d*)(?:\.(\d{1,3}))?$/.exec(cleaned);
  if (match === null || (match[2] === '' && match[3] === undefined)) {
    return 0n;
  }
  const [, sign, whole, fraction] = match;
  // Scale to thousandths first so a 3rd decimal rounds half-away-from-zero.
  const thousandths = BigInt(`${whole || '0'}${(fraction ?? '').padEnd(3, '0')}`);
  const rounded = thousandths / 10n;
  const remainder = thousandths % 10n;
  const halfUp = remainder !== 0n && remainder * 2n >= 10n;
  const cents = halfUp ? rounded + 1n : rounded;
  return sign === '-' ? -cents : cents;
}

/** Formats BigInt cents as a plain 2-decimal string with no currency symbol. */
export function formatCents(cents: bigint): string {
  const negative = cents < 0n;
  const absolute = negative ? -cents : cents;
  const ringgit = absolute / 100n;
  const sen = (absolute % 100n).toString().padStart(2, '0');
  return `${negative ? '-' : ''}${ringgit.toString()}.${sen}`;
}

/** Formats a money value for display as `RM 99.50`, or `-` when absent. */
export function formatMoneyDisplay(value: string | number | null): string {
  return value === null || value === undefined || value === ''
    ? '-'
    : `RM ${formatCents(parseMoneyToCents(value))}`;
}

/** Formats an ISO `YYYY-MM-DD` (or datetime) string as `DD/MM/YYYY`. */
export function formatDate(iso: string | null): string {
  if (iso === null || iso === undefined) {
    return '-';
  }
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return match === null ? '-' : `${match[2]}/${match[3]}/${match[1]}`;
}

/** Formats a 0..1 confidence score as a whole percentage (`94%`). */
export function formatConfidence(confidence: number): string {
  return Number.isFinite(confidence) ? `${Math.round(confidence * 100)}%` : '-';
}
