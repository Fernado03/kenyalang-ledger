# Kenyalang Ledger — Step 4: UI/UX Specification (Implemented Demo)

This document describes the interface that actually exists in `frontend/src`. It is a
specification of the shipped demo, not an aspirational design system: every screen, control,
and keyboard binding named here can be found in the repository. Where the assignment brief
asks for something the demo does not render (for example an expense-category column in the
line-item editor), the gap is stated explicitly in §4.6 rather than invented.

The frontend is a React 18 + TypeScript + Vite single-page app using Tailwind CSS and React
Router. It talks to the FastAPI backend over JSON, attaching the acting accountant's UUID as
`X-Accountant-Id`. There is no component library, no animation framework, and no formal
accessibility certification.

---

## 4.1 Visual Anti-Slop Foundations & Design Tokens

Kenyalang Ledger is an enterprise data-entry workhorse, not a lifestyle landing page. The
interface targets the density and restraint of Linear or a Bloomberg terminal: hard borders,
no gradients, no glassmorphism, and immediate feedback.

### Color Tokens (`frontend/tailwind.config.js`)

A high-contrast **Slate & Deep Hornbill Teal** theme. The teal accent grounds the brand in
Sarawak without relying on generic tech-blue.

```javascript
// tailwind.config.js (abridged, values copied verbatim)
module.exports = {
  theme: {
    extend: {
      colors: {
        canvas: '#F8FAFC',            // Slate 50
        surface: '#FFFFFF',
        'surface-subtle': '#F1F5F9',  // Slate 100
        border: '#CBD5E1',            // Slate 300
        'border-focus': '#0F172A',    // Slate 900
        'text-primary': '#0F172A',
        'text-secondary': '#475569',
        'text-muted': '#475569',      // deliberately >= 4.5:1 on white and surface-subtle
        brand: { 50: '#F0FDFA', 500: '#14B8A6', 700: '#0F766E', 900: '#134E4A' },
        verified: { bg: '#ECFDF5', border: '#10B981', text: '#065F46' },
        warning:  { bg: '#FFFBEB', border: '#F59E0B', text: '#92400E' },
        mismatch: { bg: '#FEF2F2', border: '#EF4444', text: '#991B1B' },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      height: { 'dense-row': '40px' },
    },
  },
};
```

`text-muted` is deliberately the same value as `text-secondary` (`#475569`): Slate 400 failed
contrast on `surface-subtle`, so the token was darkened rather than left unusable. The
conformance claim in the `tailwind.config.js` comment is a stale comment, not an audit result;
see §4.4.

`border-focus` (`#0F172A`) is also used as the hover-tooltip background in `ReceiptCanvas`.

### Console Chrome (`frontend/src/components/AppShell.tsx`)

Every authenticated console page renders inside `AppShell`: a 56px top bar with the 20px brand
mark, the client-scoped nav (`Clients`, `Inbox`, `Dashboard`, `Exports`, `Upload`), the
accountant id, and Sign out. `Clients` is active only on `/clients`; `Inbox` stays active on
both the inbox and review routes. The bar is static below `sm` (it scrolls away) and sticky
from `sm` up. The brand mark and favicon use the deep teal token; no purple placeholder
remains.

### Typography & Tabular Numerals

* **Interface font:** default Tailwind sans stack (no custom `fontFamily.sans` override).
* **Financial font:** `JetBrains Mono`, then `ui-monospace`, `SFMono-Regular`, `Menlo`,
  `monospace` (`fontFamily.mono`).
* **Mandatory rule for Ringgit values and quantities** (`frontend/src/index.css`):

```css
.font-mono-numbers {
  font-family: 'JetBrains Mono', monospace;
  font-variant-numeric: tabular-nums lining-nums;
  letter-spacing: -0.02em;
}
```

Tabular numerals keep decimal points aligned vertically in accounting tables. Money is parsed
to integer cents (`BigInt`) in `frontend/src/lib/format.ts`; it is never accumulated in
floats. `parseMoneyToCents` accepts an optional `RM` prefix, spaces, and thousands commas,
plus at most two fraction digits; `formatCents` prints a plain two-decimal string, and
`formatMoneyDisplay` prints `RM 99.50` or an em dash for a missing/invalid value.
`formatDate` turns an ISO `YYYY-MM-DD` string into `DD/MM/YYYY` and prints `-` otherwise.

---

## 4.2 Motion Architecture & Micro-Interactions

No animation library is installed (`frontend/package.json` has no Framer Motion or similar).
Native CSS is the whole motion system, because an accountant reviewing a hundred receipts an
hour is slowed down by entrance effects.

* **Interaction speed:** `transition-colors duration-100 ease-out` on hover and focus in the
  component class strings.
* **Review transitions:** none. Save-and-next swaps the receipt without a fade.
* **Reduced motion:** `frontend/src/index.css` collapses animation, transition, and smooth
  scroll under `prefers-reduced-motion: reduce`.
* **Receipt canvas:** pan and zoom apply
  `transform: translate3d(x, y, 0) scale(z)` with `transform-origin: 0 0` and
  `will-change: transform` on the image layer, so dragging does not trigger layout
  recalculation (`frontend/src/components/ReceiptCanvas.tsx`).
* **Route changes:** React Router swaps pages with no page-transition animation; lazy routes
  render a plain `RouteFallback` while loading.

### Keyboard Workflow (`frontend/src/lib/reviewShortcuts.ts`)

The review console installs **one** `window` keydown listener. Bindings are resolved by the
pure function `resolveReviewShortcut(event, { typing, focusedLine })`, which is unit-tested in
`frontend/src/lib/reviewShortcuts.test.ts` without a DOM.

| Keys | While typing in a field | Outside a field |
|---|---|---|
| `Escape` | blur the field | open the inline reject confirmation |
| `Cmd/Ctrl+Enter` | ignored | save and verify, then open the next receipt |
| `Alt+A` | ignored | append a blank line item |
| `Alt+Backspace` | ignored | delete the most recently focused line, if one is remembered |
| `[` | ignored | zoom the canvas out |
| `]` | ignored | zoom the canvas in |
| `R` | ignored | reset zoom to 100% and recenter |

Additional state handling lives in `ReviewPage.tsx`, above the resolver:

* When the inline reject strip is open, `Escape` cancels it and consumes the key.
* When the leave-without-saving dialog is open, `Escape` resets the router blocker and no
  other binding runs.
* Zoom keys are ignored while `Meta`, `Ctrl`, or `Alt` is held. Zoom bounds are `0.2`–`8`
  with a `1.25` step; the same functions back the on-screen `−`, `+`, and `Reset` buttons.
* No shortcut fires while an input, textarea, select, or `contenteditable` has focus, so typing
  a description cannot trigger a save, reject, or structural edit. `Escape` is deliberately
  the exception: it blurs the field instead.
* `focusedLineKey` is set when a line input receives focus and cleared after a deletion, not on
  blur; `Alt+Backspace` therefore acts on the last-focused row once focus has left the inputs.

### Two-Cent Math Tolerance (`frontend/src/lib/audit.ts`)

`auditMath(draft)` reconciles **the printed line totals plus tax against the grand total**, in
integer cents, never quantity × unit price for the main equation. `TOLERANCE_CENTS = 2n` and a
delta reconciles when `|Δ| <= 2` cents. This matches the backend reconciler's `0.02`.

* `Δ = RM 0.01`: `matches = true`; `MathBanner` renders the emerald "Math Matches" strip with
  the full breakdown and **still retains** `deltaCents = 1n` (the one-cent rounding is not
  hidden from the data model, though the green strip prints the breakdown rather than a
  separate delta figure).
* `Δ = RM 0.02`: reconciles, same as above (the boundary is inclusive).
* `Δ = RM 0.03`: `matches = false`; the banner reads
  `Math Mismatch: Line items total RM … + Tax RM … ≠ Grand Total RM … (Difference: RM 0.03)`.
* Invalid input is distinct from a mismatch: unparseable money, a non-positive quantity, or a
  line whose `line_total` differs from `qty × unit_price` by more than
  `TOLERANCE_CENTS * 100n` marks the draft `valid = false`, names the offending fields, and
  disables **Verify & Next** (`Fix {field} before verifying.`).
* An SST number anywhere in the field (`[A-Z]\d+-\d+-\d+`, upper-cased before matching, e.g.
  `W10-1808-32000018` or `200401032489 / Y24-1808-31015655`) with zero tax adds the amber chip
  `Missing SST on Registered Merchant`. The chip mirrors `extract_sst_number` in the backend so
  the console and the audit never disagree.

`MathBanner` is `role="status" aria-live="polite"`, so every recalculation is announced as the
accountant types. It also shows `Unsaved changes` whenever the draft differs from server truth.

---

## 4.3 Screen-by-Screen Component Specifications

### 1. `SCR-01`: Client Workspace Switcher (`/clients`)

* **Purpose:** choose or create the client workspace that scopes every receipt, export, and
  dashboard request.
* **Populated table columns:** Client Name, Registration, SST, Industry, **Unreviewed**,
  **Verified**, Action.
* **Counts:** both aggregates arrive in the same `GET /api/clients` response
  (`unreviewed_count`, `verified_count`), so the page costs one request regardless of client
  count.
* **Create:** inline form (`ClientForm`), validated business name; invalid fields carry
  `aria-invalid` and `aria-describedby` pointing at the error element.
* **States:** loading skeleton, error banner with retry, empty state prompting the first
  client, populated table.

### 2. `SCR-02`: Batch Inbox & Upload Dropzone (`/clients/:clientId/inbox`)

* **Header:** `← Clients` link, page title `Inbox`, and the client business name as a subtitle.
  Global navigation is owned by `AppShell`; the page header does not repeat nav links.
* **Back links:** `← Clients` on Inbox; `← Inbox` on Dashboard, Exports, Review, and Upload.
* **Density:** 40px rows (`h-dense-row`).
* **Columns:** Thumbnail, Supplier, Date, Items, Grand Total (right-aligned), Status, and the
  per-row action that opens the receipt in the review console.
  * Thumbnail: 36×36 (`h-9 w-9`) in a 56px preview column (`w-14`), fetched as an authenticated
    blob with
    `X-Accountant-Id` and rendered from an object URL that is revoked on cleanup. `alt` is the
    filename. A missing image or failed fetch renders a bordered placeholder with
    `role="img"` and `aria-label="No preview for {filename}"`.
  * Supplier: `merchant_name`, falling back to `filename`; flagged rows print their flag
    details beneath it (`Math Mismatch: Δ RM x.xx`, `Missing Date`, otherwise the raw flag).
  * Date: `DD/MM/YYYY` via `formatDate`, or `-` when absent.
  * Items: `line_item_count`.
  * Grand Total: `formatMoneyDisplay`, or `—` when absent.
  * Status: `StatusPill` (matrix below).
  * Action: a focusable `Review` `<button>` in the last cell. The whole row is also clickable
    for mouse users, so the button is the keyboard-accessible affordance; there is no row-level
    Enter binding. Rows in a processing state keep the label `Review` but disable the button;
    clicking anywhere on such a row does nothing. The status pill already communicates the
    processing state, so the action never repeats a second `Processing` label.
* **Row accents:** a 2px left border in `warning-border` for `STATUS_NEEDS_REVIEW`, and in
  `mismatch-border` for `ERR_UNREADABLE`, `ERR_TIMEOUT`, `ERR_FILE_CORRUPT`, or
  `ERR_EXTRACTION`.
* **No bulk selection and no bulk actions.** Verification and rejection are per-receipt
  decisions, each with its own audit trail.
* **Filters:** five rendered tabs — `All`, `Needs Review`, `Verified`, `Exported`, `Rejected`.
  Each is `aria-pressed`; the value (`ALL`, `NEEDS_REVIEW`, `VERIFIED`, `EXPORTED`, `REJECTED`)
  is passed verbatim as the backend `status` query parameter.
* **Pagination:** offset-based, `PAGE_SIZE = 50`. The footer reads
  `Showing {first}–{last} of {total}` (en dash) with Previous and Next buttons, disabled at the
  ends. The footer renders only when `total > 0`, and there is no page-number control. The
  backend defaults `limit` to 50 and caps it at 200.
* **Polling:** while any row on the current page is `PROCESSING_OCR`, `PROCESSING_LLM`, or
  `VALIDATING_MATH`, a 3-second `setInterval` refetches the current offset. The interval is
  cleared when no processing row remains or the page unmounts; it does not reset pagination.
* **Upload dropzone:** `UploadDropzone`, which is separate from the `/upload` page's own file
  inputs. Dropping or browsing uploads immediately (there is no separate submit or cancel
  list), and states `Drop receipts here, or click to browse. Max 50 files per batch.` Its
  hidden input accepts `image/jpeg,image/png,image/heic,.pdf`. `UploadDropzone` owns no live
  region; the host page supplies one. The inbox host's `aria-live="polite"` region reports
  `Uploading…`, `{n} files queued for processing.`, per-file errors, or a batch-level failure;
  `/upload` reports `{n} files accepted.` in its own live region.
* **States:** empty (`No receipts yet — drop a batch above.`, with the format/size hint),
  loading skeleton (five rows), populated, flagged, and an error banner with retry.

#### Status Pill Design Matrix (`frontend/src/components/StatusPill.tsx`)

Every pill is a `<span>` with
`inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium whitespace-nowrap`
and always carries `data-status={status}`. The 28px pill sits inside the 40px dense row. Icons
are `aria-hidden`; the text carries meaning.

| Status | Visual | Text | `title` |
|---|---|---|---|
| `STATUS_AUTO_VERIFIED`, `STATUS_VERIFIED` | verified bg/border/text | `● Selesai` | — |
| `STATUS_EXPORTED` | `surface-subtle` + `border` + `brand-900` | `→ Dieksport` | — |
| `STATUS_REJECTED` | mismatch bg/border/text | `✕ Ditolak` | — |
| `STATUS_NEEDS_REVIEW` + a flag starting `MATH_MISMATCH_DELTA_` | mismatch bg/border/text | `! Δ RM {suffix}` | `Math mismatch: Δ RM {suffix}` |
| `STATUS_NEEDS_REVIEW` + confidence known and `< 0.8` | warning bg/border/text | `? Semak OCR ({formatConfidence(score)})` | `Low OCR confidence` |
| `STATUS_NEEDS_REVIEW`, otherwise | warning bg/border/text | `! Perlu Semak` | — |
| `PENDING_UPLOAD`, `UPLOADED`, `PROCESSING_OCR`, `PROCESSING_LLM`, `VALIDATING_MATH` | `surface-subtle` + `border` + `text-secondary` | `Memproses...` | — |
| `ERR_UNREADABLE` | mismatch bg/border/text | `✕ Tidak Boleh Dibaca` | `processingError ?? label` |
| `ERR_TIMEOUT` | mismatch bg/border/text | `✕ Masa Tamat` | `processingError ?? label` |
| `ERR_EXTRACTION` | mismatch bg/border/text | `✕ Ekstraksi Gagal` | `processingError ?? label` |
| Any other status (`ERR_FILE_CORRUPT` and future values) | mismatch bg/border/text | `✕ Fail` | `processingError ?? label` |

Confidence handling is exact:

* The score is `confidence` only when it is defined, finite, and `>= 0`; otherwise it is
  `null` and the pill falls through to `Perlu Semak`.
* `0 <= score < 0.8` selects the low-confidence variant. `formatConfidence` clamps with
  `Math.min(confidence, 1)` and rounds, so `0.799` prints `80%`, `0.64` prints `64%`, and a
  value above `1` prints `100%`.
* The mismatch flag wins over confidence: if both are present, the delta variant renders.

`processingError` is an optional prop. `StatusPill.test.tsx` passes
`"extraction provider unavailable"` to prove the tooltip path; the current `InboxPage` and
`ReviewPage` call sites do **not** pass it, so error pills in the running app show the
fallback label as their tooltip even though the backend writes that message into
`processing_error`.

### 3. `SCR-03`: Split-Screen Review Console (`/clients/:clientId/review/:receiptId`)

A 50/50 desktop split inside `AppShell`: the 57px app header sits above a
`lg:h-[calc(100dvh-57px)] lg:grid-cols-2` grid, canvas left and scrolling form right. Below
`lg` the panes stack: canvas at `40dvh` above the form, the field and total grids
collapse to one column, and the line-item grid scrolls horizontally. Loading and error states
also render inside `AppShell`, keeping the nav visible. The diagram below shows the review
region only.

```
┌───────────────────────────────────────────────┬───────────────────────────────────────────────┐
│ LEFT: ReceiptCanvas                           │ RIGHT: verification form                      │
├───────────────────────────────────────────────┼───────────────────────────────────────────────┤
│ [−] 100% [+] [Reset]                          │ ← Inbox   ID: 1a2b3c4d   [StatusPill]          │
│                                               │         [Reject (Esc)] [Verify & Next (Ctrl+↵)]│
│ receipt image, wheel-zoom and drag-pan        ├───────────────────────────────────────────────┤
│ SVG provenance/OCR overlay                    │ Merchant & Date                               │
│ tooltip on hover                              │ [Supplier Name]        [Merchant SST]         │
│                                               │ [Invoice Date]         [Invoice Number]       │
│                                               │ [Merchant BRN]                                │
│                                               ├───────────────────────────────────────────────┤
│                                               │ Line Items                                    │
│                                               │ Description | Qty | Unit (RM) | Total (RM) | ✕│
│                                               │ [+ Add Line (Alt+A)]                 3 lines  │
│                                               ├───────────────────────────────────────────────┤
│                                               │ Totals & Tax Audit                            │
│                                               │ [Subtotal] [SST (6%)] [Grand Total]           │
│                                               │ Line Items Total RM …                         │
│                                               │ Confidence —% · Lines … + Tax … = Total …     │
│                                               │ MathBanner                                    │
│                                               │ Audit history (collapsible)                   │
└───────────────────────────────────────────────┴───────────────────────────────────────────────┘
```

**Header (sticky, right pane):**

* `← Inbox` link (leaves without saving), `ID: {receipt.id.slice(0, 8)}` in mono, and the
  `StatusPill`.
* `Reject (Esc)` opens a confirmation; `Verify & Next (Ctrl+↵)` is disabled while saving or while
  the draft is invalid. While saving the labels become `Rejecting…` and `Saving…`.
* A successful save sets a `✓ Verified` flash (auto-cleared after 1200 ms) and immediately
  navigates to the next `STATUS_NEEDS_REVIEW` receipt in the loaded inbox list, or back to the
  inbox when none remains. The flash is therefore rarely visible: the page unmounts on
  navigation.
* Save errors render inline in a mismatch-coloured box. Invalid drafts render
  `Fix {field} before verifying.` with `role="status"`.
* Reject is guarded by an inline strip with `role="alertdialog" aria-label="Confirm rejection"`:
  `Reject this receipt? This cannot be undone.` with `Cancel` and `Reject`. The strip takes
  focus when opened so `Escape` lands on it. Confirming calls the reject route
  (`POST …/reject`), which sets `STATUS_REJECTED` and writes an audit row, then advances to the
  next receipt.

**Merchant & Date** (all `LabelledInput`, `htmlFor`/`id` bound, two-column grid):

| Label | Draft field | Input |
|---|---|---|
| Supplier Name | `merchant_name` | text |
| Merchant SST | `merchant_sst` | text |
| Invoice Date | `invoice_date` | `type="date"` |
| Invoice Number | `invoice_number` | text |
| Merchant BRN | `merchant_brn` | text |

There is no combined BRN/TIN field: BRN and SST are separate strings. Focusing any input sets
it as the canvas's active field; blurring clears it.

**Line Items** (`frontend/src/components/LineItemsEditor.tsx`):

* Columns: Description, Qty, Unit (RM), Total (RM), and a per-row delete button
  (`aria-label="Remove line {n}"`, 44×44). Numeric inputs are right-aligned with tabular
  numerals and `inputMode="decimal"`; they stay text while editing.
* Each input has an `aria-label` of the form `Line 2 description`, `Line 2 quantity`,
  `Line 2 unit price`, `Line 2 total`.
* `+ Add Line (Alt+A)` appends a row; the footer prints `{n} lines`.
* A row whose **server** line item has `confidence < 0.8` renders on `warning-bg` with a dashed
  underline on the description and a `? {formatConfidence(...)}` badge. Editing the draft does
  not change that badge; it is provenance, not validation.
* The focused row gets `bg-brand-50`, and the canvas highlights the matching
  `line_items[i]` box.
* **No expense-category column is rendered, and `expense_category` is not part of the
  frontend `ReceiptLineItem` type.** The backend persists and returns the field; see §4.5 and
  §4.6.

**Totals & Tax Audit:**

* Three inputs: Subtotal, SST (6%), Grand Total — labels wrap the inputs.
* `Line Items Total` is derived from the draft's `line_total` column.
* A mono caption prints
  `Confidence {n}% · Lines {x} + Tax {y} = Total {z}`.
* `MathBanner` (rules in §4.2) plus the `Missing SST on Registered Merchant` chip and the
  `Unsaved changes` hint.
* `Audit history` is a `<details>` panel whose rows are loaded from
  `GET …/receipts/{receiptId}/audit` when the receipt loads. Each row shows `field_name`,
  `old_value → new_value`, the first 8 characters of `user_id`, and the date. It shows
  `No changes recorded yet.` or the fetch error. Entries are keyed to the receipt that produced
  them, so a previous receipt's history never flashes while the next one loads.

**Draft persistence and navigation guards:** the draft is kept per receipt in the receipt
store and mirrored to `localStorage`, so an accidental refresh restores edits. A dirty draft
(`draftSignature(draft) !== draftSignature(draftBaseline)`) arms React Router's `useBlocker` and
`beforeunload`. The blocker renders a modal `role="alertdialog" aria-modal="true"` —
`Leave without saving?` / `Your corrections on this receipt will be lost.` — with `Stay`
(autofocused) and `Leave`. `Escape` while it is open resets the blocker.

**ReceiptCanvas payload and bounding boxes** (`frontend/src/components/ReceiptCanvas.tsx`):

* Props: `clientId`, `receiptId`, `fields: FieldProvenance[]`, `lineItems: ReceiptLineItem[]`,
  `tokens: OcrToken[]`, `activeField`, `mismatchFields: string[]`, `processingError`, and the
  lifted zoom state (`scale`, `setScale`, `onZoomIn`, `onZoomOut`, `onReset`).
* The image is fetched from `receiptImageUrl(clientId, receiptId)` with `X-Accountant-Id`,
  converted to an object URL, and revoked on cleanup. Failure renders `Image unavailable` plus
  the HTTP error and, when present, `processingError`.
* Encoding: each bbox is `[x_min, y_min, x_max, y_max]` normalized to `0..1`. It is scaled by
  1000 into an SVG `viewBox="0 0 1000 1000"` with `preserveAspectRatio="none"` stretched over
  the image, so coordinates remain valid at any rendered size. Bboxes with fewer than four
  finite values or zero area are skipped. The overlay is `aria-hidden`.
* The hover tooltip matches the box to the OCR token with the highest intersection-over-union
  **strictly greater than `0.25`**, and prints `{token.text ?? field name} (Conf: {x}%)` using
  the token's confidence when a token matched, otherwise the provenance confidence. The tooltip
  is non-interactive.
* Box styles, in precedence order:
  * active (focused input, or `line_items[i]` for the focused row): teal `#14B8A6`, fill
    `rgba(20,184,166,0.15)`, 2px.
  * math mismatch (`grand_total`, `subtotal`, `tax_amount` while the audit fails): red
    `#EF4444`, fill `rgba(239,68,68,0.10)`, 2px.
  * provenance confidence `< 0.8`: amber `#F59E0B`, fill `rgba(245,158,11,0.10)`, 1px, dashed
    `4`.
  * idle: stroke `rgba(100,116,139,0.55)`, transparent fill, 1px.
* Zoom: buttons `−` / percentage / `+` / `Reset`, plus `[` / `]` / `R`. Wheel zoom is a
  non-passive listener that zooms around the cursor; it needs no modifier. Drag pans with
  pointer capture. Bounds `0.2`–`8`, step `1.25`.

**Save payload:** `PUT /api/v1/clients/{clientId}/receipts/{receiptId}` carries the eight
header strings plus the full line-item array. The server replaces the line set (re-sequencing
`line_index` 0..n-1), recomputes `math_discrepancy`, strips and re-adds `MATH_MISMATCH_DELTA_*`,
sets `STATUS_VERIFIED` with `verified_by`/`verified_at`, classifies expense categories, and
writes one audit row per changed field. The UI does not optimistically mark a receipt verified;
it navigates only after the response.

### 4. `SCR-04`: Authenticated Capture (`/upload`)

An accountant capture page, not a public SME-owner link: it renders inside `AppShell` behind
the root `AccountantGate`, and uploads into the currently selected client workspace.

* **Layout:** single column, `mx-auto max-w-2xl space-y-6 p-6`; the two capture targets sit in
  `grid gap-3 sm:grid-cols-2`.
* **Header:** `Upload receipts` and `Workspace: {business_name}`, or `Selected client` when
  the client list has not loaded, or `No client selected`.
* **No client selected:** a centred card states `Select a client workspace first`, explains
  that receipts are uploaded into the selected client, and links to `/clients` via
  **Choose a client**; the page does not silently create a workspace.
* **Controls:** two styled `<label>` wrappers around visually hidden file inputs, each 44px
  tall (`h-11`):
  * **Take photo** — `accept="image/jpeg,image/png,image/heic,application/pdf"`,
    `capture="environment"`.
  * **Choose files** — `multiple`, `accept="image/jpeg,image/png,image/heic,application/pdf"`.
* **Stated limits:** `JPEG, PNG, HEIC or PDF. Up to 50 files per batch, 15 MiB each, 50 MiB
  per batch. Processing continues in the background.`
* **No viewfinder, shutter button, or bottom sheet.** The mobile camera is delegated to the
  OS/browser through the `capture` attribute; the page itself only shows the two targets.
* **Feedback:** a single multipart `POST …/receipts/upload` returns `202 Accepted` with a
  `batch_id` and per-file results. The `role="status" aria-live="polite"` region reports
  `Uploading…`, then `{n} file(s) accepted.`; a batch-level rejection
  (too many files, oversized file/batch, unsupported type, or malformed request) arrives as one
  `ApiError` and renders as `Batch rejected: {detail}`, with nothing persisted. Below it, a list
  shows each result's filename and **raw status enum** (`PENDING_UPLOAD`, `UPLOADED`, …) plus
  any per-file `error`; these are not translated into friendly labels.
* **Duplicates:** the backend keys a duplicate on the same sanitized filename and byte size in
  the same workspace and returns the existing receipt (same `id`, no second file, no
  reprocessing). Duplicates inside one request are deduplicated with a `seen` set. Because the
  file inputs are remounted via `inputKey` after every attempt, re-selecting the *same* file
  does fire `onChange` again and reaches that duplicate path.
* **After upload:** a `← Inbox` link. The upload happens immediately on selection; there is
  no staged-review or submit step on this page.

### 5. `SCR-05`: Export Hub (`/clients/:clientId/exports`)

* **Month picker:** `type="month"`; clearing it exports all verified receipts, and the input's
  title states that.
* **Card A — Accounting CSV:** purchase-journal import for AutoCount / SQL Account, with the
  column list shown inline.
* **Card B — MyInvois JSON:** labelled **Draft MyInvois envelope — validate before
  submission.** It is a UBL-shaped draft, not an LHDN-validated or submitted document.
* **Download both:** `Download Both Files (1-Click)` requests the CSV and the JSON together;
  the per-card buttons download each alone.
* **Mark exported:** separate, explicit button. It calls `POST …/exports/mark`; downloading
  never changes status. The page says so directly beneath the buttons.
* **States:** loading, error banner, success message naming what was downloaded.

### 6. `SCR-06`: Spend Dashboard (`/clients/:clientId/dashboard`)

* **Month picker:** `type="month"`, defaults to the current month; changing it re-requests
  `GET …/dashboard/summary?month=YYYY-MM`, and the response is tagged with its request key so a
  stale month never renders.
* **Total spend:** verified receipts only (`STATUS_AUTO_VERIFIED`, `STATUS_VERIFIED`,
  `STATUS_EXPORTED`); unreviewed receipts are excluded. Rendered as the raw decimal string, with
  no `RM` prefix added by the page.
* **Top suppliers:** up to five, spend-descending, in a table with Supplier / Receipts / Spend
  columns; zero rows render `No supplier totals for this month.`
* **Spend by category:** horizontal bars over the fixed taxonomy `F&B`, `HARDWARE`,
  `WORKSHOP`, `RETAIL`, `OTHER`; all five always render, including zeros, and each bar is a
  `role="img"` element labelled `{category}: {total}`. A note states `Pre-tax line totals;
  document tax is excluded.`
* **States:** loading skeleton (four rows), error with retry, empty
  (`No dashboard data` / `Verified receipts for this month will appear here.`), populated.

---

## 4.4 Form Control & Accessibility Standards

Implemented practices, all traceable to the source:

* **Skip link:** `App.tsx` renders `Skip to content` as the first focusable element, targeting
  `#main-content` (`tabIndex={-1}`).
* **Visible focus:** most action buttons, inputs, filter tabs, and the skip link use
  `focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1
  focus-visible:outline-none` (the reject strip uses an inset ring). The `/upload` page's
  `sr-only` file inputs sit inside labels styled with `focus-within:` rings. One exception: the
  review header's `← Inbox` link signals focus with an underline rather than a ring. Rings are a
  per-component convention, not a shared focus-management layer.
* **Field validation:** `AccountantGate` and `ClientForm` render the error beneath the field
  with a stable id and set `aria-invalid` plus `aria-describedby` on the input; blocking errors
  use `role="alert"`. **This pattern is not applied to every Review input** — the review header
  fields rely on the aggregate `Fix {field} before verifying.` message and the `MathBanner`
  rather than per-field `aria-invalid`.
* **Labels:** `LabelledInput` binds `<label htmlFor>` to an input `id` (`header-field-{field}`);
  totals labels wrap their inputs; line-item inputs use `aria-label` such as
  `Line 2 quantity`; icon-only buttons (zoom, delete, dropzone remove) carry `aria-label`.
* **Touch targets:** primary actions use `h-11` (44px). Inbox rows are 40px
  (`h-dense-row`); the row-level `Review` button is 32px (`h-8`). The line-item delete/add and
  zoom buttons are `h-11`; the line-item *text inputs* are denser at `h-9` (36px), and the
  review header inputs are `h-9` as well. Pagination controls use `min-h-11`; filter buttons
  use `min-h-10` (40px).
* **Status never by colour alone:** pills pair colour with a glyph and visible text and expose
  `data-status`; mismatch, low-confidence, and error pills also carry a `title` (see the
  matrix). Thumbnails fall back to a labelled placeholder.
* **Live regions:** `MathBanner` and the `/upload` status region use
  `role="status" aria-live="polite"`; the inbox upload feedback region is `aria-live="polite"`;
  the Review loading shell and skeleton use `role="status" aria-busy="true"`; the invalid-draft
  message is `role="status"`; error banners use `role="alert"`.
* **Dialogs:** the reject strip is `role="alertdialog"` and takes focus; the leave dialog is
  `role="alertdialog" aria-modal="true"` with `aria-labelledby` and an autofocused `Stay`.
* **Structure:** the inbox table has `aria-label="Receipt inbox"` and `sr-only` header text for
  the thumbnail and action columns; the filter bar is a `<div role="group"
  aria-label="Status filter">` with `aria-pressed` buttons; decorative glyphs are `aria-hidden`.
* **Images:** receipt thumbnails use the filename as `alt`; the review image uses
  `alt="Scanned receipt for review"`; failed thumbnails render a labelled placeholder.
* **Reduced motion:** honoured globally (see §4.2).

**No formal accessibility audit has been performed, and this repository makes no WCAG
conformance or certification claim.** The practices above are WCAG 2.2 AA-aligned where they
are implemented; a real audit would be a prerequisite for any conformance claim.

---

## 4.5 Component Props Contracts (TypeScript)

The wire types are defined in `frontend/src/types/receipt.ts`; the aggregate/audit types live
in `frontend/src/api/client.ts`. The shapes below are quoted from those files. Money and
decimal quantities are **strings** on the wire (`"99.50"`), bounding boxes are four-element
normalized arrays, and dates are ISO `YYYY-MM-DD`.

```typescript
// frontend/src/types/receipt.ts
export type ReceiptStatus =
  | 'PENDING_UPLOAD' | 'UPLOADED'
  | 'PROCESSING_OCR' | 'PROCESSING_LLM' | 'VALIDATING_MATH'
  | 'STATUS_NEEDS_REVIEW' | 'STATUS_AUTO_VERIFIED'
  | 'STATUS_VERIFIED' | 'STATUS_EXPORTED' | 'STATUS_REJECTED'
  | 'ERR_UNREADABLE' | 'ERR_TIMEOUT' | 'ERR_FILE_CORRUPT' | 'ERR_EXTRACTION';

export type ReceiptListStatus =
  | 'ALL' | 'NEEDS_REVIEW' | 'VERIFIED' | 'EXPORTED' | 'REJECTED';

export interface ReceiptListItem {
  id: string;
  filename: string;
  merchant_name: string | null;
  invoice_date: string | null;
  subtotal: string | null;
  tax_amount: string | null;
  grand_total: string | null;
  status: ReceiptStatus;
  validation_flags: string[];
  overall_confidence: number;
  math_discrepancy: string;
  image_url: string;
  line_item_count: number;
}

export interface ReceiptListResponse {
  total: number;
  limit: number;
  offset: number;
  items: ReceiptListItem[];
}

export interface FieldProvenance {
  name: string;
  confidence: number;
  bbox: number[] | null; // [x_min, y_min, x_max, y_max], normalized 0..1
}

export interface OcrToken {
  text: string;
  confidence: number;
  bbox: number[] | null;
  line_num: number;
}

export interface ReceiptLineItem {
  id: string;
  line_index: number;
  description: string;
  quantity: string;
  unit_price: string;
  line_total: string;
  confidence: number;
  bbox: number[] | null;
}

export interface ReceiptDetail {
  id: string;
  client_id: string;
  filename: string;
  status: ReceiptStatus;
  processing_error: string | null;
  image_url: string;
  merchant_name: string | null;
  merchant_brn: string | null;
  merchant_sst: string | null;
  invoice_date: string | null;
  invoice_number: string | null;
  subtotal: string | null;
  tax_amount: string | null;
  grand_total: string | null;
  math_discrepancy: string;
  overall_confidence: number;
  validation_flags: string[];
  created_at: string;
  verified_at: string | null;
  fields: FieldProvenance[];
  line_items: ReceiptLineItem[];
  ocr_tokens: OcrToken[];
}

export interface ReceiptUpdateRequest {
  merchant_name: string | null;
  merchant_brn: string | null;
  merchant_sst: string | null;
  invoice_date: string | null;
  invoice_number: string | null;
  subtotal: string | null;
  tax_amount: string | null;
  grand_total: string | null;
  line_items: ReceiptUpdateLineItem[];
}

export interface ReceiptUpdateLineItem {
  description: string;
  quantity: string;
  unit_price: string;
  line_total: string;
}

export interface ReceiptUpdateResponse {
  id: string;
  status: ReceiptStatus;
  updated_at: string;
  verified_by: string;
  math_discrepancy: string;
}

export interface ReceiptUploadResult {
  id: string;
  filename: string;
  status: ReceiptStatus;
  error?: string;
}

export interface ReceiptUploadResponse {
  batch_id: string;
  total_received: number;
  receipts: ReceiptUploadResult[];
}

export interface DraftLineItem {
  key: string; // local React identity only, never sent
  description: string;
  quantity: string;
  unit_price: string;
  line_total: string;
}

export interface ReceiptDraft {
  merchant_name: string;
  merchant_brn: string;
  merchant_sst: string;
  invoice_date: string;
  invoice_number: string;
  subtotal: string;
  tax_amount: string;
  grand_total: string;
  line_items: DraftLineItem[];
}

export type DraftHeaderField =
  | 'merchant_name' | 'merchant_brn' | 'merchant_sst' | 'invoice_date'
  | 'invoice_number' | 'subtotal' | 'tax_amount' | 'grand_total';

export type DraftLineField = 'description' | 'quantity' | 'unit_price' | 'line_total';
```

```typescript
// frontend/src/api/client.ts (aggregates and audit log)
export interface ClientSummary extends Client {
  unreviewed_count: number;
  verified_count: number;
}

export interface TopSupplier {
  supplier_name: string;
  total_spend: string;
  receipt_count: number;
}

export interface CategoryBreakdown {
  category: string;
  total_spend: string;
}

export interface DashboardSummary {
  month: string;
  total_spend: string;
  top_suppliers: TopSupplier[];
  category_breakdown: CategoryBreakdown[];
}

export interface ReceiptAuditEntry {
  id: string;           // UUID
  user_id: string;
  field_name: string;
  old_value: string | null;
  new_value: string | null;
  created_at: string;
}

export interface ReceiptAuditResponse {
  items: ReceiptAuditEntry[];
}
```

There is **no per-field wrapper envelope**: provenance is a flat
`fields: FieldProvenance[]`, and the merchant identifiers are two separate strings,
`merchant_brn` and `merchant_sst`. `ReceiptCanvas` consumes those flat arrays directly:

```typescript
interface ReceiptCanvasProps {
  clientId: string;
  receiptId: string;
  fields: FieldProvenance[];
  lineItems: ReceiptLineItem[];
  tokens: OcrToken[];
  activeField: string | null;
  onHoverToken: (token: OcrToken | null) => void;
  mismatchFields: string[];
  processingError: string | null;
  scale: number;
  setScale: Dispatch<SetStateAction<number>>;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
}
```

**API/UI discrepancy — expense category.** The backend Pydantic model
`ReceiptDetailLineItem` (`backend/app/schemas/receipt.py`) includes
`expense_category: str = "OTHER"`, populated by `backend/app/services/classifier.py` and
returned by the receipt detail route; the dashboard groups by it. The frontend
`ReceiptLineItem` above omits the field, `LineItemsEditor` renders no category column, and
`ReceiptUpdateLineItem` sends no category — the server re-derives it on save. §4.6 records this
as an unimplemented UI requirement.

---

## 4.6 Documented boundaries

* No bulk select, bulk verify, or bulk reject; each receipt transition is individually audited.
* No expense-category control in the review editor. The backend stores, classifies, returns,
  and aggregates `expense_category`, but the current frontend type and line-item table do not
  expose it; the server re-classifies from the description on save.
* No row-selection checkboxes in the inbox.
* No dark mode, theming, or design-token export package.
* No formal WCAG certification or third-party accessibility audit.
* No PDF-page navigation: only the first page of a PDF is processed and displayed.
* No offline mode; every screen requires the local API.
* No public or unauthenticated capture flow; `/upload` sits behind `AccountantGate`.
* No camera viewfinder or in-page shutter: mobile capture delegates to the OS via the
  `capture="environment"` file input.
