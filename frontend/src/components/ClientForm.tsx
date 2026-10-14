import { useState, type FormEvent } from 'react'
import { useReceiptStore } from '../store/receiptStore'
import type { Client } from '../types/client'

const INPUT_CLASS =
  'h-11 w-full border border-border bg-surface px-3 text-sm text-text-primary transition-colors duration-100 ease-out placeholder:text-text-muted focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none'

const LABEL_CLASS = 'block text-xs font-medium text-text-secondary'

const BUTTON_CLASS =
  'flex h-11 items-center justify-center border border-border px-4 text-sm font-semibold transition-colors duration-100 ease-out focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none'

/**
 * Create-workspace form (SCR-01 empty + header action, docs/04 §4.4 validation
 * placement). Business name is the only required field; the rest are optional.
 */
export default function ClientForm({
  onCancel,
  onCreated,
  submitLabel = 'Add client',
}: {
  onCancel: () => void
  onCreated: (client: Client) => void
  submitLabel?: string
}) {
  const createClient = useReceiptStore((state) => state.createClient)
  const [businessName, setBusinessName] = useState('')
  const [registrationNumber, setRegistrationNumber] = useState('')
  const [sstNumber, setSstNumber] = useState('')
  const [industryCategory, setIndustryCategory] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    // Blank optional fields go on the wire as null (ClientCreate contract).
    const registration = registrationNumber.trim()
    const sst = sstNumber.trim()
    const industry = industryCategory.trim()
    if (businessName.trim() === '') {
      setError('Business name is required.')
      return
    }
    setError(null)
    setSaving(true)
    try {
      const created = await createClient({
        business_name: businessName.trim(),
        registration_number: registration === '' ? null : registration,
        sst_number: sst === '' ? null : sst,
        industry_category: industry === '' ? null : industry,
      })
      onCreated(created)
    } catch (cause) {
      setError(
        cause instanceof Error && cause.message !== ''
          ? cause.message
          : 'Could not create the client.',
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="border border-border bg-surface p-6"
    >
      <h2 className="text-base font-semibold tracking-tight text-text-primary">
        New client
      </h2>

      <div className="mt-4">
        <label htmlFor="business_name" className={LABEL_CLASS}>
          Business name
        </label>
        <input
          id="business_name"
          name="business_name"
          required
          value={businessName}
          onChange={(event) => setBusinessName(event.target.value)}
          aria-invalid={error !== null}
          aria-describedby={error !== null ? 'error-business_name' : undefined}
          className={INPUT_CLASS}
          placeholder="Ah Teck Hardware Sdn Bhd"
        />
        {error !== null ? (
          <p id="error-business_name" className="mt-1 text-xs text-mismatch-text">
            {error}
          </p>
        ) : null}
      </div>

      <div className="mt-4">
        <label htmlFor="registration_number" className={LABEL_CLASS}>
          Registration number
        </label>
        <input
          id="registration_number"
          name="registration_number"
          value={registrationNumber}
          onChange={(event) => setRegistrationNumber(event.target.value)}
          className={INPUT_CLASS}
          placeholder="002938192-K"
        />
      </div>

      <div className="mt-4">
        <label htmlFor="sst_number" className={LABEL_CLASS}>
          SST number
        </label>
        <input
          id="sst_number"
          name="sst_number"
          value={sstNumber}
          onChange={(event) => setSstNumber(event.target.value)}
          className={INPUT_CLASS}
          placeholder="W10-1808-31000052"
        />
      </div>

      <div className="mt-4">
        <label htmlFor="industry_category" className={LABEL_CLASS}>
          Industry category
        </label>
        <input
          id="industry_category"
          name="industry_category"
          value={industryCategory}
          onChange={(event) => setIndustryCategory(event.target.value)}
          className={INPUT_CLASS}
          placeholder="Hardware & Building Materials"
        />
      </div>

      <div className="mt-6 flex items-center gap-3">
        <button
          type="submit"
          disabled={saving}
          className={`${BUTTON_CLASS} border-brand-900 bg-brand-900 text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-text-muted`}
        >
          {saving ? 'Saving…' : submitLabel}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className={`${BUTTON_CLASS} bg-surface text-text-secondary hover:bg-surface-subtle`}
        >
          Cancel
        </button>
      </div>
    </form>
  )
}
