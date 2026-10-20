import type { ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useSessionStore } from '../store/sessionStore'

/**
 * Dense console chrome (docs/04 §4.1): hairline borders, soft card radius,
 * 56px sticky top bar, single teal accent. Used by every console page.
 */
function navLinkClass({ isActive }: { isActive: boolean }) {
  return `inline-flex h-10 items-center rounded-lg px-3 text-sm whitespace-nowrap transition-colors duration-100 ease-out focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none ${
    isActive
      ? 'bg-brand-50 font-medium text-brand-900'
      : 'text-text-secondary hover:bg-surface-subtle hover:text-text-primary'
  }`
}

export default function AppShell({
  children,
  clientId,
}: {
  children: ReactNode
  clientId?: string
}) {
  const accountantId = useSessionStore((state) => state.accountantId)
  const clearAccountantId = useSessionStore((state) => state.clearAccountantId)
  const { pathname } = useLocation()
  const reviewActive = pathname.includes('/review/')

  return (
    <div className="min-h-screen bg-canvas text-text-primary">
      <header className="relative top-0 z-40 border-b border-border bg-surface sm:sticky">
        <div className="mx-auto flex min-h-14 max-w-6xl flex-wrap items-center gap-x-5 gap-y-1 px-6 py-2 sm:flex-nowrap sm:py-0">
          <span className="flex shrink-0 items-center gap-2 whitespace-nowrap">
            <span aria-hidden="true" className="h-5 w-5 rounded-md bg-brand-900" />
            <span className="text-[15px] font-semibold tracking-tight">
              Kenyalang Ledger
            </span>
          </span>

          <nav className="flex flex-wrap items-center gap-1" aria-label="Console">
            <NavLink to="/clients" end className={navLinkClass}>
              Clients
            </NavLink>
            {clientId !== undefined ? (
              <>
                <NavLink
                  to={`/clients/${clientId}/inbox`}
                  className={({ isActive }) =>
                    navLinkClass({ isActive: isActive || reviewActive })
                  }
                >
                  Inbox
                </NavLink>
                <NavLink to={`/clients/${clientId}/dashboard`} className={navLinkClass}>
                  Dashboard
                </NavLink>
                <NavLink to={`/clients/${clientId}/exports`} className={navLinkClass}>
                  Exports
                </NavLink>
                <NavLink to="/upload" className={navLinkClass}>
                  Upload
                </NavLink>
              </>
            ) : null}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <span className="hidden font-mono-numbers text-xs text-text-muted sm:inline">
              {accountantId !== null ? accountantId.slice(0, 8) : ''}
            </span>
            <button
              type="button"
              onClick={clearAccountantId}
              className="inline-flex h-9 items-center rounded-lg border border-border bg-surface px-3 text-sm text-text-secondary transition-colors duration-100 ease-out hover:bg-surface-subtle hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      {children}
    </div>
  )
}
