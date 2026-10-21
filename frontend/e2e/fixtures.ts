import { type Page } from '@playwright/test'

/** Mirrors backend/seed_e2e.py; the fixture DB is reseeded on every run. */
export const ACCOUNTANT_ID = 'a0000000-0000-4000-8000-000000000001'
export const OTHER_ACCOUNTANT_ID = 'b0b0b0b0-2222-4333-8444-555555555555'
export const CLIENT_ID = 'c1000000-0000-4000-8000-000000000001'
export const EMPTY_CLIENT_ID = 'c1000000-0000-4000-8000-000000000002'

export const CLIENT_NAME = 'E2E Hardware & Supply'
export const EMPTY_CLIENT_NAME = 'E2E Second Client'

const receipt = (suffix: string): string => `e2e00000-0000-4000-8000-0000000000${suffix}`

export const RECEIPT = {
  math: receipt('01'),
  clean: receipt('02'),
  verified: receipt('03'),
  exported: receipt('04'),
  rejected: receipt('05'),
  unreadable: receipt('06'),
  processing: receipt('07'),
  save: receipt('08'),
  reject: receipt('09'),
  mark: receipt('10'),
  frozen: receipt('11'),
} as const

/** The app's default month: local `getFullYear`/`getMonth`, never UTC. */
export function localMonth(now: Date = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

/** Fixed billing month used by the export + dashboard specs. */
export const FIXED_MONTH = '2026-03'

/**
 * Session + workspace live in localStorage and are read at module scope, so
 * they must exist before the app boots. Called per page before `goto`.
 */
export async function seedSession(
  page: Page,
  options: { accountantId?: string; clientId?: string | null } = {},
): Promise<void> {
  const accountantId = options.accountantId ?? ACCOUNTANT_ID
  const clientId = options.clientId === undefined ? CLIENT_ID : options.clientId
  await page.addInitScript(
    ([accountant, client]) => {
      window.localStorage.setItem('kenyalang.accountant_id', accountant as string)
      if (client === null) window.localStorage.removeItem('kenyalang.current_client_id')
      else window.localStorage.setItem('kenyalang.current_client_id', client as string)
    },
    [accountantId, clientId] as [string, string | null],
  )
}

/** Same-origin API helper for asserting UI against server truth. */
export const apiHeaders = { 'X-Accountant-Id': ACCOUNTANT_ID }

/** Guarded read of the receipt detail payload used for server-truth assertions. */
export async function receiptState(
  page: Page,
  receiptId: string,
): Promise<{ status: string; merchant_name: string | null }> {
  const response = await page.request.get(
    `/api/v1/clients/${CLIENT_ID}/receipts/${receiptId}`,
    { headers: apiHeaders },
  )
  const body: unknown = await response.json()
  if (typeof body !== 'object' || body === null) {
    throw new Error('unexpected receipt detail payload')
  }
  const record = body as Record<string, unknown>
  return {
    status: String(record.status),
    merchant_name: typeof record.merchant_name === 'string' ? record.merchant_name : null,
  }
}

/** Guarded read of the audit-log row count for one receipt. */
export async function auditCount(page: Page, receiptId: string): Promise<number> {
  const response = await page.request.get(
    `/api/v1/clients/${CLIENT_ID}/receipts/${receiptId}/audit`,
    { headers: apiHeaders },
  )
  const body: unknown = await response.json()
  if (typeof body !== 'object' || body === null || !('items' in body) || !Array.isArray(body.items)) {
    throw new Error('unexpected audit payload')
  }
  return body.items.length
}

/** Guarded read of `/api/clients` business names. */
export async function clientNames(page: Page): Promise<string[]> {
  const response = await page.request.get('/api/clients', { headers: apiHeaders })
  const body: unknown = await response.json()
  if (typeof body !== 'object' || body === null || !('items' in body) || !Array.isArray(body.items)) {
    throw new Error('unexpected client list payload')
  }
  return body.items.map((item: unknown) =>
    typeof item === 'object' && item !== null && 'business_name' in item
      ? String(item.business_name)
      : '',
  )
}
