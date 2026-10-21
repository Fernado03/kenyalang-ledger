import { mkdir } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { CLIENT_ID, RECEIPT, seedSession } from './fixtures'

const OUT = '../docs/e2e-evidence'

/**
 * The mobile tab bar is `fixed`, so a full-page shot paints it mid-document.
 * Hide only that bar; the desktop rail is `fixed` too and must stay visible.
 */
async function hideFixedChrome(page: Page): Promise<void> {
  await page.addStyleTag({ content: 'nav[aria-label="Primary"] { display: none !important; }' })
}

/** Visual evidence for the UI/UX review; not part of the behavioural gates. */
test.describe('UI evidence capture', () => {
  test.use({ viewport: { width: 1440, height: 960 } })

  test('captures every surface at desktop and 320px', async ({ page }) => {
    await mkdir(OUT, { recursive: true })
    await seedSession(page)

    const shots = [
      { name: 'clients', path: '/clients', heading: 'Clients' },
      { name: 'client-form', path: '/clients', heading: 'Clients', openForm: true },
      { name: 'inbox', path: `/clients/${CLIENT_ID}/inbox`, heading: 'Inbox' },
      { name: 'review', path: `/clients/${CLIENT_ID}/review/${RECEIPT.math}`, heading: 'Review' },
      { name: 'exports', path: `/clients/${CLIENT_ID}/exports`, heading: 'Exports' },
      { name: 'dashboard', path: `/clients/${CLIENT_ID}/dashboard`, heading: 'Dashboard' },
      { name: 'upload', path: '/upload', heading: 'Upload receipts' },
      { name: 'gate', path: '/clients', heading: 'Open the console', anonymous: true },
    ]

    for (const shot of shots) {
      await page.setViewportSize({ width: 1440, height: 960 })
      if (shot.anonymous) {
        await page.context().clearCookies()
        await page.addInitScript(() => localStorage.clear())
      } else {
        await seedSession(page)
      }
      await page.goto(shot.path)
      await expect(page.getByRole('heading', { name: shot.heading }).first()).toBeVisible()
      if (shot.openForm === true) {
        await page.getByRole('button', { name: 'Add client' }).click()
        await expect(page.getByRole('heading', { name: 'New client' })).toBeVisible()
      }
      await page.waitForLoadState('networkidle')
      // Full-page shots make `fixed` chrome paint mid-page, which reads as an
      // overlap that does not exist on screen; hide it for the capture only.
      await hideFixedChrome(page)
      await page.screenshot({ path: `${OUT}/1440-${shot.name}.png`, fullPage: true })

      await page.setViewportSize({ width: 320, height: 720 })
      await page.waitForTimeout(250)
      await page.screenshot({ path: `${OUT}/320-${shot.name}.png`, fullPage: true })
    }

    // Mobile capture surface with the camera flow front and centre.
    await seedSession(page)
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/upload')
    await page.waitForLoadState('networkidle')
    await hideFixedChrome(page)
    await page.screenshot({ path: `${OUT}/390-upload-capture.png`, fullPage: true })
  })
})
