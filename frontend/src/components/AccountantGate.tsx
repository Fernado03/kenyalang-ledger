import { useState, type FormEvent, type ReactNode } from 'react'
import { useSessionStore } from '../store/sessionStore'

/**
 * Session gate: the console is unusable until an accountant id is present,
 * because every API call carries `X-Accountant-Id` (docs/03 §3.1 route guard).
 */
export default function AccountantGate({ children }: { children: ReactNode }) {
  const accountantId = useSessionStore((state) => state.accountantId)
  const setAccountantId = useSessionStore((state) => state.setAccountantId)
  const [draft, setDraft] = useState('')

  if (accountantId !== null) {
    return <>{children}</>
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setAccountantId(draft.trim())
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas p-6">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm border border-border bg-surface p-6"
      >
        <h1 className="text-base font-semibold tracking-tight text-text-primary">
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
          onChange={(event) => setDraft(event.target.value)}
          autoComplete="off"
          className="mt-1 h-11 w-full border border-border bg-surface px-3 text-sm text-text-primary transition-colors duration-100 ease-out placeholder:text-text-muted focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none"
          placeholder="e.g. 7f3a1c92-..."
        />
        <button
          type="submit"
          disabled={draft.trim() === ''}
          className="mt-4 flex h-11 w-full items-center justify-center border border-border bg-brand-900 text-sm font-semibold text-white transition-colors duration-100 ease-out hover:bg-brand-700 focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-text-muted"
        >
          Continue
        </button>
        <p className="mt-3 text-xs text-text-muted">
          This value is sent as the <code>X-Accountant-Id</code> header on every
          request. The backend owns validation.
        </p>
      </form>
    </div>
  )
}
