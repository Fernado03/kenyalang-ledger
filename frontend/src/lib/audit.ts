/**
 * Client-side math reconciliation for SCR-03 (docs/03_appflow.md §3.5).
 *
 * The console audits what is printed on the receipt: the sum of the line_total
 * column versus the grand total — never qty × unit_price.
 *
 * Whether tax is added to that sum depends on the receipt's tax basis
 * (TRD §5.4). Malaysian retail receipts print GST-inclusive line totals, so
 * adding the tax again would flag every correct receipt with a delta exactly
 * equal to the GST. This mirrors `resolve_amount_basis` / `_math_discrepancy`
 * in backend `services/reconciler.py`; the two must agree or the console and
 * the server will disagree about the same receipt.
 */
import { formatCents, parseMoneyToCents, parseSignedMoneyToCents } from '../lib/format';
import type { ReceiptDraft } from '../types/receipt';

/** Outcome of one reconciliation pass over a draft. */
export interface MathAudit {
  lineCents: bigint;
  taxCents: bigint;
  /** Signed printed rounding adjustment, 0 when the receipt prints none. */
  roundingCents: bigint;
  totalCents: bigint;
  deltaCents: bigint;
  matches: boolean;
  /** False when a money field cannot be parsed or a line is out of range. */
  valid: boolean;
  /** Human-readable labels of the offending fields, in draft order. */
  invalidFields: string[];
  message: string;
  missingSstOnRegisteredMerchant: boolean;
  /** `INCLUSIVE` when the line totals already contain the tax (TRD §5.4). */
  basis: string;
  /** True when tax is inside the line totals rather than added on top. */
  taxInLines: boolean;
}

/** LHDN SST registration number shape, e.g. `W10-1808-32000018`.
 *
 * Anchors are deliberately dropped: receipts print the SST ID beside the BRN
 * ("200401032489 / Y24-1808-31015655"), so a full-match test would hide the
 * missing-tax chip on a genuinely SST-registered merchant. Mirrors
 * `extract_sst_number` in backend `services/reconciler.py`.
 */
const SST_NUMBER_PATTERN = /[A-Z]\d+-\d+-\d+/;

/** True when the field carries a well-formed SST registration number. */
export function hasSstNumber(value: string | null | undefined): boolean {
  if (!value) return false;
  return SST_NUMBER_PATTERN.test(value.trim().toUpperCase());
}

/** Tolerance in cents: Δ ≤ RM 0.02 counts as reconciled. */
const TOLERANCE_CENTS = 2n;

/** Canonical basis labels, mirroring the backend schema. */
export const BASIS_INCLUSIVE = 'INCLUSIVE';
export const BASIS_EXCLUSIVE = 'EXCLUSIVE';

/**
 * Resolve whether this draft's line totals already contain the tax.
 *
 * An explicit label wins. Otherwise infer from the numbers, testing exclusive
 * first so a receipt with no tax keeps the historical behaviour.
 */
export function resolveAmountBasis(
  draft: Pick<
    ReceiptDraft,
    'amount_basis' | 'line_items' | 'tax_amount' | 'grand_total' | 'rounding'
  >,
): string {
  const explicit = draft.amount_basis?.trim().toUpperCase();
  if (explicit === BASIS_INCLUSIVE) return BASIS_INCLUSIVE;
  if (explicit === BASIS_EXCLUSIVE) return BASIS_EXCLUSIVE;

  const totalCents = parseMoneyToCents(draft.grand_total);
  if (totalCents === null || draft.line_items.length === 0) return BASIS_EXCLUSIVE;

  let lineCents = 0n;
  for (const item of draft.line_items) {
    const lineTotal = parseMoneyToCents(item.line_total);
    if (lineTotal === null) return BASIS_EXCLUSIVE;
    lineCents += lineTotal;
  }
  const taxCents = parseMoneyToCents(draft.tax_amount) ?? 0n;
  const roundingCents = parseSignedMoneyToCents(draft.rounding) ?? 0n;

  const exclusiveDelta = lineCents + taxCents + roundingCents - totalCents;
  const exclusiveMagnitude = exclusiveDelta < 0n ? -exclusiveDelta : exclusiveDelta;
  if (exclusiveMagnitude <= TOLERANCE_CENTS) return BASIS_EXCLUSIVE;

  const inclusiveDelta = lineCents + roundingCents - totalCents;
  const inclusiveMagnitude = inclusiveDelta < 0n ? -inclusiveDelta : inclusiveDelta;
  if (inclusiveMagnitude <= TOLERANCE_CENTS) return BASIS_INCLUSIVE;

  return BASIS_EXCLUSIVE;
}

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
  });

  // A blank tax is not an error: the PUT sends null and the API accepts it, so
  // it contributes zero to the sum (and the SST advisory covers the real case).
  const taxCents = parseMoneyToCents(draft.tax_amount);
  const totalCents = parseMoneyToCents(draft.grand_total);
  if (totalCents === null) {
    invalidFields.push('Grand Total');
  }

  const valid = invalidFields.length === 0;
  const resolvedTax = taxCents ?? 0n;
  const resolvedTotal = totalCents ?? 0n;
  // A printed till-rounding line ("ROUNDING -0.04") is part of the receipt's own
  // arithmetic. Leaving it out of the identity reported a RM 0.04 error on a
  // receipt that balanced, which no amount of editing can fix.
  const resolvedRounding = parseSignedMoneyToCents(draft.rounding) ?? 0n;
  const basis = resolveAmountBasis(draft);
  const taxInLines = basis === BASIS_INCLUSIVE;
  // Inclusive lines already contain the tax, so adding it again would report a
  // delta exactly equal to the GST on every correct Malaysian retail receipt.
  const expectedCents = (taxInLines ? lineCents : lineCents + resolvedTax) + resolvedRounding;
  const deltaCents = expectedCents - resolvedTotal;
  const magnitude = deltaCents < 0n ? -deltaCents : deltaCents;
  const matches = valid && magnitude <= TOLERANCE_CENTS;

  // Only name the rounding term when the receipt actually prints one; an
  // unconditional "+ Rounding RM 0.00" is noise on the overwhelming majority of
  // receipts that round to nothing.
  const roundingTerm = resolvedRounding === 0n
    ? ''
    : ` ${resolvedRounding < 0n ? '−' : '+'} Rounding RM ${formatCents(
        resolvedRounding < 0n ? -resolvedRounding : resolvedRounding,
      )}`;
  const linesTerm = taxInLines
    ? `Line items total RM ${formatCents(lineCents)} (GST inclusive)`
    : `Line items total RM ${formatCents(lineCents)} + Tax RM ${formatCents(resolvedTax)}`;
  const breakdown = `${linesTerm}${roundingTerm} = Grand Total RM ${formatCents(resolvedTotal)}`;
  const mismatchBreakdown = `${linesTerm}${roundingTerm} ≠ Grand Total RM ${formatCents(
    resolvedTotal,
  )} (Difference: RM ${formatCents(magnitude)})`;

  const missingSstOnRegisteredMerchant =
    resolvedTax === 0n && hasSstNumber(draft.merchant_sst);

  return {
    lineCents,
    taxCents: resolvedTax,
    roundingCents: resolvedRounding,
    totalCents: resolvedTotal,
    deltaCents,
    matches,
    valid,
    invalidFields,
    message: valid ? (matches ? `Math Matches — ${breakdown}` : mismatchBreakdown) : mismatchBreakdown,
    missingSstOnRegisteredMerchant,
    basis,
    taxInLines,
  };
}
