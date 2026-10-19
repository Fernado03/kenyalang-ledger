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
  /** False when a money field cannot be parsed or a line is out of range. */
  valid: boolean;
  /** Human-readable labels of the offending fields, in draft order. */
  invalidFields: string[];
  message: string;
  missingSstOnRegisteredMerchant: boolean;
}

/** LHDN SST registration number shape, e.g. `W10-1808-32000018`. */
const SST_NUMBER_PATTERN = /^[A-Z]\d+-\d+-\d+$/;

/** Tolerance in cents: Δ ≤ RM 0.02 counts as reconciled. */
const TOLERANCE_CENTS = 2n;

/** Runs the §3.5 reconciliation rules over the current draft. */
export function auditMath(draft: ReceiptDraft): MathAudit {
  const invalidFields: string[] = [];
  let lineCents = 0n;

  draft.line_items.forEach((item, index) => {
    const label = `Line ${index + 1}`;
    const quantity = parseMoneyToCents(item.quantity);
    const unitPrice = parseMoneyToCents(item.unit_price);
    const lineTotal = parseMoneyToCents(item.line_total);

    if (quantity === null || quantity <= 0n) {
      invalidFields.push(`${label} quantity`);
    }
    if (unitPrice === null) {
      invalidFields.push(`${label} unit price`);
    }
    if (lineTotal === null) {
      invalidFields.push(`${label} total`);
    } else {
      lineCents += lineTotal;
    }
    // qty × unit price is in hundredths-of-cents (qty is a plain count).
    if (quantity !== null && unitPrice !== null && lineTotal !== null) {
      const expected = quantity * unitPrice;
      const difference = expected - lineTotal * 100n;
      if ((difference < 0n ? -difference : difference) > TOLERANCE_CENTS * 100n) {
        invalidFields.push(`${label} total ≠ qty × unit price`);
      }
    }
  });

  const taxCents = parseMoneyToCents(draft.tax_amount);
  if (taxCents === null) {
    invalidFields.push('SST');
  }
  const totalCents = parseMoneyToCents(draft.grand_total);
  if (totalCents === null) {
    invalidFields.push('Grand Total');
  }

  const valid = invalidFields.length === 0;
  const resolvedTax = taxCents ?? 0n;
  const resolvedTotal = totalCents ?? 0n;
  const deltaCents = lineCents + resolvedTax - resolvedTotal;
  const magnitude = deltaCents < 0n ? -deltaCents : deltaCents;
  const matches = valid && magnitude <= TOLERANCE_CENTS;

  const breakdown = `Line items total RM ${formatCents(lineCents)} + Tax RM ${formatCents(
    resolvedTax,
  )} = Grand Total RM ${formatCents(resolvedTotal)}`;
  const mismatchBreakdown = `Line items total RM ${formatCents(
    lineCents,
  )} + Tax RM ${formatCents(resolvedTax)} ≠ Grand Total RM ${formatCents(
    resolvedTotal,
  )} (Difference: RM ${formatCents(magnitude)})`;

  const missingSstOnRegisteredMerchant =
    resolvedTax === 0n && SST_NUMBER_PATTERN.test(draft.merchant_sst.trim());

  return {
    lineCents,
    taxCents: resolvedTax,
    totalCents: resolvedTotal,
    deltaCents,
    matches,
    valid,
    invalidFields,
    message: valid ? (matches ? `Math Matches — ${breakdown}` : mismatchBreakdown) : mismatchBreakdown,
    missingSstOnRegisteredMerchant,
  };
}
