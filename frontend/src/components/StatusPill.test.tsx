import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import StatusPill from './StatusPill';

describe('StatusPill', () => {
  it('treats negative and NaN confidence as unknown', () => {
    const { rerender } = render(
      <StatusPill status="STATUS_NEEDS_REVIEW" flags={[]} confidence={Number.NaN} />,
    );
    expect(screen.getByText(/Needs review/)).toBeInTheDocument();
    expect(screen.queryByText(/OCR check/)).not.toBeInTheDocument();

    rerender(<StatusPill status="STATUS_NEEDS_REVIEW" flags={[]} confidence={-0.4} />);
    expect(screen.getByText(/Needs review/)).toBeInTheDocument();
    expect(screen.queryByText(/OCR check/)).not.toBeInTheDocument();
  });

  it('treats null confidence as unknown and shows the plain needs-review pill', () => {
    render(<StatusPill status="STATUS_NEEDS_REVIEW" flags={[]} confidence={null} />);
    expect(screen.getByText(/Needs review/)).toBeInTheDocument();
    expect(screen.queryByText(/OCR check/)).not.toBeInTheDocument();
    expect(screen.queryByText(/0%/)).not.toBeInTheDocument();
  });

  it('does not print an out-of-range score above 100%', () => {
    render(<StatusPill status="STATUS_NEEDS_REVIEW" flags={[]} confidence={1.2} />);
    expect(screen.getByText(/Needs review/)).toBeInTheDocument();
    expect(screen.queryByText(/120%/)).not.toBeInTheDocument();
  });

  it('shows low confidence as text, not colour alone', () => {
    render(<StatusPill status="STATUS_NEEDS_REVIEW" flags={[]} confidence={0.42} />);
    expect(screen.getByText('OCR check 42%')).toBeInTheDocument();
  });

  it('shows the math delta from the mismatch flag', () => {
    render(<StatusPill status="STATUS_NEEDS_REVIEW" flags={['MATH_MISMATCH_DELTA_1.50']} />);
    expect(screen.getByText('Off by RM 1.50')).toBeInTheDocument();
    expect(screen.queryByText(/OCR check/)).not.toBeInTheDocument();
  });

  it('renders ERR_EXTRACTION as a terminal error with the backend message', () => {
    render(
      <StatusPill
        status="ERR_EXTRACTION"
        flags={[]}
        processingError="extraction provider unavailable"
      />,
    );
    const pill = screen.getByText('Extraction failed');
    expect(pill).toBeInTheDocument();
    expect(pill.closest('[data-status]')).toHaveAttribute('data-status', 'ERR_EXTRACTION');
    expect(pill.closest('[data-status]')).toHaveAttribute('title', 'extraction provider unavailable');
  });

  it('labels a processing status without exposing an error', () => {
    render(<StatusPill status="PROCESSING_OCR" flags={[]} />);
    expect(screen.getByText(/Processing/)).toBeInTheDocument();
  });
});
