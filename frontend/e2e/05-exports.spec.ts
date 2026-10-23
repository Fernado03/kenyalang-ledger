import { readFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import {
  apiHeaders,
  CLIENT_ID,
  FIXED_MONTH,
  RECEIPT,
  localMonth,
  seedSession,
} from './fixtures'

const EXPORTS = `/clients/${CLIENT_ID}/exports`

test.describe('Exports', () => {
  test.beforeEach(async ({ page }) => {
    await seedSession(page)
    await page.goto(EXPORTS)
    await expect(page.getByRole('heading', { level: 1, name: 'Exports' })).toBeVisible()
  })

  test('defaults to the current month and describes the dispatch surface', async ({ page }) => {
    await expect(page.getByLabel('Accounting billing period')).toHaveValue(
      localMonth(),
    )
    await expect(page.getByRole('button', { name: 'All time' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
    await expect(page.getByText('Exporting all verified receipts across all billing dates')).toHaveCount(0)
    await expect(page.getByRole('heading', { level: 2, name: 'Accounting batch CSV' })).toBeVisible()
    await expect(page.getByRole('heading', { level: 2, name: 'LHDN MyInvois multi-line JSON' })).toBeVisible()
  })

  test('defaults to the same month the dashboard resolves', async ({ page }) => {
    // The two surfaces must agree on "the month this workspace is about";
    // otherwise exports silently batches a different period than the figures
    // the user just reviewed.
    const response = await page.request.get(
      `/api/v1/clients/${CLIENT_ID}/dashboard/summary`,
      { headers: apiHeaders },
    )
    const summary = (await response.json()) as { month: string }

    await expect(page.getByLabel('Accounting billing period')).toHaveValue(summary.month)
  })

  test('an explicit month choice wins over the default', async ({ page }) => {
    await page.getByLabel('Accounting billing period').fill('2026-01')

    await expect(page.getByText('Filtering verified receipts for 2026-01')).toBeVisible()
    await expect(page.getByLabel('Accounting billing period')).toHaveValue('2026-01')
  })

  test('month selection filters the dispatch line and "All time" clears it', async ({ page }) => {
    await page.getByLabel('Accounting billing period').fill(FIXED_MONTH)
    await expect(page.getByText(/Filtering verified receipts for/)).toBeVisible()

    await page.getByRole('button', { name: 'All time' }).click()
    await expect(page.getByLabel('Accounting billing period')).toHaveValue('')
    await expect(page.getByRole('button', { name: 'All time' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await expect(
      page.getByText('Exporting all verified receipts across all billing dates'),
    ).toBeVisible()
  })

  test('downloads the accounting CSV and MyInvois JSON for the selected month', async ({ page }) => {
    await page.getByLabel('Accounting billing period').fill(FIXED_MONTH)

    const [csv] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: /Download accounting CSV/ }).click(),
    ])
    expect(csv.suggestedFilename()).toBe('Kenyalang_PurJournal_202603.csv')
    await expect(page.getByText('Accounting CSV downloaded successfully.')).toBeVisible()

    const [json] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: /Download MyInvois JSON/ }).click(),
    ])
    expect(json.suggestedFilename()).toBe('Kenyalang_MyInvois_202603.json')
    await expect(page.getByText('LHDN MyInvois JSON downloaded successfully.')).toBeVisible()

    const path = await csv.path()
    expect(path).not.toBeNull()
    const text = path === null ? '' : await readFile(path, 'utf8')
    // Every field is quoted (H3): a bare-quoted writer let a value beginning with
    // "\r" hide a spreadsheet formula behind the quote.
    expect(text.split('\n')[0]).toBe(
      '"DocDate","DocNo","SupplierCode","SupplierName","Description","ItemCode","Qty",' +
        '"UnitPrice","TaxCode","TaxAmount","TotalAmount"',
    )
    // March holds the frozen exported row plus the markable verified row.
    expect(text).toContain('INV-E2E-008')
    expect(text).toContain('INV-E2E-007')
  })

  test('download both emits two files and one success message', async ({ page }) => {
    await page.getByLabel('Accounting billing period').fill(FIXED_MONTH)

    const downloads: string[] = []
    page.on('download', (download) => downloads.push(download.suggestedFilename()))

    await page.getByRole('button', { name: 'Download both' }).click()
    await expect(
      page.getByText('Both accounting CSV and LHDN MyInvois JSON downloaded successfully.'),
    ).toBeVisible()
    expect(downloads).toEqual([
      'Kenyalang_PurJournal_202603.csv',
      'Kenyalang_MyInvois_202603.json',
    ])
  })

  test('confirms the irreversible mark once, then freezes the receipts', async ({ page }) => {
    await page.getByLabel('Accounting billing period').fill(FIXED_MONTH)

    await page.getByRole('button', { name: 'Mark exported', exact: true }).click()
    const confirmation = page.getByRole('group', { name: /Mark these receipts as exported/ })
    await expect(confirmation).toContainText('This cannot be undone')
    await expect(confirmation).toContainText('the selected month (2026-03)')
    await expect(page.getByText('Marked 1 receipt as exported.')).toHaveCount(0)

    // Escape cancels without touching the server.
    await page.keyboard.press('Escape')
    await expect(confirmation).toHaveCount(0)
    await expect(page.getByText('Marked 1 receipt as exported.')).toHaveCount(0)

    await page.getByRole('button', { name: 'Mark exported', exact: true }).click()
    await page.getByRole('button', { name: 'Confirm mark exported' }).click()
    await expect(page.getByText('Marked 1 receipt as exported.')).toBeVisible()

    // Repeat call is a documented no-op, still behind the same confirmation.
    await page.getByRole('button', { name: 'Mark exported', exact: true }).click()
    await page.getByRole('button', { name: 'Confirm mark exported' }).click()
    await expect(page.getByText('No verified receipts to mark as exported.')).toBeVisible()

    // The mutation landed: the frozen fixture joins it in the exported set.
    await page.goto(`/clients/${CLIENT_ID}/inbox`)
    await page
      .getByRole('group', { name: 'Status filter' })
      .getByRole('button', { name: 'Exported' })
      .click()
    await expect(page.getByText(/receipts 1–3 of 3/)).toBeVisible()

    // Exported rows open read-only: the console refuses the mutation up front.
    await page.goto(`/clients/${CLIENT_ID}/review/${RECEIPT.mark}`)
    await expect(page.getByLabel('Supplier Name')).toBeDisabled()
    await expect(page.getByRole('button', { name: /Verify & Next/ })).toBeDisabled()
    await expect(
      page.getByText(/already been exported, so it can no longer be edited/),
    ).toBeVisible()
  })
})