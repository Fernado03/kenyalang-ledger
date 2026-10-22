import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getDashboardSummary } from '../api/client';
import type { ClientSummary, DashboardSummary } from '../api/client';
import AppShell from '../components/AppShell';
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../components/DataStates';
import PageHeader, { PageMeta } from '../components/PageHeader';
import { formatMoneyDisplay } from '../lib/format';
import { useReceiptStore } from '../store/receiptStore';

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

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
  const clientsError = useReceiptStore((state) => state.clientsError);
  const loadClients = useReceiptStore((state) => state.loadClients);
  // The list endpoint carries the aggregates, but the store types clients as Client.
  const client = (clients as ClientSummary[]).find((item) => item.id === clientId) ?? null;

  // The response is tagged with the request it answers, so a month change
  // shows the loading state without a setState in the effect body.
  const requestKey = `${clientId ?? ''}|${month}|${reloadKey}`;
  const loading = clientId !== undefined && result.requestKey !== requestKey;
  const summary = loading ? null : result.summary;
  const error = loading ? null : result.error;

  // Counts and spend come from two endpoints, so one effect owns both: the
  // workspace aggregates are refreshed first, then the summary. Splitting them
  // let a verify on another page leave new counts beside a pre-verify spend.
  useEffect(() => {
    if (!clientId) return;
    let active = true;
    void (async () => {
      await loadClients();
      try {
        const next = await getDashboardSummary(clientId, month || undefined);
        if (active) setResult({ requestKey, summary: next, error: null });
      } catch (err) {
        if (!active) return;
        setResult({
          requestKey,
          summary: null,
          error: err instanceof Error ? err.message : 'Failed to load dashboard',
        });
      }
    })();
    return () => {
      active = false;
    };
  }, [clientId, month, requestKey, loadClients]);

  if (!clientId) {
    return (
      <AppShell>
        <div className="page-shell">
          <ErrorBanner message="No workspace client selected." />
        </div>
      </AppShell>
    );
  }

  const reviewed = client === null ? '—' : String(client.verified_count ?? 0);
  const needsReview = client === null ? '—' : String(client.unreviewed_count ?? 0);
  const totalReceipts = client === null ? '—' : String(client.total_count ?? 0);

  return (
    <AppShell clientId={clientId}>
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow={client?.registration_number ? `Workspace ${client.registration_number}` : 'Workspace'}
          title="Dashboard"
          meta={
            <PageMeta
              name={client?.business_name ?? 'Client workspace'}
              note="verified and exported receipts only"
              back={{ to: `/clients/${clientId}/inbox`, label: 'Inbox' }}
            />
          }
          actions={
            <div>
              <label htmlFor="dashboard-month" className="field-label">
                Month
              </label>
              <input
                id="dashboard-month"
                type="month"
                value={month}
                onChange={(event) => setMonth(event.target.value)}
                className="field-input w-auto font-mono-numbers"
              />
            </div>
          }
        />

        {clientsError !== null ? (
          <ErrorBanner message={clientsError} onRetry={() => void loadClients()} />
        ) : null}

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
            <section aria-labelledby="spend-heading">
              <h2 id="spend-heading" className="section-title">
                Spend this month
              </h2>
              <p className="mt-2 font-mono-numbers text-display-lg text-text-primary">
                {formatMoneyDisplay(summary.total_spend)}
              </p>
              <dl className="mt-6 grid grid-cols-1 gap-px border-y border-border bg-border sm:grid-cols-3">
                <div className="bg-canvas px-4 py-3">
                  <dt className="section-label">Receipts reviewed</dt>
                  <dd className="mt-1 font-mono-numbers text-title text-text-primary">{reviewed}</dd>
                </div>
                <div className="bg-canvas px-4 py-3">
                  <dt className="section-label">Needs review</dt>
                  <dd className="mt-1 font-mono-numbers text-title text-text-primary">
                    {needsReview}
                  </dd>
                </div>
                <div className="bg-canvas px-4 py-3">
                  <dt className="section-label">Total receipts</dt>
                  <dd className="mt-1 font-mono-numbers text-title text-text-primary">{totalReceipts}</dd>
                </div>
              </dl>
              <p className="mt-3 text-label text-text-muted">
                Spend covers the selected month; receipt counts cover the whole workspace.
              </p>
            </section>

            <section>
              <h2 className="section-title">Top suppliers</h2>
              {summary.top_suppliers.length === 0 ? (
                <p className="mt-2 text-ui text-text-secondary">
                  No supplier totals for this month.
                </p>
              ) : (
                <div className="mt-3 overflow-x-auto">
                  <table className="data-table" aria-label="Top suppliers by spend">
                    <thead>
                      <tr>
                        <th>Supplier</th>
                        <th className="text-right">Receipts</th>
                        <th className="text-right">Spend</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.top_suppliers.map((supplier) => (
                        <tr key={supplier.supplier_name}>
                          <td className="break-words font-semibold text-text-primary">
                            {supplier.supplier_name}
                          </td>
                          <td className="text-right font-mono-numbers">
                            {supplier.receipt_count}
                          </td>
                          <td className="text-right font-mono-numbers">
                            {formatMoneyDisplay(supplier.total_spend)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section>
              <h2 className="section-title">Spend by category</h2>
              <p className="mt-1 text-label text-text-muted">
                Pre-tax line totals; document tax is excluded.
              </p>
              <div className="mt-3 overflow-x-auto">
                <table className="data-table" aria-label="Spend by category">
                  <thead>
                    <tr>
                      <th>Category</th>
                      <th className="text-right">Spend</th>
                    </tr>
                  </thead>
                  <tbody>
                    {/* All five categories in taxonomy order: a zero row states
                        "no spend here", which is information (docs/04 §Dashboard). */}
                    {summary.category_breakdown.map((row) => (
                      <tr key={row.category}>
                        <td className="font-semibold text-text-primary">{row.category}</td>
                        <td className="text-right font-mono-numbers">
                          {formatMoneyDisplay(row.total_spend)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
    </AppShell>
  );
}
