import { useState, type FormEvent, type ReactNode } from 'react'
import { useSessionStore } from '../store/sessionStore'

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Session gate: the console is unusable until an accountant id is present,
 * because every API call carries `X-Accountant-Id` (docs/03 §3.1 route guard).
 * This is a forgeable demo identity, not authentication.
 */
export default function AccountantGate({ children }: { children: ReactNode }) {
  const accountantId = useSessionStore((state) => state.accountantId)
  const setAccountantId = useSessionStore((state) => state.setAccountantId)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)

  if (accountantId !== null) {
    return <>{children}</>
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const value = draft.trim()
    if (!UUID_RE.test(value)) {
      setError('Enter a valid UUID')
      return
    }
    setError(null)
    setAccountantId(value)
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas p-6">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-2xl border border-border bg-surface p-8 shadow-card"
      >
        <span aria-hidden="true" className="mb-4 inline-flex h-8 w-8 rounded-lg bg-brand-900" />
        <h1 className="text-xl font-semibold tracking-tight text-text-primary">
          Kenyalang Ledger
        </h1>
        <p className="mt-2 text-sm text-text-secondary">
          Enter the accountant session id to open the console.
        </p>
        <label
          htmlFor="accountant-id"
          className="mt-4 block text-xs font-medium text-text-secondary"
        >
          Accountant session id
        </label>
        <input
          id="accountant-id"
          name="accountant_id"
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value)
            setError(null)
          }}
          autoComplete="off"
          aria-invalid={error !== null}
          aria-describedby={error === null ? undefined : 'accountant-id-error'}
          className="mt-1 h-12 w-full border border-border bg-surface px-3 text-sm text-text-primary transition-colors duration-100 ease-out placeholder:text-text-muted focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none"
          placeholder="e.g. 7f3a1c92-..."
        />
        {error !== null && (
          <p id="accountant-id-error" role="alert" className="mt-1 text-xs text-mismatch-text">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={draft.trim() === ''}
          className="mt-4 flex h-12 w-full items-center justify-center rounded-lg border border-border bg-brand-900 text-sm font-semibold text-white shadow-sm transition-colors duration-100 ease-out hover:bg-brand-700 focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-text-muted"
        >
          Continue
        </button>
        <p className="mt-3 text-xs text-text-muted">
          This value is sent as the <code>X-Accountant-Id</code> header on every
          request. It is a forgeable demo identity, not authentication.
        </p>
      </form>
    </div>
  )
}
