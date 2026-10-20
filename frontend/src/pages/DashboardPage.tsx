import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getDashboardSummary } from '../api/client';
import type { ClientSummary, DashboardSummary } from '../api/client';
import AppShell from '../components/AppShell';
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../components/DataStates';
import { Icon } from '../components/Icon';
import PageHeader from '../components/PageHeader';
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
  const loadClients = useReceiptStore((state) => state.loadClients);
  // The list endpoint carries the aggregates, but the store types clients as Client.
  const client = (clients as ClientSummary[]).find((item) => item.id === clientId) ?? null;

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
        <div className="page-shell">
          <ErrorBanner message="No workspace client selected." />
        </div>
      </AppShell>
    );
  }

  const reviewed = client === null ? '—' : String(client.verified_count ?? 0);
  const needsReview = client === null ? '—' : String(client.unreviewed_count ?? 0);
  const totalReceipts =
    client === null ? '—' : String((client.verified_count ?? 0) + (client.unreviewed_count ?? 0));

  return (
    <AppShell clientId={clientId}>
      <div className="page-shell space-y-7">
        <PageHeader
          eyebrow={`WORKSPACE · ${client?.registration_number ?? 'CLIENTS'}`}
          title="Dashboard"
          meta={
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="text-text-primary">
                {client?.business_name ?? 'Client workspace'}
              </span>
              <span aria-hidden="true" className="text-text-muted">
                ·
              </span>
              <span className="text-label text-text-muted">
                verified and exported receipts only
              </span>
              <Link to={`/clients/${clientId}/inbox`} className="link-quiet text-label">
                <Icon name="arrow-left" size={14} />
                Inbox
              </Link>
            </div>
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
                className="field-input mt-0 w-auto font-mono-numbers"
              />
            </div>
          }
        />

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
            <dl className="grid grid-cols-1 gap-px border-y border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
              {[
                { label: 'Spend this month', value: formatMoneyDisplay(summary.total_spend) },
                { label: 'Receipts reviewed', value: reviewed },
                { label: 'Needs review', value: needsReview },
                { label: 'Total receipts', value: totalReceipts },
              ].map((stat) => (
                <div key={stat.label} className="bg-canvas px-4 py-4 sm:px-5 sm:py-5">
                  <dt className="section-label">{stat.label}</dt>
                  <dd className="mt-1.5 break-words font-mono-numbers text-title text-text-primary sm:text-display">
                    {stat.value}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="-mt-4 text-label text-text-muted">
              Spend covers the selected month; receipt counts cover the whole workspace.
            </p>

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
