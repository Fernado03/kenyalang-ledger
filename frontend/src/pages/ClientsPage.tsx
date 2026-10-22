import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ClientSummary } from '../api/client'
import AppShell from '../components/AppShell'
import ClientForm from '../components/ClientForm'
import { Icon } from '../components/Icon'
import PageHeader, { PageMeta } from '../components/PageHeader'
import { useReceiptStore } from '../store/receiptStore'

const COUNT_PLACEHOLDER = '-'

/** Renders a receipt count, falling back for freshly created clients. */
function CountCell({ value }: { value: number | undefined }) {
  return (
    <td className="py-1.5 text-right font-mono-numbers text-ui text-text-primary">
      {value ?? 0}
    </td>
  )
}

/** One shimmering placeholder row for the loading state. */
function SkeletonRow() {
  return (
    <tr className="h-[52px]">
      {Array.from({ length: 6 }, (_unused, index) => (
        <td className="px-3 py-2" key={index}>
          <span className="skeleton block h-3.5 w-full" />
        </td>
      ))}
    </tr>
  )
}

/**
 * SCR-01 Client Workspace Switcher (docs/03 §3.3): dense client ledger plus the
 * inline create form. All 5 UX states are explicit.
 */
export default function ClientsPage() {
  const clients = useReceiptStore((state) => state.clients)
  const loadClients = useReceiptStore((state) => state.loadClients)
  const currentClientId = useReceiptStore((state) => state.currentClientId)
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

  const formPanel = (
    <div className="border-t-2 border-brand-900 bg-surface px-5 py-5">
      <ClientForm
        onCancel={() => setFormOpen(false)}
        onCreated={() => setFormOpen(false)}
        submitLabel={summaries.length === 0 ? 'Create client' : undefined}
      />
    </div>
  )

  let body: ReactNode

  if (loading) {
    body = (
      <>
        <div className="hidden md:block">
          <table className="data-table" aria-label="Client workspaces" aria-busy="true">
            <thead>
              <tr>
                <th>Client name</th>
                <th>Registration</th>
                <th>SST</th>
                <th className="text-right">Unreviewed</th>
                <th className="text-right">Verified</th>
                <th className="text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
            </tbody>
          </table>
        </div>
        <div className="md:hidden" aria-busy="true">
          {[0, 1, 2].map((index) => (
            <div className="border-b border-border py-4" key={index}>
              <span className="skeleton block h-4 w-1/2" />
              <span className="skeleton mt-2 block h-3 w-2/3" />
              <span className="skeleton mt-3 block h-9 w-full" />
            </div>
          ))}
        </div>
      </>
    )
  } else if (clients.length === 0) {
    // A failed fetch must not read as an empty account: no create invitation.
    // A form the user already opened stays, so typed input is not discarded.
    body = formOpen ? (
      formPanel
    ) : receiptsError !== null ? null : (
      <div className="border-t-2 border-brand-900 py-10">
        <h2 className="section-title">Add your first client</h2>
        <p className="mt-2 max-w-md text-body text-text-secondary">
          Create a client workspace to start uploading receipts.
        </p>
        <button
          type="button"
          onClick={() => setFormOpen(true)}
          className="btn btn-primary mt-5"
        >
          <Icon name="plus" size={16} />
          Add your first client
        </button>
      </div>
    )
  } else {
    body = (
      <>
        <div className="hidden md:block">
          <table className="data-table" aria-label="Client workspaces">
            <thead>
              <tr>
                <th>Client name</th>
                <th>Registration</th>
                <th>SST</th>
                <th className="text-right">Unreviewed</th>
                <th className="text-right">Verified</th>
                <th className="text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {summaries.map((client) => (
                <tr key={client.id} className="h-[52px]">
                  <td className="py-1.5">
                    <p className="text-body font-semibold text-text-primary">
                      {client.business_name}
                    </p>
                    <p className="text-label text-text-muted">
                      {client.industry_category ?? COUNT_PLACEHOLDER}
                    </p>
                  </td>
                  <td className="whitespace-nowrap py-1.5 font-mono text-label text-text-secondary">
                    {client.registration_number ?? COUNT_PLACEHOLDER}
                  </td>
                  <td className="whitespace-nowrap py-1.5 font-mono text-label text-text-secondary">
                    {client.sst_number ?? COUNT_PLACEHOLDER}
                  </td>
                  <CountCell value={client.unreviewed_count} />
                  <CountCell value={client.verified_count} />
                  <td className="py-0 pl-3 pr-0 text-right">
                    <button
                      type="button"
                      onClick={() => navigate(`/clients/${client.id}/inbox`)}
                      className="link-quiet h-11 justify-end px-2"
                    >
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <ul className="divide-y divide-border md:hidden" aria-label="Client workspaces">
          {summaries.map((client) => (
            <li key={client.id} className="py-4">
              <p className="text-body font-semibold text-text-primary">
                {client.business_name}
              </p>
              <p className="mt-0.5 text-label text-text-muted">
                {client.industry_category ?? COUNT_PLACEHOLDER}
              </p>
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2">
                <div>
                  <dt className="section-label">Registration</dt>
                  <dd className="font-mono text-label text-text-secondary">
                    {client.registration_number ?? COUNT_PLACEHOLDER}
                  </dd>
                </div>
                <div>
                  <dt className="section-label">SST</dt>
                  <dd className="font-mono text-label text-text-secondary">
                    {client.sst_number ?? COUNT_PLACEHOLDER}
                  </dd>
                </div>
                <div>
                  <dt className="section-label">Unreviewed</dt>
                  <dd className="font-mono-numbers text-ui text-text-primary">
                    {client.unreviewed_count ?? 0}
                  </dd>
                </div>
                <div>
                  <dt className="section-label">Verified</dt>
                  <dd className="font-mono-numbers text-ui text-text-primary">
                    {client.verified_count ?? 0}
                  </dd>
                </div>
              </dl>
              <button
                type="button"
                onClick={() => navigate(`/clients/${client.id}/inbox`)}
                className="btn btn-secondary mt-4 w-full"
              >
                Open
              </button>
            </li>
          ))}
        </ul>
      </>
    )
  }

  const workspaceLabel = `${summaries.length} ${
    summaries.length === 1 ? 'client workspace' : 'client workspaces'
  }`

  return (
    <AppShell clientId={currentClientId ?? undefined}>
      <div className="page-shell">
        <PageHeader
          eyebrow="Workspaces"
          title="Clients"
          meta={
            <PageMeta
              note={
                loading
                  ? 'Loading client workspaces.'
                  : summaries.length === 0
                    ? 'No client workspaces yet.'
                    : workspaceLabel
              }
            />
          }
          actions={
            formOpen ? (
              <button
                type="button"
                onClick={() => setFormOpen(false)}
                className="btn btn-ghost"
              >
                <Icon name="close" size={16} />
                Close
              </button>
            ) : clients.length > 0 ? (
              <button
                type="button"
                onClick={() => setFormOpen(true)}
                className="btn btn-primary"
              >
                <Icon name="plus" size={16} />
                Add client
              </button>
            ) : undefined
          }
        />

        {receiptsError !== null ? (
          <div
            role="alert"
            className="mt-6 flex flex-wrap items-center justify-between gap-4 border-l-2 border-mismatch-border bg-mismatch-bg px-4 py-3 text-ui text-mismatch-text"
          >
            <span>{receiptsError}</span>
            <button
              type="button"
              onClick={() => void loadClients()}
              className="btn btn-secondary"
            >
              Retry
            </button>
          </div>
        ) : null}

        {formOpen && clients.length > 0 ? <div className="mt-6">{formPanel}</div> : null}

        <div className="mt-6">{body}</div>
      </div>
    </AppShell>
  )
}
