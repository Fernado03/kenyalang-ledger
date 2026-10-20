import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ClientSummary } from '../api/client'
import AppShell from '../components/AppShell'
import ClientForm from '../components/ClientForm'
import { useReceiptStore } from '../store/receiptStore'

const COUNT_PLACEHOLDER = '-'

const HEADER_CLASS =
  'px-3 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-text-muted'

const CELL_CLASS = 'px-3 py-2 text-sm text-text-secondary'

const ACTION_BUTTON_CLASS =
  'flex h-11 items-center border border-border bg-surface px-3 text-sm text-text-primary transition-colors duration-100 ease-out hover:bg-surface-subtle focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none'

const PRIMARY_BUTTON_CLASS =
  'flex h-11 items-center rounded-lg border border-brand-900 bg-brand-900 px-4 text-sm font-semibold text-white shadow-sm transition-colors duration-100 ease-out hover:bg-brand-700 focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none'

/** One shimmering placeholder row for the loading state. */
function SkeletonRow({ columns }: { columns: number }) {
  return (
    <tr className="h-12 border-b border-border last:border-b-0">
      {Array.from({ length: columns }, (_unused, index) => (
        <td className="px-3 py-2" key={index}>
          <span className="block h-4 animate-pulse rounded-sm bg-surface-subtle" />
        </td>
      ))}
    </tr>
  )
}

/** Renders a receipt count, falling back for freshly created clients. */
function CountCell({ value }: { value: number | undefined }) {
  return (
    <td className={`${CELL_CLASS} font-mono-numbers`}>
      {value ?? 0}
    </td>
  )
}

/**
 * SCR-01 Client Workspace Switcher (docs/03 §3.3): dense client table plus the
 * inline create form. All 5 UX states are explicit.
 */
export default function ClientsPage() {
  const clients = useReceiptStore((state) => state.clients)
  const loadClients = useReceiptStore((state) => state.loadClients)
  const receiptsError = useReceiptStore((state) => state.receiptsError)

  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [formOpen, setFormOpen] = useState(false)

  useEffect(() => {
    let active = true
    void loadClients().finally(() => {
      if (active) setLoading(false)
    })
    return () => {
      active = false
    }
  }, [loadClients])

  // The list response already carries both aggregates, so no per-client calls.
  const summaries = clients as ClientSummary[]

  let body: ReactNode

  if (loading) {
    body = (
      <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-card">
        <div className="relative overflow-x-auto">
          <table className="w-full" aria-label="Client workspaces" aria-busy="true">
            <thead className="border-b border-border bg-surface-subtle/70">
              <tr>
                <th className={HEADER_CLASS}>Client Name</th>
                <th className={HEADER_CLASS}>Registration</th>
                <th className={HEADER_CLASS}>SST</th>
                <th className={HEADER_CLASS}>Industry</th>
                <th className={`${HEADER_CLASS} text-right`}>Unreviewed</th>
                <th className={`${HEADER_CLASS} text-right`}>Verified</th>
                <th className={HEADER_CLASS}>Action</th>
              </tr>
            </thead>
            <tbody>
              <SkeletonRow columns={7} />
            </tbody>
          </table>
        </div>
      </div>
    )
  } else if (clients.length === 0) {
    body = formOpen ? (
      <ClientForm
        onCancel={() => setFormOpen(false)}
        onCreated={() => setFormOpen(false)}
        submitLabel="Create client"
      />
    ) : (
      <div className="rounded-xl border border-border bg-surface p-6 shadow-card">
        <div className="mx-auto max-w-sm py-10 text-center">
          <p className="text-sm font-semibold text-text-primary">
            Add your first client
          </p>
          <p className="mt-1 text-sm text-text-secondary">
            Create a client workspace to start uploading receipts.
          </p>
          <button
            type="button"
            onClick={() => setFormOpen(true)}
            className={`${PRIMARY_BUTTON_CLASS} mx-auto mt-4`}
          >
            Add your first client
          </button>
        </div>
      </div>
    )
  } else {
    body = (
      <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-card">
        <div className="relative overflow-x-auto">
          <table className="w-full" aria-label="Client workspaces">
            <thead className="border-b border-border bg-surface-subtle/70">
              <tr>
                <th className={HEADER_CLASS}>Client Name</th>
                <th className={HEADER_CLASS}>Registration</th>
                <th className={HEADER_CLASS}>SST</th>
                <th className={HEADER_CLASS}>Industry</th>
                <th className={`${HEADER_CLASS} text-right`}>Unreviewed</th>
                <th className={`${HEADER_CLASS} text-right`}>Verified</th>
                <th className={HEADER_CLASS}>Action</th>
              </tr>
            </thead>
            <tbody>
              {summaries.map((client) => (
                <tr
                  key={client.id}
                  className="h-12 border-b border-border last:border-b-0 hover:bg-surface-subtle/60"
                >
                  <td className="px-3 py-2 text-sm font-semibold text-text-primary">
                    {client.business_name}
                  </td>
                  <td className={`${CELL_CLASS} font-mono-numbers`}>
                    {client.registration_number ?? COUNT_PLACEHOLDER}
                  </td>
                  <td className={`${CELL_CLASS} font-mono-numbers`}>
                    {client.sst_number ?? COUNT_PLACEHOLDER}
                  </td>
                  <td className={CELL_CLASS}>
                    {client.industry_category ?? COUNT_PLACEHOLDER}
                  </td>
                  <CountCell value={client.unreviewed_count} />
                  <CountCell value={client.verified_count} />
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={() => navigate(`/clients/${client.id}/inbox`)}
                      className={ACTION_BUTTON_CLASS}
                    >
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
            Clients
          </h1>
          <button
            type="button"
            onClick={() => setFormOpen(true)}
            className={PRIMARY_BUTTON_CLASS}
          >
            Add client
          </button>
        </div>

        {receiptsError !== null ? (
          <div
            role="alert"
            className="mb-4 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-mismatch-border bg-mismatch-bg px-4 py-3 text-sm text-mismatch-text shadow-card"
          >
            <span>{receiptsError}</span>
            <button
              type="button"
              onClick={() => void loadClients()}
              className="flex h-11 items-center px-2 text-sm font-semibold underline focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none"
            >
              Retry
            </button>
          </div>
        ) : null}

        {formOpen && clients.length > 0 ? (
          <div className="mb-4">
            <ClientForm
              onCancel={() => setFormOpen(false)}
              onCreated={() => setFormOpen(false)}
            />
          </div>
        ) : null}

        {body}
      </div>
    </AppShell>
  )
}
