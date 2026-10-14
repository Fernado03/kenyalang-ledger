/**
 * Client-side math reconciliation for SCR-03 (docs/03_appflow.md §3.5).
 *
 * The console audits what is printed on the receipt: the sum of the line_total
 * column plus tax versus the grand total — never qty × unit_price.
 */
import { formatCents, parseMoneyToCents } from '../lib/format';
import type { ReceiptDraft } from '../types/receipt';

/** Outcome of one reconciliation pass over a draft. */
export interface MathAudit {
  lineCents: bigint;
  taxCents: bigint;
  totalCents: bigint;
  deltaCents: bigint;
  matches: boolean;
  message: string;
  missingSstOnRegisteredMerchant: boolean;
}

/** LHDN SST registration number shape, e.g. `W10-1808-32000018`. */
const SST_NUMBER_PATTERN = /^[A-Z]\d+-\d+-\d+$/;

/** Tolerance in cents: Δ ≤ RM 0.02 counts as reconciled. */
const TOLERANCE_CENTS = 2n;

/** Runs the §3.5 reconciliation rules over the current draft. */
export function auditMath(draft: ReceiptDraft): MathAudit {
  let lineCents = 0n;
  for (const item of draft.line_items) {
    lineCents += parseMoneyToCents(item.line_total);
  }
  const taxCents = parseMoneyToCents(draft.tax_amount);
  const totalCents = parseMoneyToCents(draft.grand_total);
  const deltaCents = lineCents + taxCents - totalCents;
  const magnitude = deltaCents < 0n ? -deltaCents : deltaCents;
  const matches = magnitude <= TOLERANCE_CENTS;

  const breakdown = `Line items total RM ${formatCents(lineCents)} + Tax RM ${formatCents(
    taxCents,
  )} = Grand Total RM ${formatCents(totalCents)}`;
  const mismatchBreakdown = `Line items total RM ${formatCents(
    lineCents,
  )} + Tax RM ${formatCents(taxCents)} ≠ Grand Total RM ${formatCents(
    totalCents,
  )} (Difference: RM ${formatCents(magnitude)})`;

  const missingSstOnRegisteredMerchant =
    taxCents === 0n && SST_NUMBER_PATTERN.test(draft.merchant_sst.trim());

  return {
    lineCents,
    taxCents,
    totalCents,
    deltaCents,
    matches,
    message: matches ? `Math Matches — ${breakdown}` : mismatchBreakdown,
    missingSstOnRegisteredMerchant,
  };
}
