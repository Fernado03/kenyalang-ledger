import { expect, test } from '@playwright/test'
import { ACCOUNTANT_ID, CLIENT_ID, RECEIPT, seedSession } from './fixtures'

/**
 * Pasting a review URL into a fresh tab must work: the page has to adopt the
 * workspace from the path instead of trusting the last stored workspace.
 */
test.describe('Review deep link', () => {
  test('a review URL opens the receipt in a browser with no stored workspace', async ({ page }) => {
    await page.addInitScript((id) => {
      localStorage.clear()
      localStorage.setItem('kenyalang.accountant_id', id)
    }, ACCOUNTANT_ID)

    await page.goto(`/clients/${CLIENT_ID}/review/${RECEIPT.clean}`)

    await expect(page.getByRole('heading', { level: 1 })).toContainText('Review receipt')
    await expect(page.getByText('Receipt not found')).toBeHidden()
    await expect(page.getByLabel('Supplier name')).toHaveValue('Restoran E2E')
    // Adopting the workspace must survive a reload of the same URL.
    await page.reload()
    await expect(page.getByLabel('Supplier name')).toHaveValue('Restoran E2E')
  })

  test('the stored workspace follows the URL when switching clients', async ({ page }) => {
    await seedSession(page)
    await page.goto(`/clients/${CLIENT_ID}/review/${RECEIPT.clean}`)
    await expect(page.getByLabel('Supplier name')).toHaveValue('Restoran E2E')

    await seedSession(page, { clientId: 'c1000000-0000-4000-8000-000000000002' })
    await page.goto(`/clients/${CLIENT_ID}/review/${RECEIPT.clean}`)
    await expect(page.getByLabel('Supplier name')).toHaveValue('Restoran E2E')
  })
})
