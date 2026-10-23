import { describe, expect, it } from 'vitest';
import { auditMath, resolveAmountBasis } from './audit';
import type { ReceiptDraft } from '../types/receipt';

function draft(overrides: Partial<ReceiptDraft> = {}): ReceiptDraft {
  return {
    merchant_name: 'Kedai Hardware',
    merchant_brn: '202301234567',
    merchant_sst: '',
    invoice_date: '2026-10-01',
    invoice_number: 'INV-1',
    subtotal: '10.00',
    tax_amount: '1.00',
    grand_total: '11.00',
    rounding: '',
    amount_basis: null,
    line_items: [
      {
        key: 'line-1',
        description: 'PVC pipe',
        quantity: '1',
        unit_price: '10.00',
        line_total: '10.00',
      },
    ],
    ...overrides,
  };
}

describe('auditMath', () => {
  it('reports exact totals as a match', () => {
    const result = auditMath(draft());

    expect(result.valid).toBe(true);
    expect(result.matches).toBe(true);
    expect(result.lineCents).toBe(1000n);
    expect(result.taxCents).toBe(100n);
    expect(result.totalCents).toBe(1100n);
    expect(result.deltaCents).toBe(0n);
    expect(result.invalidFields).toEqual([]);
    expect(result.message).toContain('Math Matches');
  });

  it('reports a one-cent mismatch but keeps it inside the 2-cent tolerance', () => {
    const result = auditMath(draft({ grand_total: '11.01' }));

    expect(result.valid).toBe(true);
    expect(result.matches).toBe(true);
    expect(result.deltaCents).toBe(-1n);
    expect(result.message).toContain('Math Matches');
  });

  it('fails reconciliation once the delta exceeds 2 cents', () => {
    const result = auditMath(draft({ grand_total: '11.03' }));

    expect(result.valid).toBe(true);
    expect(result.matches).toBe(false);
    expect(result.deltaCents).toBe(-3n);
    expect(result.message).toContain('Difference: RM 0.03');
  });

  it('still treats a two-cent delta as reconciled', () => {
    const result = auditMath(draft({ grand_total: '11.02' }));

    expect(result.valid).toBe(true);
    expect(result.matches).toBe(true);
  });

  it('marks an unparseable line total as invalid and not matching', () => {
    const result = auditMath(
      draft({
        line_items: [
          {
            key: 'line-1',
            description: 'PVC pipe',
            quantity: '1',
            unit_price: '10.00',
            line_total: 'abc',
          },
        ],
      }),
    );

    expect(result.valid).toBe(false);
    expect(result.matches).toBe(false);
    expect(result.invalidFields).toContain('Line 1 total');
    expect(result.message).toContain('≠ Grand Total');
  });

  it('treats blank tax as zero and reports SST registration separately', () => {
    const result = auditMath(
      draft({
        merchant_sst: 'W10-1808-32000018',
        tax_amount: '',
        grand_total: '10.00',
      }),
    );

    expect(result.valid).toBe(true);
    expect(result.matches).toBe(true);
    expect(result.taxCents).toBe(0n);
    expect(result.missingSstOnRegisteredMerchant).toBe(true);
  });

  it('rejects non-positive quantity but trusts the printed line total', () => {
    const result = auditMath(
      draft({
        line_items: [
          {
            key: 'line-1',
            description: 'PVC pipe',
            quantity: '0',
            unit_price: '10.00',
            line_total: '10.00',
          },
          {
            key: 'line-2',
            description: 'Elbow',
            quantity: '2',
            unit_price: '3.00',
            line_total: '7.00',
          },
        ],
        subtotal: '17.00',
        tax_amount: '0.00',
        grand_total: '17.00',
      }),
    );

    expect(result.valid).toBe(false);
    expect(result.invalidFields).toContain('Line 1 quantity');
    expect(result.invalidFields).not.toContain('Line 2 total ≠ qty × unit price');
  });

  it('detects a zero-tax receipt from an SST-registered merchant', () => {
    const result = auditMath(
      draft({
        merchant_sst: 'W10-1808-32000018',
        tax_amount: '0.00',
        grand_total: '10.00',
      }),
    );

    expect(result.missingSstOnRegisteredMerchant).toBe(true);

    const untaxedPlain = auditMath(
      draft({ merchant_sst: '', tax_amount: '0.00', grand_total: '10.00' }),
    );
    expect(untaxedPlain.missingSstOnRegisteredMerchant).toBe(false);
  });

  it('detects an SST number printed alongside the BRN', () => {
    // What extraction produces from a "No. Pendaftaran (BRN) / SST ID" header.
    const combined = auditMath(
      draft({
        merchant_sst: '200401032489 / Y24-1808-31015655',
        tax_amount: '0.00',
        grand_total: '10.00',
      }),
    );

    expect(combined.missingSstOnRegisteredMerchant).toBe(true);

    const lowercase = auditMath(
      draft({
        merchant_sst: 'y24-1808-31015655',
        tax_amount: '0.00',
        grand_total: '10.00',
      }),
    );
    expect(lowercase.missingSstOnRegisteredMerchant).toBe(true);
  });
});

describe('tax basis (H1)', () => {
  /** The audit's 100.jpg: lines 7.42, GST 0.42, total 7.42 — GST inclusive. */
  const inclusiveReceipt = (overrides: Partial<ReceiptDraft> = {}): ReceiptDraft =>
    draft({
      subtotal: '7.00',
      tax_amount: '0.42',
      grand_total: '7.42',
      line_items: [
        {
          key: 'line-1',
          description: 'BEG GUNI',
          quantity: '1',
          unit_price: '7.42',
          line_total: '7.42',
        },
      ],
      ...overrides,
    });

  it('infers INCLUSIVE when the lines already equal the grand total', () => {
    expect(resolveAmountBasis(inclusiveReceipt())).toBe('INCLUSIVE');
  });

  it('does not double-count GST on an inclusive receipt', () => {
    const result = auditMath(inclusiveReceipt());

    expect(result.matches).toBe(true);
    expect(result.deltaCents).toBe(0n);
    expect(result.message).toContain('Math Matches');
    // The explanation must not claim tax is being added on top.
    expect(result.message).toContain('GST inclusive');
    expect(result.message).not.toContain('+ Tax RM 0.42');
  });

  it('still adds tax for an exclusive receipt', () => {
    const result = auditMath(draft());

    expect(resolveAmountBasis(draft())).toBe('EXCLUSIVE');
    expect(result.matches).toBe(true);
    expect(result.message).toContain('+ Tax RM 1.00');
  });

  it('honours an explicit basis over inference', () => {
    const explicit = inclusiveReceipt({ amount_basis: 'EXCLUSIVE' });

    expect(resolveAmountBasis(explicit)).toBe('EXCLUSIVE');
    // Reading 7.42 + 0.42 against 7.42 is a genuine 42-cent mismatch.
    expect(auditMath(explicit).deltaCents).toBe(42n);
  });

  it('reports the unexplained amount on a true mismatch', () => {
    // Basis pinned so the expectation does not depend on inference: lines 7.42
    // against a printed 8.00 leaves 58 cents unaccounted for.
    const result = auditMath(
      inclusiveReceipt({ amount_basis: 'INCLUSIVE', grand_total: '8.00' }),
    );

    expect(result.matches).toBe(false);
    expect(result.deltaCents).toBe(-58n);
    expect(result.message).toContain('Difference: RM 0.58');
  });

  it('treats a receipt with no lines as exclusive', () => {
    expect(
      resolveAmountBasis(
        inclusiveReceipt({ line_items: [], subtotal: '7.00', grand_total: '7.42' }),
      ),
    ).toBe('EXCLUSIVE');
  });
});

describe('printed rounding line', () => {
  const receipt = draft({
    tax_amount: '4.29',
    grand_total: '75.75',
    rounding: '-0.04',
    line_items: [
      { key: 'a', description: 'PAKU 2 INCI', quantity: '1', unit_price: '4.50', line_total: '4.50' },
      { key: 'b', description: 'CAT JOTUN', quantity: '1', unit_price: '38.00', line_total: '38.00' },
      { key: 'c', description: 'ROLLER BRUSH', quantity: '2', unit_price: '12.00', line_total: '24.00' },
      { key: 'd', description: 'AMPELAS', quantity: '5', unit_price: '1.00', line_total: '5.00' },
    ],
  });

  it('reconciles a receipt whose till rounded the total down', () => {
    const audit = auditMath(receipt);

    expect(audit.matches).toBe(true);
    expect(audit.roundingCents).toBe(-4n);
    expect(audit.message).toContain('− Rounding RM 0.04');
  });

  it('still reports the gap when the rounding line does not explain it', () => {
    const audit = auditMath({ ...receipt, rounding: '0.00', grand_total: '75.75' });

    expect(audit.matches).toBe(false);
    expect(audit.message).toContain('Difference: RM 0.04');
  });

  it('keeps the identity unchanged when no rounding line is printed', () => {
    const audit = auditMath({ ...receipt, rounding: '', grand_total: '75.79' });

    expect(audit.matches).toBe(true);
    expect(audit.roundingCents).toBe(0n);
    expect(audit.message).not.toContain('Rounding');
  });
});
