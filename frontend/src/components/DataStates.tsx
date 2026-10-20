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
    <div className="border-y border-border py-12 text-center">
      <p className="section-title">{title}</p>
      {hint !== undefined && <p className="mx-auto mt-2 max-w-md text-body text-text-secondary">{hint}</p>}
      {action !== undefined && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}

/** Ruled SCR-02 table placeholder; one row per expected receipt. */
export function LoadingSkeleton({ rows }: LoadingSkeletonProps): JSX.Element {
  return (
    <div role="status" aria-busy="true" className="border-y border-border">
      <span className="sr-only">Loading receipts</span>
      {Array.from({ length: Math.max(rows, 1) }, (_unused, index) => (
        <div
          key={index}
          className="flex h-12 items-center gap-4 border-b border-border px-1 last:border-b-0"
        >
          <span className="skeleton h-3 w-10" />
          <span className="skeleton h-3 flex-1" />
          <span className="skeleton h-3 w-24" />
        </div>
      ))}
    </div>
  );
}

/** Inline (non-toast) error banner with an accessible retry action. */
export function ErrorBanner({ message, onRetry }: ErrorBannerProps): JSX.Element {
  return (
    <div
      role="alert"
      className="flex min-h-11 flex-wrap items-center justify-between gap-2 border-l-[3px] border-mismatch-border bg-mismatch-bg/60 px-4 py-3 text-mismatch-text"
    >
      <p className="text-ui">{message}</p>
      {onRetry !== undefined && (
        <button type="button" onClick={onRetry} className="btn btn-secondary btn-sm">
          Retry
        </button>
      )}
    </div>
  );
}
