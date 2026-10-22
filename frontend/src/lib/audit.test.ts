import { describe, expect, it } from 'vitest';
import { auditMath } from './audit';
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
