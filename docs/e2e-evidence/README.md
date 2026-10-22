# E2E evidence and UI/UX findings

Captured by `frontend/e2e/09-evidence.spec.ts` (`npm run test:e2e -- 09-evidence`) against the
seeded fixture database. Regenerate after any UI change; the shots are generated, not hand-edited.

| File | Surface | Viewport |
| --- | --- | --- |
| `1440-*.png` | clients, client form, inbox, review, exports, dashboard, upload, gate | 1440×960, full page |
| `320-*.png` | same surfaces | 320×720, full page |
| `390-upload-capture.png` | mobile capture surface | 390×844 |

## Defects found and fixed

Fourteen defects surfaced across the Playwright gate, the design audit and the live browser
pass. All are fixed in this branch; the ones with a plausible regression carry a test.

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

8. **A failed receipt load painted the previous receipt's fields (high, from a store review).**
   `loadReceipt` swallowed the error and left `activeReceipt` set, so opening receipt B after A
   showed A's values under B's URL, and Save wrote to A. The store now clears the draft, records
   `receiptError`, resets the saved stamp, and refuses a save whose expected id differs
   (`receiptStore.ts`, `ReviewPage.tsx`).
9. **The saved stamp bled onto the next receipt (medium).** `saveState === 'saved'` persisted
   across navigation, so the VERIFIED stamp overpainted the next NEEDS_REVIEW receipt for 1.2s.
   Flash state now carries `flashFor` and only paints for the matching receipt id.
10. **A failed client refresh looked like an empty account (medium).** `loadClients` replaced
    `clients` with `[]` on error, so the error banner and "Add your first client" rendered
    together. The previous list is now kept.
11. **An exported receipt still looked editable (high).** The console rendered live inputs and an
    enabled Reject for `STATUS_EXPORTED`; only a save attempt surfaced the backend 409. The
    sections now render inside a disabled `<fieldset>` with a plain explanation, and both
    mutating toolbar buttons are disabled, and the Ctrl+Enter / Escape / Add-Line / Delete-Line
    shortcuts are refused in the same guard so they cannot route around the buttons. Regression:
    `04-review → an exported receipt opens read-only and still 409s a direct write`, which also
    presses Escape and Ctrl+Enter against the frozen receipt and asserts the backend 409 directly.
12. **FastAPI 422 details were rendered raw (medium).** A malformed receipt id printed the whole
    validation array (`uuid_parsing`, `loc`, `ctx`). `parseDetail` now reduces a detail array to
    a field list, so the console says "Check these fields: path.receipt_id."
13. **The inbox filter tabs had no counts (medium) and the dashboard buried its own answer
    (medium).** Tabs now carry per-bucket counts from one grouped count on the receipt list
    response (`status_counts`, computed over every status so the active filter cannot narrow it).
    The dashboard promotes month spend to a 56px figure, demotes the three counts, and links
    "Needs review" into the inbox.
14. **Design tells removed.** Uppercase mono micro-labels (`.eyebrow`, `.section-label`,
    `.field-label`, `.data-table th`), the rail's coloured active bar, the mobile tab's brand top
    rule, the review sections' 01/02/03 numbering, and the four decorative `border-l-2` status
    bars all went. Zero-spend category rows no longer print `RM 0.00`. A receipt with no merchant
    shows `—` with the filename demoted to secondary text. The gate no longer prints
    `Route guard · docs/03 §3.1` at the user, and has one `h1`.

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
- **The Inbox keeps its per-row Open button.** A design audit called it a duplicate of the row
  `onClick`, but the row handler is not keyboard reachable (no `tabindex`, no key handler), so
  that button is the only tab path into the review console. Removing it would have been a
  keyboard regression.
- **A receipt image that 404s shows "Image request failed (HTTP 404)".** The seeded demo receipt
  has no stored blob; the fallback is correct and the surface stays usable.
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
