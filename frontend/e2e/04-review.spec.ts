import { expect, test } from '@playwright/test'
import { CLIENT_ID, RECEIPT, apiHeaders, auditCount, receiptState, seedSession } from './fixtures'

const review = (receiptId: string): string => `/clients/${CLIENT_ID}/review/${receiptId}`

test.describe('Review console', () => {
  test.beforeEach(async ({ page }) => {
    await seedSession(page)
  })

  test('surfaces the math mismatch and saves corrections as verified', async ({ page }) => {
    await page.goto(review(RECEIPT.save))

    await expect(page.getByRole('heading', { level: 2, name: 'Supplier & date' })).toBeVisible()
    await expect(page.getByLabel('Supplier Name')).toHaveValue('Bengkel E2E')
    await expect(page.getByText(/Line items total RM 100\.00 \+ Tax RM 6\.00 = Grand Total RM 106\.00/)).toBeVisible()

    await page.getByLabel('Supplier Name').fill('Bengkel E2E (corrected)')
    await expect(page.getByText('Unsaved changes')).toBeVisible()

    await page.getByRole('button', { name: /Verify & Next/ }).click()

    await expect(page).not.toHaveURL(new RegExp(RECEIPT.save))
    const saved = await receiptState(page, RECEIPT.save)
    expect(saved.status).toBe('STATUS_VERIFIED')
    expect(saved.merchant_name).toBe('Bengkel E2E (corrected)')
    expect(await auditCount(page, RECEIPT.save)).toBeGreaterThan(0)
  })

  test('blocks verification on an unparseable amount', async ({ page }) => {
    await page.goto(review(RECEIPT.clean))

    const verify = page.getByRole('button', { name: /Verify & Next/ })
    await expect(verify).toBeEnabled()

    await page.getByLabel(/^Grand Total/).fill('')
    await expect(page.getByText('Fix Grand Total before verifying.')).toBeVisible()
    await expect(verify).toBeDisabled()
    await expect(page.getByText(/Invalid amount/)).toBeVisible()

    await page.getByLabel(/^Grand Total/).fill('88.20')
    await expect(verify).toBeEnabled()
    // Restored to server truth, so nothing is pending.
    await expect(page.getByText('Unsaved changes')).toHaveCount(0)
  })

  test('a printed rounding line reconciles an otherwise correct receipt', async ({ page }) => {
    await page.goto(review(RECEIPT.clean))

    // 83.00 of lines + 5.20 tax = 88.20 as printed.
    await expect(page.getByText(/Line items total RM 83\.00 \+ Tax RM 5\.20 = Grand Total RM 88\.20/)).toBeVisible()

    // A till that rounds 88.20 down to 88.16 prints "ROUNDING -0.04"; without a
    // field for it the console reported a RM 0.04 error the user could not fix.
    await page.getByLabel(/^Rounding/).fill('-0.04')
    await page.getByLabel(/^Grand Total/).fill('88.16')

    await expect(page.getByText(/Line items total RM 83\.00 \+ Tax RM 5\.20 − Rounding RM 0\.04 = Grand Total RM 88\.16/)).toBeVisible()
    await expect(page.getByRole('button', { name: /Verify & Next/ })).toBeEnabled()
  })

  test('rejects only after confirmation and records the terminal status', async ({ page }) => {
    await page.goto(review(RECEIPT.reject))
    await page.getByRole('button', { name: /^Reject/ }).click()

    const dialog = page.getByRole('group', { name: 'Reject this receipt? This cannot be undone.' })
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText('Reject this receipt? This cannot be undone.')

    // Focus moves into the confirmation, and Cancel returns it to the trigger.
    await expect(dialog).toBeFocused()
    await dialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).toHaveCount(0)
    await expect(page.getByRole('button', { name: /^Reject/ })).toBeFocused()

    await page.getByRole('button', { name: /^Reject/ }).click()
    await page
      .getByRole('group', { name: 'Reject this receipt? This cannot be undone.' })
      .getByRole('button', { name: 'Reject' })
      .click()

    await expect(page).not.toHaveURL(new RegExp(RECEIPT.reject))
    expect((await receiptState(page, RECEIPT.reject)).status).toBe('STATUS_REJECTED')
  })

  test('guards unsaved edits behind a native leave dialog', async ({ page }) => {
    await page.goto(review(RECEIPT.clean))

    await page.getByLabel('Supplier Name').fill('Dirty draft')
    const backLink = page.getByTitle('Back to inbox without saving')
    await backLink.click()

    const leave = page.getByRole('alertdialog', { name: 'Leave without saving?' })
    await expect(leave).toBeVisible()
    await expect(leave).toContainText('Your corrections on this receipt will be lost.')

    await leave.getByRole('button', { name: 'Stay' }).click()
    await expect(page).toHaveURL(new RegExp(RECEIPT.clean))
    await expect(page.getByLabel('Supplier Name')).toHaveValue('Dirty draft')

    await backLink.click()
    await page
      .getByRole('alertdialog', { name: 'Leave without saving?' })
      .getByRole('button', { name: 'Leave' })
      .click()
    await expect(page).toHaveURL(new RegExp(`/clients/${CLIENT_ID}/inbox$`))
  })

  test('Ctrl+Enter saves without leaving the keyboard flow', async ({ page }) => {
    // `save` rather than `clean`: the upload spec re-captures clean-review.jpg and
    // asserts it is still awaiting review, so this spec must not settle it.
    await page.goto(review(RECEIPT.save))
    await expect(page.getByRole('button', { name: /Verify & Next/ })).toBeEnabled()

    await page.getByLabel('Supplier Name').click()
    // Escape blurs the field first; shortcuts are suppressed while typing.
    await page.keyboard.press('Escape')
    await page.keyboard.press('Control+Enter')

    await expect(page).not.toHaveURL(new RegExp(RECEIPT.save))
    expect((await receiptState(page, RECEIPT.save)).status).toBe('STATUS_VERIFIED')
  })

  test('an unexplained mismatch needs an explicit override, by mouse or key', async ({ page }) => {
    await page.goto(review(RECEIPT.math))
    // A mismatch is a legitimate manual-verify case, but not a silent one: the
    // primary action becomes an override and the override has to be confirmed.
    await expect(page.getByText(/Math Mismatch/)).toBeVisible()
    const override = page.getByRole('button', { name: 'Verify anyway' })
    await expect(override).toBeEnabled()

    await override.click()
    // The question is the alert; the actions live on the group that owns it.
    const band = page.getByRole('group', { name: /Verify with RM 5\.00 unexplained\?/ })
    await expect(page.getByRole('alert')).toContainText('Verify with RM 5.00 unexplained?')
    await expect(band).toContainText('The audit trail records that you overrode it.')
    // Opening the band must not have saved anything.
    expect((await receiptState(page, RECEIPT.math)).status).toBe('STATUS_NEEDS_REVIEW')

    await band.getByRole('button', { name: 'Cancel' }).click()
    await expect(band).toHaveCount(0)

    // The keyboard takes the same gate: Ctrl+Enter opens the band, not the save.
    await page.keyboard.press('Control+Enter')
    await expect(page.getByRole('alert')).toContainText('Verify with RM 5.00 unexplained?')
    expect((await receiptState(page, RECEIPT.math)).status).toBe('STATUS_NEEDS_REVIEW')

    // Escape dismisses the override without arming the reject band.
    await page.keyboard.press('Escape')
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByText('Reject this receipt? This cannot be undone.')).toHaveCount(0)
    expect((await receiptState(page, RECEIPT.math)).status).toBe('STATUS_NEEDS_REVIEW')

    await page.getByRole('button', { name: 'Verify anyway' }).click()
    await page
      .getByRole('group', { name: /Verify with RM 5\.00 unexplained\?/ })
      .getByRole('button', { name: 'Confirm override' })
      .click()
    await expect(page).not.toHaveURL(new RegExp(RECEIPT.math))
    expect((await receiptState(page, RECEIPT.math)).status).toBe('STATUS_VERIFIED')
  })

  test('an exported receipt opens read-only and still 409s a direct write', async ({ page }) => {
    await page.goto(review(RECEIPT.frozen))
    await expect(page.getByRole('heading', { level: 2, name: 'Supplier & date' })).toBeVisible()

    // The console refuses the edit up front rather than letting it fail on save.
    await expect(page.getByText(/already been exported, so it can no longer be edited/)).toBeVisible()
    await expect(page.getByLabel('Supplier Name')).toBeDisabled()
    await expect(page.getByRole('button', { name: /Verify & Next/ })).toBeDisabled()
    await expect(page.getByRole('button', { name: /^Reject/ })).toBeDisabled()

    // The keyboard shortcuts must not route around the disabled buttons.
    await page.keyboard.press('Escape')
    await expect(page.getByText('Reject this receipt? This cannot be undone.')).toHaveCount(0)
    await page.keyboard.press('Control+Enter')
    await expect(page.getByText(/already been exported/)).toHaveCount(1)
    await expect(page).toHaveURL(new RegExp(RECEIPT.frozen))

    // Alt+A would persist a phantom draft line and arm the leave guard. The bug
    // was the stored draft, so assert the persisted copy as well as the DOM.
    const draftKey = `kenyalang.draft.${RECEIPT.frozen}`
    const descriptions = page.getByLabel(/Line \d+ description/)
    const before = await descriptions.count()
    const storedBefore = await page.evaluate((key) => localStorage.getItem(key), draftKey)

    await page.keyboard.press('Alt+a')

    await expect(descriptions).toHaveCount(before)
    expect(await page.evaluate((key) => localStorage.getItem(key), draftKey)).toBe(storedBefore)

    // The backend guard is the real invariant: a direct write must still 409.
    const response = await page.request.put(`/api/v1/clients/${CLIENT_ID}/receipts/${RECEIPT.frozen}`, {
      headers: apiHeaders,
      data: { merchant_name: 'Should not stick' },
    })
    expect(response.status()).toBe(409)
    expect(await response.text()).toContain('already been exported')
  })
})