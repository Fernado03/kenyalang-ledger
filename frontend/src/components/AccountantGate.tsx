import { useState, type FormEvent, type ReactNode } from 'react'
import { useSessionStore } from '../store/sessionStore'
import { BrandMark } from './Icon'

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
    <div className="min-h-screen bg-canvas lg:grid lg:grid-cols-12">
      <aside className="on-dark bg-brand-950 px-5 py-4 text-brand-50 lg:col-span-5 lg:flex lg:min-h-screen lg:flex-col lg:justify-between lg:px-10 lg:py-12">
        <div className="flex items-center gap-3">
          <BrandMark size={30} />
          <h1 className="font-serif text-title font-normal tracking-[-0.01em]">Kenyalang Ledger</h1>
        </div>

        <div className="mt-6 hidden lg:mt-0 lg:block">
          <p className="max-w-xs font-serif text-display font-normal leading-tight tracking-[-0.015em]">
            Every request carries an accountant id.
          </p>
          <p className="mt-6 font-mono text-micro uppercase tracking-[0.14em] text-brand-100">
            Route guard · docs/03 §3.1
          </p>
        </div>
      </aside>

      <div className="flex items-center justify-center px-5 py-10 lg:col-span-7 lg:px-10 lg:py-12">
        <form onSubmit={handleSubmit} className="w-full max-w-md">
          <p className="eyebrow">Session</p>
          <h2 className="section-title mt-2">Open the console</h2>
          <p className="mt-2 text-body text-text-secondary">
            Enter the accountant session id to open the console.
          </p>

          <div className="mt-6">
            <label htmlFor="accountant-id" className="field-label">
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
              className="field-input"
              placeholder="e.g. 7f3a1c92-..."
            />
            {error !== null && (
              <p id="accountant-id-error" role="alert" className="field-error">
                {error}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={draft.trim() === ''}
            className="btn btn-primary mt-5 w-full"
          >
            Continue
          </button>

          <p className="mt-4 font-mono text-micro leading-relaxed text-text-muted">
            This value is sent as the <code>X-Accountant-Id</code> header on every
            request. It is a forgeable demo identity, not authentication.
          </p>
        </form>
      </div>
    </div>
  )
}
