import { expect, test } from '@playwright/test'
import { ACCOUNTANT_ID, seedSession } from './fixtures'

test.describe('Accountant gate', () => {
  test('blocks the console until a valid UUID is entered', async ({ page }) => {
    await page.goto('/clients')

    await expect(page.getByRole('heading', { name: 'Open the console' })).toBeVisible()
    const submit = page.getByRole('button', { name: 'Continue' })
    await expect(submit).toBeDisabled()

    await page.getByLabel('Accountant session id').fill('not-a-uuid')
    await expect(submit).toBeEnabled()
    await submit.click()
    await expect(page.getByRole('alert')).toHaveText('Enter a valid UUID')

    await page.getByLabel('Accountant session id').fill(ACCOUNTANT_ID)
    await expect(page.getByRole('alert')).toHaveCount(0)
    await submit.click()

    await expect(page.getByRole('heading', { level: 1, name: 'Clients' })).toBeVisible()
    expect(await page.evaluate(() => localStorage.getItem('kenyalang.accountant_id'))).toBe(
      ACCOUNTANT_ID,
    )
  })

  test('deep link to a review URL is gated too', async ({ page }) => {
    await page.goto('/clients/c1000000-0000-4000-8000-000000000001/inbox')
    await expect(page.getByRole('heading', { name: 'Open the console' })).toBeVisible()
    await expect(page.getByLabel('Accountant session id')).toBeVisible()
  })

  test('signing out returns to the gate and clears the stored id', async ({ page }) => {
    await seedSession(page)
    await page.goto('/clients')
    await expect(page.getByRole('heading', { level: 1, name: 'Clients' })).toBeVisible()

    await page.getByRole('button', { name: 'Sign out' }).last().click()

    await expect(page.getByRole('heading', { name: 'Open the console' })).toBeVisible()
    expect(await page.evaluate(() => localStorage.getItem('kenyalang.accountant_id'))).toBeNull()
  })

  test('an accountant with no clients sees the create-workspace empty state', async ({ page }) => {
    await seedSession(page, { accountantId: 'b0b0b0b0-2222-4333-8444-555555555555', clientId: null })
    await page.goto('/clients')

    await expect(page.getByRole('heading', { level: 2, name: 'Add your first client' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Add your first client' })).toBeVisible()
  })
})
