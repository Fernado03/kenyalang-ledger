import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Icon, type IconName, BrandMark } from './Icon'
import { useSessionStore } from '../store/sessionStore'
import { useReceiptStore } from '../store/receiptStore'

interface NavItem {
  label: string
  to: string
  icon: IconName
  end?: boolean
  activeOnReview?: boolean
  disabled?: boolean
}

const railItemClass = (active: boolean) =>
  `flex h-14 w-full flex-col items-center justify-center gap-1 text-micro font-medium transition-colors duration-100 ${
    active
      ? 'bg-surface font-semibold text-text-primary'
      : 'text-text-muted hover:bg-surface hover:text-text-primary'
  }`

const tabItemClass = (active: boolean) =>
  `relative flex min-h-14 flex-1 flex-col items-center justify-center gap-1 px-1 text-micro font-medium transition-colors duration-100 ${
    active ? 'font-semibold text-brand-900' : 'text-text-muted'
  }`

const disabledClass = 'pointer-events-none opacity-35'

function NavGlyph({ item }: { item: NavItem }) {
  return (
    <>
      <Icon name={item.icon} size={20} />
      <span>{item.label}</span>
    </>
  )
}

/**
 * Console chrome: a compact rail on desktop, a persistent bottom tab bar on
 * mobile. Navigation never depends on the page rendering its own links.
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
  const resetWorkspace = useReceiptStore((state) => state.resetWorkspace)
  // The persisted workspace id belongs to the signed-in accountant; leaving it
  // behind lets the next one land in a tenant they do not own.
  const signOut = (): void => {
    resetWorkspace()
    clearAccountantId()
  }
  const { pathname } = useLocation()
  const reviewActive = pathname.includes('/review/')
  const hasWorkspace = clientId !== undefined

  const items: NavItem[] = [
    { label: 'Clients', to: '/clients', icon: 'clients', end: true },
    {
      label: 'Inbox',
      to: hasWorkspace ? `/clients/${clientId}/inbox` : '/clients',
      icon: 'inbox',
      activeOnReview: true,
      disabled: !hasWorkspace,
    },
    {
      label: 'Dashboard',
      to: hasWorkspace ? `/clients/${clientId}/dashboard` : '/clients',
      icon: 'dashboard',
      disabled: !hasWorkspace,
    },
    {
      label: 'Exports',
      to: hasWorkspace ? `/clients/${clientId}/exports` : '/clients',
      icon: 'exports',
      disabled: !hasWorkspace,
    },
    { label: 'Upload', to: '/upload', icon: 'camera' },
  ]

  const isItemActive = (item: NavItem): boolean => {
    if (item.activeOnReview === true && reviewActive) return true;
    return item.end === true
      ? pathname === item.to
      : pathname === item.to || pathname.startsWith(`${item.to}/`);
  };

  return (
    <div className="min-h-dvh bg-canvas text-text-primary">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[72px] flex-col border-r border-border bg-surface-subtle lg:flex">
        <Link
          to="/clients"
          className="flex h-16 shrink-0 items-center justify-center border-b border-border"
          aria-label="Kenyalang Ledger — clients"
        >
          <BrandMark size={30} />
        </Link>

        <nav className="flex flex-1 flex-col gap-0.5 py-2" aria-label="Primary">
          {items.map((item) =>
            item.disabled ? (
              <span
                key={item.label}
                className={`${railItemClass(false)} ${disabledClass}`}
                aria-disabled="true"
                title="Select a workspace first"
              >
                <Icon name={item.icon} size={20} />
                <span>{item.label}</span>
              </span>
            ) : (
              <Link
                key={item.label}
                to={item.to}
                title={item.label}
                aria-current={isItemActive(item) ? 'page' : undefined}
                className={railItemClass(isItemActive(item))}
              >
                <NavGlyph item={item} />
              </Link>
            ),
          )}
        </nav>

        <div className="flex flex-col items-center gap-1 border-t border-border py-2">
          <span
            className="flex h-8 w-8 items-center justify-center border border-border bg-surface font-mono text-micro uppercase text-text-secondary"
            title={accountantId ?? 'Accountant'}
          >
            {accountantId !== null ? accountantId.slice(0, 2).toUpperCase() : '—'}
          </span>
          <button
            type="button"
            onClick={signOut}
            className="flex h-10 w-10 items-center justify-center text-text-muted transition-colors duration-100 hover:bg-surface hover:text-text-primary"
            aria-label="Sign out"
            title="Sign out"
          >
            <Icon name="sign-out" size={18} />
          </button>
        </div>
      </aside>

      <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-border bg-surface px-4 lg:hidden">
        <Link to="/clients" className="flex min-w-0 items-center gap-2" aria-label="Kenyalang Ledger — clients">
          <BrandMark size={26} />
          <span className="truncate font-serif text-[17px] font-semibold tracking-[-0.01em]">
            Kenyalang <span className="text-text-muted">Ledger</span>
          </span>
        </Link>
        <button
          type="button"
          onClick={signOut}
          className="ml-auto flex h-10 w-10 shrink-0 items-center justify-center text-text-muted transition-colors duration-100 hover:bg-surface-subtle hover:text-text-primary"
          aria-label="Sign out"
          title="Sign out"
        >
          <Icon name="sign-out" size={18} />
        </button>
      </header>

      <div className="pb-[calc(3.5rem+env(safe-area-inset-bottom))] lg:pl-[72px] lg:pb-0">
        {children}
      </div>

      <nav
        className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden"
        aria-label="Primary"
      >
        <div className="flex">
          {items.map((item) =>
            item.disabled ? (
              <span
                key={item.label}
                className={`${tabItemClass(false)} ${disabledClass}`}
                aria-disabled="true"
                title="Select a workspace first"
              >
                <Icon name={item.icon} size={20} />
                <span>{item.label}</span>
              </span>
            ) : (
              <Link
                key={item.label}
                to={item.to}
                aria-current={isItemActive(item) ? 'page' : undefined}
                className={tabItemClass(isItemActive(item))}
              >
                <NavGlyph item={item} />
              </Link>
            ),
          )}
        </div>
      </nav>
    </div>
  )
}
