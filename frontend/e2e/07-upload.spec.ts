import { readFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { CLIENT_ID, OTHER_ACCOUNTANT_ID, seedSession } from './fixtures'

const UPLOAD = '/upload'
/** Byte-identical to the seeded `clean-review.jpg`, so the backend dedupes it. */
const SEEDED_BLOB = `../backend/storage-e2e/tenants/${CLIENT_ID}/e2e00000-0000-4000-8000-000000000002.jpg`

test.describe('Upload capture surface', () => {
  test('asks for a workspace when the accountant has no clients', async ({ page }) => {
    await seedSession(page, { accountantId: OTHER_ACCOUNTANT_ID, clientId: null })
    await page.goto(UPLOAD)

    await expect(page.getByRole('heading', { level: 1, name: 'Upload receipts' })).toBeVisible()
    await expect(page.getByRole('heading', { level: 2, name: 'No workspace selected' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Go to clients' })).toHaveAttribute(
      'href',
      '/clients',
    )
    await expect(page.locator('input[type="file"]')).toHaveCount(0)
  })

  test('offers camera capture plus a multi-file picker with the documented limits', async ({
    page,
  }) => {
    await seedSession(page)
    await page.goto(UPLOAD)

    const camera = page.locator('input[type="file"][capture]')
    await expect(camera).toHaveAttribute('accept', 'image/jpeg,image/png,image/heic,application/pdf')
    await expect(camera).toHaveCount(1)
    await expect(page.locator('input[type="file"]:not([capture])')).toHaveCount(1)
    await expect(page.getByText('JPEG, PNG, HEIC, PDF · 50 files per batch · 15 MiB each · 50 MiB per batch')).toBeVisible()
    await expect(page.getByText('Processing continues in the background.')).toBeVisible()
  })

  test('rejects an unsupported file type and reports the server detail', async ({ page }) => {
    await seedSession(page)
    await page.goto(UPLOAD)

    await page.locator('input[type="file"]:not([capture])').setInputFiles({
      name: 'notes.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('not a receipt'),
    })

    await expect(page.getByText('Batch rejected: notes.txt: unsupported file type')).toBeVisible()
    // A rejected batch must not invent rows.
    await expect(page.getByRole('status').getByRole('listitem')).toHaveCount(0)
  })

  test('accepts a duplicate capture without re-running extraction', async ({ page }) => {
    await seedSession(page)
    await page.goto(UPLOAD)

    // Same name and byte length as the seeded row, so the backend dedupes it.
    await page.locator('input[type="file"]:not([capture])').setInputFiles({
      name: 'clean-review.jpg',
      mimeType: 'image/jpeg',
      buffer: await readFile(SEEDED_BLOB),
    })

    await expect(page.getByText('1 file accepted.')).toBeVisible()
    const accepted = page.getByRole('list', { name: 'Accepted this batch' })
    await expect(accepted.getByRole('listitem')).toHaveCount(1)
    await expect(accepted).toContainText('clean-review.jpg')
    await expect(accepted).toContainText('Needs review')
  })

  test('links back to the inbox for the active workspace', async ({ page }) => {
    await seedSession(page)
    await page.goto(UPLOAD)

    await expect(page.getByRole('link', { name: 'Inbox' }).first()).toHaveAttribute(
      'href',
      `/clients/${CLIENT_ID}/inbox`,
    )
  })
})