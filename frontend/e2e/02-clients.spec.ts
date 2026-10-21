import { expect, test } from '@playwright/test'
import { CLIENT_ID, CLIENT_NAME, EMPTY_CLIENT_NAME, clientNames, seedSession } from './fixtures'

test.describe('Client workspaces', () => {
  test.beforeEach(async ({ page }) => {
    await seedSession(page)
    await page.goto('/clients')
    await expect(page.getByRole('heading', { level: 1, name: 'Clients' })).toBeVisible()
  })

  test('lists both workspaces with receipt aggregates', async ({ page }) => {
    const table = page.getByRole('table', { name: 'Client workspaces' })
    await expect(table.getByText(CLIENT_NAME)).toBeVisible()
    await expect(table.getByText(EMPTY_CLIENT_NAME)).toBeVisible()

    // Seeded truth: 4 needs-review, 4 verified+exported on the main workspace.
    const row = table.getByRole('row').filter({ hasText: CLIENT_NAME })
    await expect(row).toContainText('202301234567')
    await expect(row).toContainText('4')

    const empty = table.getByRole('row').filter({ hasText: EMPTY_CLIENT_NAME })
    await expect(empty).toContainText('0')
  })

  test('opening a workspace navigates to its inbox and persists the selection', async ({ page }) => {
    const row = page.getByRole('row').filter({ hasText: CLIENT_NAME })
    await row.getByRole('button', { name: 'Open' }).click()

    await expect(page).toHaveURL(new RegExp(`/clients/${CLIENT_ID}/inbox`))
    await expect(page.getByRole('heading', { level: 1, name: 'Inbox' })).toBeVisible()
    expect(await page.evaluate(() => localStorage.getItem('kenyalang.current_client_id'))).toBe(
      CLIENT_ID,
    )
  })

  test('creates a client, validates the required name, and cancels cleanly', async ({ page }) => {
    await page.getByRole('button', { name: 'Add client' }).click()
    await expect(page.getByRole('heading', { level: 2, name: 'New client' })).toBeVisible()

    // Required-field validation is inline, not a browser bubble (form is noValidate).
    await page.getByRole('button', { name: 'Add client' }).last().click()
    await expect(page.getByText('Business name is required.')).toBeVisible()

    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByRole('heading', { level: 2, name: 'New client' })).toHaveCount(0)

    await page.getByRole('button', { name: 'Add client' }).click()
    const name = `E2E Created ${Date.now()}`
    await page.getByLabel('Business name').fill(name)
    await page.getByLabel('Registration number').fill('202399999999')
    await page.getByLabel('SST number').fill('W10-1808-99999999')
    await page.getByLabel('Industry category').fill('RETAIL')
    await page.getByRole('button', { name: 'Add client' }).last().click()

    await expect(page.getByRole('heading', { level: 2, name: 'New client' })).toHaveCount(0)
    await expect(page.getByRole('table', { name: 'Client workspaces' })).toContainText(name)

    // The new workspace is real server state, not an optimistic row.
    expect(await clientNames(page)).toContain(name)
  })
})