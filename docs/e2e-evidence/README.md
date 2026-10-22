# E2E evidence and UI/UX findings

Captured by `frontend/e2e/09-evidence.spec.ts` (`npm run test:e2e -- 09-evidence`) against the
seeded fixture database. Regenerate after any UI change; the shots are generated, not hand-edited.

| File | Surface | Viewport |
| --- | --- | --- |
| `1440-*.png` | clients, client form, inbox, review, exports, dashboard, upload, gate | 1440×960, full page |
| `320-*.png` | same surfaces | 320×720, full page |
| `390-upload-capture.png` | mobile capture surface | 390×844 |

## Defects found and fixed

Seven defects surfaced from the audit and are fixed in this branch, each with a regression test.

1. **Inbox overflowed the page at 640–700px (medium).** The table switched to its seven desktop
   columns at `sm` (640px) but needs ≈671px, so the document scrolled sideways by up to 31px on
   tablets in landscape. Fixed by moving the table breakpoint to `md`; `docs/04 §5` updated to
   match. Regression: `08-standards → 640/660/700px do not overflow`.
2. **A review deep link showed "Receipt not found" (high).** `ReviewPage` read the receipt
   through the store's `currentClientId` but never adopted the workspace from the URL, so a
   pasted link in a fresh browser failed while the same link after visiting the inbox worked.
   Fixed by adopting the route client first (`10-deeplink.spec.ts`).
3. **Dashboard "Total receipts" undercounted (medium).** It rendered
   `verified_count + unreviewed_count` = 8 for a workspace of 11 receipts, because rejected,
   unreadable and processing receipts are in neither count. Added `total_count` to
   `GET /api/clients` and the stat now shows 11.
4. **Clients table overflowed the page at 640–768px (medium).** The client workspace table
   switched to its six desktop columns at `sm` (640px) but its min-content is ≈622px, wider than
   the 576px container — so with three or more clients the document scrolled sideways by up to
   16px. Fixed by moving that breakpoint to `md` (same fix as the inbox); `docs/04 §2` updated.
   Regression: the full-surface width sweep in `08-standards`.
5. **`/upload` had two nested `<main>` landmarks (moderate).** axe flagged
   `landmark-no-duplicate-main` and `landmark-main-is-top-level`: `UploadPage` rendered its own
   `<main>` inside the shell's `<main id="main-content">`. Replaced with a `<div>`; the shell
   landmark is the only one.
6. **The review line-item table had an unlabeled action column (minor).** The delete column
   header carried `aria-label` on an empty `<th>`, which axe reports as `empty-table-header`.
   Replaced with an `sr-only` "Delete line" label, so the column is announced.
7. **Vitest collected the Playwright specs (low).** `npm test` treated `e2e/*.spec.ts` as unit
   tests. Excluded in `vite.config.ts`; `e2e/**` is linted with Node globals instead and
   type-checked by `tsconfig.e2e.json` through `tsc -b`.

## Observations, no change made

- **Sign-out is a 40px icon button and inbox filter tabs are 40px tall.** Below the 44px
  general guidance, but both are deliberate (`docs/04_ui_specs.md`, accessibility notes) and sit in dense desktop
  chrome; the mobile tab bar is 56px. Flagged, not changed — changing it is a design call.
- **Line-item inputs are 34px dense fields** (`docs/04_ui_specs.md`, review + accessibility notes), and the 44px rule applies to
  header fields and primary actions. Consistent with the spec.
- **axe-core WCAG 2.2 AA sweep is clean** on all six surfaces (wcag2a/2aa/21a/21aa/22aa plus
  best-practice rules), gated by `08-standards → every surface passes an axe WCAG 2.2 AA sweep`.
- **Palette passes WCAG AA.** `08-standards` walks every leaf text node on all six surfaces
  (computed colour vs the first opaque ancestor background) and fails on any pair below 4.5:1,
  or 3:1 for large text. `text-muted #5F665F` on `canvas #F6F1E7` = 5.25:1.
- **No slop.** No gradients, backdrop blur or text shadows anywhere in the rendered DOM; one
  `h1` per page; `prefers-reduced-motion` collapses transitions to 0.01ms; focus-visible paints
  a 2px ring; every async result is exposed on a `role="status"`/`role="alert"` region.
- **Horizontal reflow is clean** across a 17-width sweep (320, 360, 390, 414, 480, 560, 600, 639,
  640, 660, 700, 720, 768, 900, 1024, 1280, 1440) on all six surfaces; 720px is what 200% browser
  zoom gives on a 1440 desktop. Gated by `08-standards → every surface reflows across the width
  sweep`.

## Guide coverage

`web-production-motion-standards.txt` section by section. "Automated" means a committed spec
fails if this regresses; "manual" means it was inspected during this audit but has no gate.

| § | Subject | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Visual anti-slop (tokens, type, shape, icons, copy) | automated (partial) | no gradients/blur/text-shadow in DOM, one `h1` per page, token palette — `08-standards` |
| 2 | Motion (tool choice, composite-only, reduced motion, lifecycle) | automated | no animation library installed; `prefers-reduced-motion` collapses to 0.01ms — `08-standards` |
| 3 | Performance (bundle, fonts, images, states) | manual + partial | routes are `lazy()` behind `Suspense`; system font stack (no webfont CLS); inbox thumbs `loading="lazy"`; loading/empty/error states asserted per surface in `02`–`07` |
| 3 | Core Web Vitals (LCP/INP/CLS, Lighthouse) | **not run** | no deploy target; a Lighthouse run against the Vite dev server is unrepresentative. Measure on the demo host before launch |
| 4 | Backend and data (indexes, N+1, pagination) | manual | `EXPLAIN QUERY PLAN` on the three hot queries uses `idx_receipts_client_date`, `idx_audit_logs_receipt`, `idx_line_items_receipt`; receipt lists use `selectinload` and keyset-free `LIMIT/OFFSET` at 50/page |
| 5 | Security (secrets, authz, headers, uploads, supply chain) | automated (partial) | security headers asserted in `08-standards`; tenant scoping covered by backend pytest; `X-Accountant-Id` is demo-only and disabled outside `local`/`test` |
| 5 | Dependency audit | **split by tree** | `npm audit --omit=dev` = 2 moderate (`react-router`, `react-router-dom`); the 5 highs are devDependencies (build tooling) and never ship |
| 6 | SEO and metadata | n/a | internal accountant console, not indexable marketing pages |
| 7 | Accessibility (WCAG 2.2 AA) | automated | axe sweep (wcag2a/2aa/21a/21aa/22aa + best-practice) and a full-page contrast sweep on all six surfaces; focus-visible ring; dialog focus move/restore; 320px reflow |
| 7 | Screen-reader spot check | **not run** | no NVDA/JAWS available in this environment. axe covers structure and labels, not announcement quality |
| 8 | Legal and compliance | n/a | local accountant tool, no accounts, cookies, marketing email or payments |
| 9 | Operations | n/a for this scope | `/api/health/live` and `/api/health/ready` exist and are asserted in `01-gate`; deployment concerns belong to the demo host |

### Known exposure, not fixed

`react-router` 6.30.x carries two moderate advisories; the published fix for both is a major bump
to 7.18.4.

GHSA-wrjc-x8rr-h8h6 (open redirect via backslash in `Link` / `useNavigate`) does apply to this
SPA. It is low risk here only because no destination is attacker-controlled: every `Link` `to` and
every `navigate()` target is a template built from server-issued client/receipt ids and fixed
segments. Passing a raw query parameter into either would make it exploitable.

GHSA-337j-9hxr-rhxg (`deserializeErrors` during SSR hydration) cannot be reached: the app is
client-only (`createBrowserRouter`, no `hydrateRoot`, no `StaticRouter`).

Both are a documented demo risk, not a blocker. Upgrade after the demo.
