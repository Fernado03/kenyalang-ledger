import { expect, test } from '@playwright/test'
import { apiHeaders, CLIENT_ID, FIXED_MONTH, localMonth, seedSession } from './fixtures'

const DASHBOARD = `/clients/${CLIENT_ID}/dashboard`

test.describe('Spend dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await seedSession(page)
    await page.goto(DASHBOARD)
    await expect(page.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeVisible()
  })

  test('defaults to the current month and renders all four stats', async ({ page }) => {
    await expect(page.getByRole('textbox', { name: 'Month' })).toHaveValue(localMonth())

    for (const label of ['Spend this month', 'Receipts reviewed', 'Needs review', 'Total receipts']) {
      await expect(page.getByText(label, { exact: true })).toBeVisible()
    }
    await expect(
      page.getByText('Spend covers the selected month; receipt counts cover the whole workspace.'),
    ).toBeVisible()
  })

  test('a fixed month reports exact spend, suppliers, and category split', async ({ page }) => {
    await page.getByRole('textbox', { name: 'Month' }).fill(FIXED_MONTH)

    // March fixtures: 180.00 verified + 95.00 exported.
    await expect(page.getByText('RM 275.00')).toBeVisible()

    const suppliers = page.getByRole('table', { name: 'Top suppliers by spend' })
    const supplierRows = suppliers.getByRole('row')
    await expect(supplierRows).toHaveCount(3) // header + 2 suppliers
    await expect(supplierRows.nth(1)).toContainText('Pembekal Mac E2E')
    await expect(supplierRows.nth(1)).toContainText('RM 180.00')
    await expect(supplierRows.nth(2)).toContainText('Pembekal Beku E2E')
    await expect(supplierRows.nth(2)).toContainText('RM 95.00')

    const categories = page.getByRole('table', { name: 'Spend by category' })
    await expect(categories.getByRole('row').filter({ hasText: 'WORKSHOP' })).toContainText('RM 180.00')
    await expect(categories.getByRole('row').filter({ hasText: 'HARDWARE' })).toContainText('RM 95.00')
    await expect(page.getByText('Pre-tax line totals; document tax is excluded.')).toBeVisible()
  })

  test('a month with no verified receipts reports zero spend instead of vanishing', async ({
    page,
  }) => {
    await page.getByRole('textbox', { name: 'Month' }).fill('2026-01')

    // Empty months still render the stat grid; only the supplier list empties out.
    await expect(page.getByText('Spend this month', { exact: true }).locator('..')).toContainText(
      'RM 0.00',
    )
    await expect(page.getByText('No supplier totals for this month.')).toBeVisible()
    await expect(page.getByRole('table', { name: 'Top suppliers by spend' })).toHaveCount(0)
  })

  test('receipt counts are workspace-wide while spend is month-scoped', async ({ page }) => {
    await page.getByRole('textbox', { name: 'Month' }).fill('2026-01')

    const reviewed = page.getByText('Receipts reviewed', { exact: true }).locator('..')
    const needsReview = page.getByText('Needs review', { exact: true }).locator('..')
    const total = page.getByText('Total receipts', { exact: true }).locator('..')

    const value = async (locator: typeof reviewed): Promise<number> => {
      const text = (await locator.locator('dd').innerText()).trim()
      expect(text).toMatch(/^\d+$/)
      return Number(text)
    }

    const [rev, needs, all] = await Promise.all([
      value(reviewed),
      value(needsReview),
      value(total),
    ])
    // "Total receipts" counts every receipt, so rejected/failed/processing ones
    // are included and the reviewed+needs pair cannot add up to it.
    expect(rev + needs).toBeLessThanOrEqual(all)
    const response = await page.request.get(`/api/v1/clients/${CLIENT_ID}/receipts?limit=100`, { headers: apiHeaders })
    const body = (await response.json()) as { total: number }
    expect(all).toBe(body.total)
  })

  test('dashboard links back to the inbox without losing the workspace', async ({ page }) => {
    await page.getByRole('link', { name: 'Inbox', exact: true }).first().click()
    await expect(page).toHaveURL(new RegExp(`/clients/${CLIENT_ID}/inbox$`))
  })
})