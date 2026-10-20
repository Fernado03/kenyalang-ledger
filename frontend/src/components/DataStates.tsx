interface EmptyStateProps {
  title: string;
  hint?: string;
  action?: React.ReactNode;
}

interface LoadingSkeletonProps {
  rows: number;
}

interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
}

/** Full-width SCR-02 blank state: message, optional hint, optional action. */
export function EmptyState({ title, hint, action }: EmptyStateProps): JSX.Element {
  return (
    <div className="flex min-h-11 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-surface px-6 py-12 text-center shadow-card">
      <p className="text-sm font-semibold text-text-primary">{title}</p>
      {hint !== undefined && <p className="text-xs text-text-secondary">{hint}</p>}
      {action}
    </div>
  );
}

/** Shimmering SCR-02 table placeholder; one row per expected receipt. */
export function LoadingSkeleton({ rows }: LoadingSkeletonProps): JSX.Element {
  return (
    <div
      className="overflow-hidden rounded-xl border border-border bg-surface shadow-card"
      role="status"
      aria-busy="true"
    >
      <span className="sr-only">Loading receipts</span>
      {Array.from({ length: Math.max(rows, 1) }, (_unused, index) => (
        <div
          key={index}
          className="h-12 animate-pulse border-b border-border bg-surface-subtle/60 last:border-b-0"
        />
      ))}
    </div>
  );
}

/** Inline (non-toast) error banner with an accessible retry action. */
export function ErrorBanner({ message, onRetry }: ErrorBannerProps): JSX.Element {
  return (
    <div
      role="alert"
      className="flex min-h-11 flex-wrap items-center justify-between gap-2 rounded-xl border border-mismatch-border bg-mismatch-bg px-4 py-3 text-mismatch-text shadow-card"
    >
      <p className="text-xs">{message}</p>
      {onRetry !== undefined && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex min-h-11 items-center border border-mismatch-border bg-surface px-3 text-xs font-medium text-mismatch-text focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none"
        >
          Retry
        </button>
      )}
    </div>
  );
}
