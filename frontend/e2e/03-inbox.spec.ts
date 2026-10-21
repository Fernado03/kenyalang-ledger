import { expect, test } from '@playwright/test'
import { CLIENT_ID, RECEIPT, seedSession } from './fixtures'

const INBOX = `/clients/${CLIENT_ID}/inbox`

test.describe('Receipt inbox', () => {
  test.beforeEach(async ({ page }) => {
    await seedSession(page)
    await page.goto(INBOX)
    await expect(page.getByRole('heading', { level: 1, name: 'Inbox' })).toBeVisible()
  })

  test('renders every seeded receipt with supplier, total, and status stamp', async ({ page }) => {
    const table = page.getByRole('table', { name: 'Receipt inbox' })
    await expect(table).toBeVisible()
    await expect(page.getByText(/receipts 1–11 of 11/)).toBeVisible()

    const mathRow = table.getByRole('row').filter({ hasText: 'Kedai E2E Hardware' })
    await expect(mathRow).toContainText('265.00')
    await expect(mathRow).toContainText('Δ RM 5.00')
    // The flag summary under the supplier name explains the delta.
    await expect(mathRow).toContainText('Math mismatch: Δ RM 5.00')

    const unreadable = table.getByRole('row').filter({ hasText: 'unreadable.jpg' })
    await expect(unreadable).toContainText('Unreadable')

    const processing = table.getByRole('row').filter({ hasText: 'processing.jpg' })
    await expect(processing).toContainText('Processing')
    await expect(processing.getByRole('button', { name: 'Open' })).toBeDisabled()

    await expect(
      table.getByRole('row').filter({ hasText: 'Pembekal Beku E2E' }),
    ).toContainText('Exported')
  })

  test('status filters request the right slice and expose aria-pressed', async ({ page }) => {
    const filter = page.getByRole('group', { name: 'Status filter' })

    await filter.getByRole('button', { name: 'Needs review' }).click()
    await expect(filter.getByRole('button', { name: 'Needs review' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await expect(page.getByText(/receipts 1–4 of 4/)).toBeVisible()

    // The Verified tab excludes exported rows even though the client aggregate counts them.
    await filter.getByRole('button', { name: 'Verified' }).click()
    await expect(page.getByText(/receipts 1–2 of 2/)).toBeVisible()

    await filter.getByRole('button', { name: 'Exported' }).click()
    await expect(page.getByText(/receipts 1–2 of 2/)).toBeVisible()

    await filter.getByRole('button', { name: 'Rejected' }).click()
    await expect(page.getByText(/receipts 1–1 of 1/)).toBeVisible()
    await expect(page.getByRole('table', { name: 'Receipt inbox' })).toContainText('Tidak Sah E2E')

    await filter.getByRole('button', { name: 'All' }).click()
    await expect(page.getByText(/receipts 1–11 of 11/)).toBeVisible()
  })

  test('a filtered empty result shows the empty state, not a blank table', async ({ page }) => {
    await page.goto(`/clients/c1000000-0000-4000-8000-000000000002/inbox`)
    await expect(page.getByRole('heading', { level: 1, name: 'Inbox' })).toBeVisible()
    await expect(page.getByText('No receipts yet — drop a batch above.')).toBeVisible()
    await expect(page.getByRole('table', { name: 'Receipt inbox' })).toHaveCount(0)
  })

  test('thumbnails load lazily and fill in when scrolled into view', async ({ page }) => {
    const requested = new Set<string>()
    page.on('request', (request) => {
      if (request.url().includes('/image')) requested.add(request.url())
    })

    // Short viewport: only the first rows are on screen, so only they may fetch.
    await page.setViewportSize({ width: 1280, height: 420 })
    await page.goto(INBOX)
    await expect(page.getByRole('table', { name: 'Receipt inbox' })).toBeVisible()
    await page.waitForTimeout(500)

    const aboveTheFold = requested.size
    expect(aboveTheFold).toBeGreaterThan(0)
    expect(aboveTheFold).toBeLessThan(11)

    // Rows below the fold fetch only once scrolled to.
    await page.getByRole('row').filter({ hasText: 'Tidak Sah E2E' }).scrollIntoViewIfNeeded()
    await expect.poll(() => requested.size).toBeGreaterThan(aboveTheFold)
  })

  test('row click and the Open button both reach the review console', async ({ page }) => {
    const row = page.getByRole('row').filter({ hasText: 'Restoran E2E' })
    await row.getByRole('button', { name: 'Open' }).click()

    await expect(page).toHaveURL(new RegExp(`/review/${RECEIPT.clean}$`))
    await expect(page.getByRole('heading', { level: 2, name: 'Supplier & date' })).toBeVisible()
  })
})