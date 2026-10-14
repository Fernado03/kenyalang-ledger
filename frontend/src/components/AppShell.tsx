import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useSessionStore } from '../store/sessionStore'

/**
 * Dense console chrome (docs/04 §4.1): razor-sharp borders, 44px top bar,
 * single teal accent. Opt-in per page — App.tsx does not wrap routes in it.
 */
export default function AppShell({
  children,
  clientId,
}: {
  children: ReactNode
  clientId?: string
}) {
  const accountantId = useSessionStore((state) => state.accountantId)
  const clearAccountantId = useSessionStore((state) => state.clearAccountantId)

  return (
    <div className="min-h-screen bg-canvas text-text-primary">
      <header className="flex h-11 items-center gap-4 border-b border-border bg-surface px-4">
        <span className="flex items-center gap-2">
          <span aria-hidden="true" className="h-3 w-3 bg-brand-700" />
          <span className="text-sm font-semibold tracking-tight text-text-primary">
            Kenyalang Ledger
          </span>
        </span>

        <nav className="flex items-center gap-4" aria-label="Console">
          <NavLink
            to="/clients"
            className={({ isActive }) =>
              `text-sm text-text-secondary transition-colors duration-100 ease-out hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none ${
                isActive ? 'font-semibold text-brand-900' : ''
              }`
            }
          >
            Clients
          </NavLink>
          {clientId !== undefined ? (
            <>
              <NavLink
                to={`/clients/${clientId}/inbox`}
                className={({ isActive }) =>
                  `text-sm text-text-secondary transition-colors duration-100 ease-out hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none ${
                    isActive ? 'font-semibold text-brand-900' : ''
                  }`
                }
              >
                Inbox
              </NavLink>
              <NavLink
                to={`/clients/${clientId}/exports`}
                className={({ isActive }) =>
                  `text-sm text-text-secondary transition-colors duration-100 ease-out hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none ${
                    isActive ? 'font-semibold text-brand-900' : ''
                  }`
                }
              >
                Exports
              </NavLink>
            </>
          ) : null}
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <span className="font-mono-numbers text-xs text-text-muted">
            {accountantId !== null ? accountantId.slice(0, 8) : ''}
          </span>
          <button
            type="button"
            onClick={clearAccountantId}
            className="flex h-11 items-center text-sm text-text-secondary transition-colors duration-100 ease-out hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none"
          >
            Sign out
          </button>
        </div>
      </header>
      {children}
    </div>
  )
}
