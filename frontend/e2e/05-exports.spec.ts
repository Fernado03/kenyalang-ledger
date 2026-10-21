import { readFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { CLIENT_ID, FIXED_MONTH, RECEIPT, localMonth, seedSession } from './fixtures'

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
    expect(text.split('\n')[0]).toContain('DocDate,DocNo,SupplierCode')
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

  test('marks verified receipts as exported exactly once and freezes them afterwards', async ({
    page,
  }) => {
    await page.getByLabel('Accounting billing period').fill(FIXED_MONTH)

    await page.getByRole('button', { name: 'Mark exported' }).click()
    await expect(page.getByText('Marked 1 receipt as exported.')).toBeVisible()

    // Repeat call is a documented no-op.
    await page.getByRole('button', { name: 'Mark exported' }).click()
    await expect(page.getByText('No verified receipts to mark as exported.')).toBeVisible()

    // The mutation landed: the frozen fixture joins it in the exported set.
    await page.goto(`/clients/${CLIENT_ID}/inbox`)
    await page.getByRole('group', { name: 'Status filter' }).getByRole('button', { name: 'Exported' }).click()
    await expect(page.getByText(/receipts 1–3 of 3/)).toBeVisible()

    // Exported rows can no longer be reviewed into a different state.
    await page.goto(`/clients/${CLIENT_ID}/review/${RECEIPT.mark}`)
    await expect(page.getByLabel('Supplier Name')).toBeVisible()
    await page.getByLabel('Supplier Name').fill('Mutation after export')
    await page.getByRole('button', { name: /Verify & Next/ }).click()
    await expect(
      page.getByText('Receipt has already been exported and can no longer be edited'),
    ).toBeVisible()
  })
})