import { useState, type FormEvent } from 'react'
import { useReceiptStore } from '../store/receiptStore'
import type { Client } from '../types/client'

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
      className="border-t-2 border-brand-900 bg-surface p-5 sm:p-6"
    >
      <h2 className="section-title">New client</h2>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label htmlFor="business_name" className="field-label">
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
            className="field-input"
            placeholder="Ah Teck Hardware Sdn Bhd"
          />
          {error !== null ? (
            <p id="error-business_name" className="field-error">
              {error}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="registration_number" className="field-label">
            Registration number
          </label>
          <input
            id="registration_number"
            name="registration_number"
            value={registrationNumber}
            onChange={(event) => setRegistrationNumber(event.target.value)}
            className="field-input"
            placeholder="002938192-K"
          />
        </div>

        <div>
          <label htmlFor="sst_number" className="field-label">
            SST number
          </label>
          <input
            id="sst_number"
            name="sst_number"
            value={sstNumber}
            onChange={(event) => setSstNumber(event.target.value)}
            className="field-input"
            placeholder="W10-1808-31000052"
          />
        </div>

        <div>
          <label htmlFor="industry_category" className="field-label">
            Industry category
          </label>
          <input
            id="industry_category"
            name="industry_category"
            value={industryCategory}
            onChange={(event) => setIndustryCategory(event.target.value)}
            className="field-input"
            placeholder="Hardware & Building Materials"
          />
        </div>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-2">
        <button type="submit" disabled={saving} className="btn btn-primary">
          {saving ? 'Saving…' : submitLabel}
        </button>
        <button type="button" onClick={onCancel} className="btn btn-ghost">
          Cancel
        </button>
      </div>
    </form>
  )
}
