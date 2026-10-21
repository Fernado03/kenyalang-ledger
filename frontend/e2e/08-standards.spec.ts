import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { CLIENT_ID, seedSession } from './fixtures'

const PAGES = [
  { name: 'clients', path: '/clients', heading: 'Clients' },
  { name: 'inbox', path: `/clients/${CLIENT_ID}/inbox`, heading: 'Inbox' },
  { name: 'review', path: `/clients/${CLIENT_ID}/review/e2e00000-0000-4000-8000-000000000002`, heading: 'Review' },
  { name: 'dashboard', path: `/clients/${CLIENT_ID}/dashboard`, heading: 'Dashboard' },
  { name: 'exports', path: `/clients/${CLIENT_ID}/exports`, heading: 'Exports' },
  { name: 'upload', path: '/upload', heading: 'Upload receipts' },
] as const

/** Milliseconds from a CSS time value (`0.01ms`, `0.1s`). */
function ms(value: string): number {
  const parsed = /^(-?[\d.]+(?:e-?\d+)?)(ms|s)$/.exec(value.trim())
  if (parsed === null) throw new Error(`unparsable time: ${value}`)
  return Number(parsed[1]) * (parsed[2] === 's' ? 1000 : 1)
}

/** WCAG 2.x contrast failures for every leaf text node on the page. */
async function contrastFailures(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const parse = (value: string): [number, number, number] | null => {
      const match = /rgba?\(([^)]+)\)/.exec(value)
      if (match === null) return null
      const parts = match[1].split(',').map(Number)
      return [parts[0], parts[1], parts[2]]
    }
    const channel = (value: number): number => {
      const normalized = value / 255
      return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4
    }
    const luminance = ([r, g, b]: [number, number, number]): number =>
      0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)

    const failures: string[] = []
    const selector = 'p,span,a,button,dt,dd,th,td,label,h1,h2,h3,li,time'
    for (const element of Array.from(document.querySelectorAll(selector))) {
      if (element.children.length > 0) continue
      const text = (element.textContent ?? '').trim()
      if (text.length < 2) continue
      const box = element.getBoundingClientRect()
      if (box.width === 0 || box.height === 0) continue
      const style = getComputedStyle(element)
      if (style.visibility === 'hidden' || style.opacity === '0') continue

      const foreground = parse(style.color)
      if (foreground === null) continue
      // Walk up to the first opaque painter; gradients are out of scope by policy.
      let background: [number, number, number] | null = null
      let node: Element | null = element
      while (node !== null) {
        const nodeStyle = getComputedStyle(node)
        const painted = /rgba?\(([^)]+)\)/.exec(nodeStyle.backgroundColor)
        if (painted !== null && Number(painted[1].split(',')[3] ?? '1') > 0.5) {
          background = parse(nodeStyle.backgroundColor)
          break
        }
        if (nodeStyle.backgroundImage !== 'none') break
        node = node.parentElement
      }
      if (background === null) background = [246, 241, 231] // canvas token

      const light = luminance(background)
      const dark = luminance(foreground)
      const ratio = (Math.max(light, dark) + 0.05) / (Math.min(light, dark) + 0.05)
      const size = Number.parseFloat(style.fontSize)
      const bold = Number.parseInt(style.fontWeight, 10) >= 700
      const required = size >= 24 || (size >= 18.66 && bold) ? 3 : 4.5
      if (ratio < required) {
        failures.push(`${text.slice(0, 30)} — ${ratio.toFixed(2)}:1 < ${required}:1`)
      }
    }
    return failures
  })
}

const horizontalOverflow = (page: Page): Promise<number> =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)

test.describe('Production web standards', () => {
  test('API responses carry the documented security headers', async ({ request }) => {
    const response = await request.get('/api/clients', {
      headers: { 'X-Accountant-Id': 'a0000000-0000-4000-8000-000000000001' },
    })
    expect(response.status()).toBe(200)

    const headers = response.headers()
    expect(headers['x-content-type-options']).toBe('nosniff')
    expect(headers['x-frame-options']).toBe('DENY')
    expect(headers['referrer-policy']).toBe('strict-origin-when-cross-origin')
    expect(headers['permissions-policy']).toContain('camera=()')
    expect(headers['content-security-policy']).toContain("frame-ancestors 'none'")
    expect(headers['cache-control']).toBe('private, no-store')
  })

  test.describe('320px reflow', () => {
    test.use({ viewport: { width: 320, height: 720 } })

    for (const target of PAGES) {
      test(`${target.name} fits without horizontal scrolling`, async ({ page }) => {
        await seedSession(page)
        await page.goto(target.path)
        await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible()

        // Layout settles after data arrives; one frame is enough at 320px.
        await page.waitForLoadState('networkidle')
        expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0)
      })
    }

    test('the inbox table stacks instead of scrolling sideways', async ({ page }) => {
      await seedSession(page)
      await page.goto(`/clients/${CLIENT_ID}/inbox`)
      const table = page.getByRole('table', { name: 'Receipt inbox' })
      await expect(table).toBeVisible()

      // Mobile uses a stacked card layout, so nothing needs a horizontal scroller.
      await expect(table).toHaveCSS('display', 'block')
      await expect(table.locator('thead')).toBeHidden()
      expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0)

      // Above `md` the real column header returns.
      await page.setViewportSize({ width: 900, height: 900 })
      await expect(table).toHaveCSS('display', 'table')
      await expect(table.locator('thead')).toBeVisible()

      // Regression: 640-700px used to show the wide columns and overflow the page.
      for (const width of [640, 660, 700]) {
        await page.setViewportSize({ width, height: 900 })
        await expect.poll(() => horizontalOverflow(page)).toBeLessThanOrEqual(0)
      }
    })
  })

  test('every surface reflows across the width sweep', async ({ page }) => {
    await seedSession(page)
    // 200% zoom on a 1440 desktop lands at 720; both ends must stay scroll-free.
    const widths = [320, 360, 390, 414, 480, 560, 600, 639, 640, 660, 700, 720, 768, 900, 1024, 1280, 1440]

    for (const target of PAGES) {
      await page.setViewportSize({ width: 1440, height: 900 })
      await page.goto(target.path)
      await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible()
      await page.waitForLoadState('networkidle')

      for (const width of widths) {
        await page.setViewportSize({ width, height: 900 })
        await expect
          .poll(() => horizontalOverflow(page), {
            message: `${target.name} overflows at ${width}px`,
          })
          .toBeLessThanOrEqual(0)
      }
    }
  })

  test('keyboard focus paints a visible 2px ring', async ({ page }) => {
    await seedSession(page)
    await page.goto('/clients')
    await expect(page.getByRole('heading', { level: 1, name: 'Clients' })).toBeVisible()

    await page.keyboard.press('Tab')
    const ring = await page.evaluate(() => {
      const element = document.activeElement
      if (element === null) throw new Error('nothing focused')
      const style = getComputedStyle(element)
      return {
        outlineWidth: style.outlineWidth,
        outlineStyle: style.outlineStyle,
        outlineOffset: style.outlineOffset,
      }
    })
    expect(ring.outlineStyle).toBe('solid')
    expect(ring.outlineWidth).toBe('2px')
    expect(ring.outlineOffset).toBe('2px')
  })

  test('documented touch targets meet their sizes', async ({ page }) => {
    await seedSession(page)
    await page.goto('/clients')
    await expect(page.getByRole('heading', { level: 1, name: 'Clients' })).toBeVisible()

    const add = await page.getByRole('button', { name: 'Add client' }).boundingBox()
    expect(add?.height ?? 0).toBeGreaterThanOrEqual(44)

    await page.goto(`/clients/${CLIENT_ID}/inbox`)
    const open = page.getByRole('button', { name: 'Open' }).first()
    await expect(open).toBeVisible()
    const openBox = await open.boundingBox()
    expect(openBox?.height ?? 0).toBeGreaterThanOrEqual(44)

    // Mobile tab targets are documented as at least 56px tall.
    await page.setViewportSize({ width: 375, height: 720 })
    const tab = page.getByRole('link', { name: 'Clients' }).last()
    const tabBox = await tab.boundingBox()
    expect(tabBox?.height ?? 0).toBeGreaterThanOrEqual(56)
  })

  test('reduced motion collapses transitions and animations', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await seedSession(page)
    await page.goto('/clients')

    const add = page.getByRole('button', { name: 'Add client' })
    await expect(add).toBeVisible()
    const durations = await add.evaluate((element) => {
      const style = getComputedStyle(element)
      return { transition: style.transitionDuration, animation: style.animationDuration }
    })
    expect(ms(durations.transition.split(',')[0])).toBeLessThanOrEqual(1)
    expect(ms(durations.animation.split(',')[0])).toBeLessThanOrEqual(1)
  })

  test('every surface passes an axe WCAG 2.2 AA sweep', async ({ page }) => {
    // axe-core is a dev dependency; inject the bundle once per page.
    const axeSource = readFileSync(
      new URL('../node_modules/axe-core/axe.min.js', import.meta.url),
      'utf8',
    )

    await seedSession(page)
    for (const target of PAGES) {
      await page.setViewportSize({ width: 1440, height: 900 })
      await page.goto(target.path)
      await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible()
      await page.waitForLoadState('networkidle')
      await page.addScriptTag({ content: axeSource })

      const violations = await page.evaluate(async () => {
        const axe = (window as unknown as { axe: { run: (ctx: Document, opts: unknown) => Promise<{ violations: { id: string; help: string; nodes: unknown[] }[] }> } }).axe
        const result = await axe.run(document, {
          runOnly: {
            type: 'tag',
            values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'],
          },
        })
        return result.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`)
      })

      expect(violations, target.name).toEqual([])
    }
  })

  test('every surface keeps WCAG AA text contrast', async ({ page }) => {
    await seedSession(page)
    for (const target of PAGES) {
      await page.goto(target.path)
      await expect(page.getByRole('heading', { level: 1, name: target.heading })).toBeVisible()
      expect(await contrastFailures(page), target.name).toEqual([])
    }
  })
})