import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getDashboardSummary } from '../api/client';
import type { DashboardSummary } from '../api/client';
import AppShell from '../components/AppShell';
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../components/DataStates';
import { useReceiptStore } from '../store/receiptStore';

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

const HEADER_CLASS =
  'px-3 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-text-muted';
const CELL_CLASS = 'px-3 py-2 text-sm text-text-secondary';

/** SCR-06 spend dashboard: month total, top suppliers, category split. */
export default function DashboardPage() {
  const { clientId } = useParams<{ clientId: string }>();
  const [month, setMonth] = useState(currentMonth);
  const [reloadKey, setReloadKey] = useState(0);
  const [result, setResult] = useState<{
    requestKey: string;
    summary: DashboardSummary | null;
    error: string | null;
  }>({ requestKey: '', summary: null, error: null });
  const clients = useReceiptStore((state) => state.clients);
  const loadClients = useReceiptStore((state) => state.loadClients);
  const client = clients.find((item) => item.id === clientId) ?? null;

  useEffect(() => {
    if (clients.length === 0) {
      void loadClients();
    }
  }, [clients.length, loadClients]);

  // The response is tagged with the request it answers, so a month change
  // shows the loading state without a setState in the effect body.
  const requestKey = `${clientId ?? ''}|${month}|${reloadKey}`;
  const loading = clientId !== undefined && result.requestKey !== requestKey;
  const summary = loading ? null : result.summary;
  const error = loading ? null : result.error;

  useEffect(() => {
    if (!clientId) return;
    let active = true;
    void getDashboardSummary(clientId, month || undefined)
      .then((next) => {
        if (active) setResult({ requestKey, summary: next, error: null });
      })
      .catch((err: unknown) => {
        if (!active) return;
        setResult({
          requestKey,
          summary: null,
          error: err instanceof Error ? err.message : 'Failed to load dashboard',
        });
      });
    return () => {
      active = false;
    };
  }, [clientId, month, requestKey]);

  if (!clientId) {
    return (
      <AppShell>
        <div className="p-6">
          <ErrorBanner message="No workspace client selected." />
        </div>
      </AppShell>
    );
  }

  const maxCategorySpend = Math.max(
    0,
    ...(summary?.category_breakdown ?? []).map((row) => Number(row.total_spend) || 0),
  );

  return (
    <AppShell clientId={clientId}>
      <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-5 shadow-card sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
              Dashboard
            </h1>
            <p className="mt-1 text-xs text-text-secondary">
              {client?.business_name ?? 'Client workspace'} · verified and exported
              receipts only
            </p>
          </div>
          <div className="flex items-end gap-3">
            <div>
              <label
                htmlFor="dashboard-month"
                className="block text-xs font-semibold uppercase tracking-wider text-text-secondary"
              >
                Month
              </label>
              <input
                id="dashboard-month"
                type="month"
                value={month}
                onChange={(event) => setMonth(event.target.value)}
                className="mt-1 h-11 border border-border bg-canvas px-3 text-sm font-mono-numbers text-text-primary focus-visible:border-border-focus focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-900"
              />
            </div>
            <Link
              to={`/clients/${clientId}/inbox`}
              className="inline-flex h-11 items-center rounded-lg border border-border bg-surface px-3 text-xs font-medium text-text-secondary hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-900"
            >
              ← Inbox
            </Link>
          </div>
        </div>

        {error !== null ? (
          <ErrorBanner message={error} onRetry={() => setReloadKey((key) => key + 1)} />
        ) : null}

        {loading ? (
          <LoadingSkeleton rows={4} />
        ) : summary === null ? (
          <EmptyState
            title="No dashboard data"
            hint="Verified receipts for this month will appear here."
          />
        ) : (
          <>
            <section className="rounded-xl border border-brand-900 bg-brand-900 px-6 py-5 text-white shadow-card">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-brand-50/80">
                Total spend · {summary.month}
              </h2>
              <p className="mt-2 font-mono-numbers text-4xl font-semibold tracking-tight text-white">
                {summary.total_spend}
              </p>
            </section>

            <section className="overflow-hidden rounded-xl border border-border bg-surface shadow-card">
              <h2 className="p-5 pb-3 text-sm font-semibold text-text-primary">
                Top suppliers
              </h2>
              {summary.top_suppliers.length === 0 ? (
                <p className="px-5 pb-5 text-sm text-text-secondary">
                  No supplier totals for this month.
                </p>
              ) : (
                <div className="relative overflow-x-auto">
                <table className="w-full min-w-[20rem]" aria-label="Top suppliers by spend">
                  <thead className="border-y border-border bg-surface-subtle/70">
                    <tr>
                      <th className={HEADER_CLASS}>Supplier</th>
                      <th className={`${HEADER_CLASS} text-right`}>Receipts</th>
                      <th className={`${HEADER_CLASS} text-right`}>Spend</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.top_suppliers.map((supplier) => (
                      <tr
                        key={supplier.supplier_name}
                        className="h-dense-row border-b border-border last:border-b-0 hover:bg-surface-subtle/60"
                      >
                        <td className="px-3 py-2 text-sm font-semibold text-text-primary">
                          {supplier.supplier_name}
                        </td>
                        <td className={`${CELL_CLASS} text-right font-mono-numbers`}>
                          {supplier.receipt_count}
                        </td>
                        <td className={`${CELL_CLASS} text-right font-mono-numbers`}>
                          {supplier.total_spend}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              )}
            </section>

            <section className="rounded-xl border border-border bg-surface shadow-card">
              <h2 className="px-5 pt-5 text-sm font-semibold text-text-primary">
                Spend by category
              </h2>
              <p className="px-5 pt-1 text-[11px] text-text-muted">
                Pre-tax line totals; document tax is excluded.
              </p>
              <ul className="space-y-3 p-5">
                {summary.category_breakdown.map((row) => {
                  const width =
                    maxCategorySpend > 0
                      ? `${Math.max(
                          2,
                          ((Number(row.total_spend) || 0) / maxCategorySpend) * 100,
                        )}%`
                      : '0%';
                  return (
                    <li key={row.category}>
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-text-primary">
                          {row.category}
                        </span>
                        <span className="font-mono-numbers text-text-secondary">
                          {row.total_spend}
                        </span>
                      </div>
                      <div
                        className="mt-1 h-2 w-full rounded-full bg-surface-subtle"
                        role="img"
                        aria-label={`${row.category}: ${row.total_spend}`}
                      >
                        <div className="h-2 rounded-full bg-brand-700" style={{ width }} />
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          </>
        )}
      </div>
    </AppShell>
  );
}
