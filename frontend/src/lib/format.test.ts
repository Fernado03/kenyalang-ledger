import { describe, expect, it } from 'vitest';
import {
  formatCents,
  formatConfidence,
  formatDate,
  formatMoneyDisplay,
  parseMoneyToCents,
} from './format';

describe('parseMoneyToCents', () => {
  it('returns null for blank and unparseable input', () => {
    expect(parseMoneyToCents('')).toBeNull();
    expect(parseMoneyToCents('   ')).toBeNull();
    expect(parseMoneyToCents(null)).toBeNull();
    expect(parseMoneyToCents('abc')).toBeNull();
  });

  it('rejects more than two fraction digits instead of rounding', () => {
    expect(parseMoneyToCents('1.005')).toBeNull();
    expect(parseMoneyToCents('10.999')).toBeNull();
  });

  it('parses exact cents without floating point drift', () => {
    expect(parseMoneyToCents('1.00')).toBe(100n);
    expect(parseMoneyToCents('1')).toBe(100n);
    expect(parseMoneyToCents('1.1')).toBe(110n);
    expect(parseMoneyToCents('0.01')).toBe(1n);
    expect(parseMoneyToCents('1234567.89')).toBe(123456789n);
    expect(parseMoneyToCents(12.34)).toBe(1234n);
  });

  it('accepts RM prefixes, spaces, and thousands separators', () => {
    expect(parseMoneyToCents('RM 1,234.50')).toBe(123450n);
    expect(parseMoneyToCents('rm99')).toBe(9900n);
    expect(parseMoneyToCents(' 8.20 ')).toBe(820n);
  });

  it('rejects negative and exponent notation', () => {
    expect(parseMoneyToCents('-5.00')).toBeNull();
    expect(parseMoneyToCents('1e3')).toBeNull();
  });
});

describe('formatCents', () => {
  it('always renders two fraction digits', () => {
    expect(formatCents(0n)).toBe('0.00');
    expect(formatCents(5n)).toBe('0.05');
    expect(formatCents(123450n)).toBe('1234.50');
  });

  it('renders negative cents with a leading sign', () => {
    expect(formatCents(-5n)).toBe('-0.05');
    expect(formatCents(-123450n)).toBe('-1234.50');
  });
});

describe('formatMoneyDisplay', () => {
  it('shows an em dash when the value is missing or invalid', () => {
    expect(formatMoneyDisplay(null)).toBe('—');
    expect(formatMoneyDisplay('abc')).toBe('—');
  });

  it('prefixes a valid amount with RM', () => {
    expect(formatMoneyDisplay('1')).toBe('RM 1.00');
    expect(formatMoneyDisplay('0.5')).toBe('RM 0.50');
    expect(formatMoneyDisplay('1234.50')).toBe('RM 1234.50');
  });
});

describe('formatDate', () => {
  it('formats ISO dates as DD/MM/YYYY', () => {
    expect(formatDate('2026-10-19')).toBe('19/10/2026');
    expect(formatDate('2026-10-19T08:30:00+08:00')).toBe('19/10/2026');
  });

  it('falls back to a dash for absent or malformed input', () => {
    expect(formatDate(null)).toBe('-');
    expect(formatDate('19/10/2026')).toBe('-');
  });
});

describe('formatConfidence', () => {
  it('rounds a 0..1 score to a whole percentage', () => {
    expect(formatConfidence(0)).toBe('0%');
    expect(formatConfidence(0.814)).toBe('81%');
    expect(formatConfidence(1)).toBe('100%');
  });

  it('treats absent confidence (null or undefined) as unknown', () => {
    expect(formatConfidence(null)).toBe('—');
    expect(formatConfidence(undefined)).toBe('—');
    expect(formatConfidence(0)).toBe('0%');
  });

  it('clamps above 1 and treats non-finite or negative values as unknown', () => {
    expect(formatConfidence(1.2)).toBe('100%');
    expect(formatConfidence(Number.NaN)).toBe('—');
    expect(formatConfidence(Number.POSITIVE_INFINITY)).toBe('—');
    expect(formatConfidence(-0.1)).toBe('—');
  });
});
