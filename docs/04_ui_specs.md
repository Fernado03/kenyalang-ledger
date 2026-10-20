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

## 4.1 Visual System & Design Tokens

The interface is a **ruled ledger**. Warm paper surfaces, 1px rules, serif page titles,
monospaced figures, and square ink stamps carry the hierarchy. There are no cards, no content
shadows, no gradients, no glass effects, and no pill-shaped chrome. A surface is either the
page (`canvas`), a form or reading pane (`surface`), or a recessed band (`surface-subtle`);
separation comes from rules, not elevation. Status is never encoded by tinting a whole row — it
is a stamp (§4.3).

### Color tokens (`frontend/tailwind.config.js`)

| Token | Value | Used for |
|---|---|---|
| `canvas` | `#F6F1E7` | App background, table-header band |
| `surface` | `#FBF8F1` | Form panes, sticky headers, dialogs, buttons |
| `surface-subtle` | `#EFE8DA` | Desktop rail, neutral stamps, hover fills, disabled fields |
| `border` | `#D9D2C3` | Hairline rules, table cell rules, page-header rule |
| `border-strong` | `#8A8274` | Input borders, secondary buttons, double total rule |
| `border-focus` | `#0B3F3A` | Declared token only; the live focus outline is `brand-700` (§4.4) |
| `text-primary` | `#171A18` | Titles and values |
| `text-secondary` | `#3F4742` | Body copy, table cells |
| `text-muted` | `#5F665F` | Eyebrows, labels, captions, placeholders |
| `text-inverse` | `#F6F1E7` | Text on the charcoal receipt canvas |
| `brand-50` | `#E7F0EB` | Active-row tint, light text on dark |
| `brand-100` | `#DCEBE5` | Secondary text on `brand-950`, text selection |
| `brand-500` | `#147A6C` | Active OCR box stroke |
| `brand-700` | `#0E5A50` | Global focus outline, primary-button hover |
| `brand-900` | `#0B3F3A` | Primary buttons, active rail mark |
| `brand-950` | `#072A26` | Session-gate panel |
| `verified.bg` / `.border` / `.text` | `#E7EFE5` / `#9DB79F` / `#2D5334` | Verified stamp |
| `warning.bg` / `.border` / `.text` | `#F6E9D2` / `#C9A05A` / `#7A4E0A` | Needs review, low-confidence fields |
| `mismatch.bg` / `.border` / `.text` | `#F6E2DC` / `#C58375` / `#8C2F22` | Rejected/error stamps, reject band, error text |
| `charcoal` / `charcoal-raised` / `charcoal-rule` | `#20241F` / `#2A2F29` / `#3A4038` | Receipt canvas / toolbar / toolbar rules |

Notes:

* `text-muted` is a distinct mid-grey, not a darkened `text-secondary`. It is used on `canvas`
  and `surface`; no contrast conformance is claimed (§4.4).
* Charcoal is scoped to the receipt viewer. It is not a dark theme.
* No token is computed at runtime; every value above is a literal hex string.

### Typography

```text
sans   "Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system,
       "Helvetica Neue", Arial, sans-serif
serif  "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Palatino,
       Georgia, "Times New Roman", serif
mono   "Cascadia Mono", "SFMono-Regular", ui-monospace, Consolas,
       "Liberation Mono", monospace
```

`font-mono-numbers` is the mono stack plus `font-variant-numeric: tabular-nums lining-nums`.
Every money amount, date, ID, count, percentage, and column label uses it.

| Token | Size / line | Use |
|---|---|---|
| `micro` | 10 / 12 | Stamps, eyebrows, field labels, table headers, rail tab labels |
| `label` | 11 / 14 | Metadata, small buttons, counts, errors |
| `ui` | 13 / 18 | Controls, table body, UI copy |
| `body` | 14 / 21 | Prose, page meta, dialog copy |
| `title` | 20 / 24 | Section titles |
| `display` | 34 / 38 | Page titles |
| `display-lg` | 56 / 52 | Declared in the scale; unused by the six screens |

Serif headings are weight 400, never bold: page titles use `display` with `-0.015em` tracking,
section titles use `title` with `-0.01em`. Eyebrows are 10px uppercase at `0.14em`; section and
field labels at `0.12em`; stamps at `0.08em`. Body copy is sans at 14px.

### Shape and surfaces

* Radii: 2px on controls and panels (`rounded-sm`); stamps and thumbnails use 1px. No circular
  chrome is used anywhere.
* `shadow-card` is `none`; the only shadow in the system is `shadow-modal`
  (`0 24px 80px rgba(23,26,24,.22), 0 2px 8px rgba(23,26,24,.12)`) on native dialogs.
* `.rule-total` is a 3px double `#8A8274` rule, used above grand totals and export/pagination
  footers.
* `.data-table` is a full-width collapsed table: 1px cell rules, 10px uppercase mono headers,
  13px secondary body text, 12px horizontal and 8–10px vertical cell padding, and a `surface`
  hover fill.
* The content measure is `max-w-shell` = 1240px. `.page-shell` supplies
  `mx-auto w-full max-w-shell px-5 py-7 sm:px-8 lg:px-10 lg:py-10`; every page starts with it.

### Shared components

* **`Icon`** — one inline SVG set, 24px viewBox, `stroke="currentColor"`, 1.6 stroke width,
  round caps and joins. Names: `clients`, `inbox`, `dashboard`, `exports`, `camera`, `upload`,
  `file`, `download`, `plus`, `minus`, `reset`, `close`, `check`, `alert`, `clock`,
  `chevron-right`, `arrow-left`, `sign-out`. Icons are `aria-hidden` unless a `title` is passed.
* **`BrandMark`** — a 32px square tile (4px radius, `brand-900` fill) carrying the paper-tinted
  hornbill mark as a filled path. No image asset or gradient is used.
* **`PageHeader`** — `eyebrow`, `title`, `meta`, optional `actions`. It renders a bottom rule,
  a mono uppercase eyebrow, a serif `display` title, a secondary-colour meta block, and a
  right-aligned action group that wraps under the title on narrow screens. At `lg` the header is
  a 12-column grid with the title spanning 7 and actions spanning 5.

### Application shell (`AppShell.tsx`)

* **Desktop (`lg`+):** a fixed 72px left icon rail on `surface-subtle` with a right rule.
  The brand link is 64px tall with a bottom rule; each destination is a 56px item with a 20px
  icon above a 10px uppercase label. Active items get a 2px `brand-900` left border, `surface`
  fill, and primary text; inactive items are muted. The rail's bottom block holds the
  accountant's initials in a 32px square (first two characters, full UUID in `title`) and a
  40px sign-out icon button labelled `Sign out`.
* **Mobile (`<lg`):** a sticky 56px top bar with the 26px brand mark, the serif wordmark
  `Kenyalang Ledger`, and a 40px sign-out button. A persistent bottom tab bar repeats the same
  five destinations at `min-h-14` with 10px labels; the active tab is `brand-900` with a 2px
  top indicator, and the bar pads for the safe-area inset.
* **Destinations:** Clients, Inbox, Dashboard, Exports, Upload. Without a selected workspace,
  Inbox, Dashboard, and Exports render as non-interactive `<span aria-disabled="true">` items at
  35% opacity with the tooltip `Select a workspace first`. Clients and Upload are always live.
  Inbox also stays active on the review route.
* **Content offset:** `lg:pl-[72px]` on the main region; mobile pages reserve
  `calc(3.5rem + env(safe-area-inset-bottom))` at the bottom so the tab bar never covers content.
* Navigation exists only in the shell. Page headers add contextual links (`Clients`, `Inbox`)
  and never repeat the primary navigation.

---

## 4.2 Motion Architecture & Micro-Interactions

There is no animation library. Motion is limited to feedback:

* **Controls:** 100ms `ease-out` transitions on colour, background, border, and transform.
  `.btn` also presses down 1px (`active:translate-y-px`). This is a press acknowledgement, not
  a lift or elevation change.
* **Hover:** background and border colour only. Rows, tabs, and buttons never move, scale, or
  gain shadow.
* **Dialogs:** the native `<dialog>` fades in over 140ms (`dialog-in`, opacity only); its
  backdrop is `rgb(23 26 24 / 0.58)`. There is no scale or slide.
* **Page changes:** none. React Router swaps routes with no entrance, stagger, or parallax;
  lazy routes show the static skeleton fallback (`role="status" aria-busy="true"`).
* **Review save:** no transition. After a successful save-and-next, the next receipt replaces
  the current one and a `VERIFIED` stamp with a 12px check flashes in the action bar for 1200ms
  (or until navigation). The flash is a confirmation, not an entrance animation.
* **Reduced motion:** a global `prefers-reduced-motion: reduce` rule collapses all animation
  and transition durations to `0.01ms` and sets `scroll-behavior: auto`. The dialog then opens
  without a fade, and the verified flash is effectively instantaneous.

### Receipt canvas transform

Pan and zoom apply
`transform: translate3d(x, y, 0) scale(z)` with `transform-origin: 0 0`, and the image layer is
memoized so dragging does not re-render it. The stage has `touch-action: none` and an inline
`transition: none`, so pointer movement is 1:1 with the image at all times. Wheel zoom is
anchored at the cursor; the toolbar's zoom buttons change scale only, with the stage transformed
from its top-left origin. Scale is clamped to `0.2–8` and steps by `1.25`.

### Keyboard workflow (`frontend/src/lib/reviewShortcuts.ts` + `ReviewPage.tsx`)

The pure resolver owns the first four bindings; the page's window listener adds zoom keys after
it. `ReviewPage.tsx` also lets the native modal block every shortcut while the leave dialog is
open.

| Key | Behaviour |
|---|---|
| `Esc` | Closes the reject band if it is open; otherwise blurs the focused field; otherwise opens the reject band |
| `Ctrl/⌘ + Enter` | Save and move to the next receipt (ignored while a field has focus) |
| `Alt + A` | Append a line item |
| `Alt + Backspace` | Delete the focused line item, including the last one |
| `[` / `]` | Zoom out / in (×1.25 per press, clamped `0.2–8`), ignored inside fields |
| `R` | Reset zoom to 100% (ignored inside fields) |

Single-key shortcuts (`[`, `]`, `R`) are ignored when focus is in an `input`, `textarea`,
`select`, or `contenteditable`, and when any modifier is held, so typing in a field never
triggers them. `[` and `]` are resolved only after the shortcut lookup. `R` resets scale to 100%
only; the toolbar's **Reset** (`Reset zoom and center`) resets scale and returns the pan offset to
0. While the reject band is open, `Escape` cancels it; while the leave dialog is open, the native
`<dialog>` owns `Escape`.

### Reconciliation and status copy

The audit is unchanged and lives in `frontend/src/lib/audit.ts`:

* It compares the printed line totals plus tax against the grand total — never
  `qty × unit_price` as the total.
* `|line_total sum + tax − grand_total| ≤ RM 0.02` counts as reconciled (`TOLERANCE_CENTS = 2`).
  RM 0.01 matches; RM 0.03 does not.
* A negative delta is retained for display (`−RM x.xx`); magnitude is used for the tolerance.
* A draft is invalid when a money field cannot be parsed, a quantity is not a positive number,
  or `qty × unit_price` differs from the line total by more than RM 2.00 (rounding headroom;
  `TOLERANCE_CENTS * 100n` = 200 cents).
* `missingSstOnRegisteredMerchant` is true when tax is exactly zero while `merchant_sst` matches
  the LHDN shape (for example `W10-1808-32000018`). It is a warning stamp, not a blocker.

All status text is English: `Verified`, `Exported`, `Rejected`, `Needs review`, `Δ RM x.xx`,
`OCR check n%`, `Processing`, `Unreadable`, `Timed out`, `Extraction failed`, `File error`.
Money is `RM 1234.50` (no thousands separator); dates are `DD/MM/YYYY`; an unrecognised status
falls back to the `File error` stamp rather than exposing a raw enum.

---

## 4.3 Screen-by-Screen Component Specifications

### 1. `SCR-01`: Client Workspace Switcher (`/clients`)

**Header.** Eyebrow `WORKSPACE INDEX`; title `Clients`; meta `Loading client workspaces.`,
`No client workspaces yet.`, or `{n} client workspace(s) · Select a client to open its receipt
inbox.` Actions: `Add client` (primary, `plus` icon) when the form is closed, `Close` (ghost)
when it is open.

**Layout.** At `sm`+, a ruled table: Client name, Registration, SST, Unreviewed, Verified,
Action. The industry category is folded into the name cell as a muted subline — there is no
separate column. Registration and SST are mono and print an em dash when absent. Counts are
right-aligned mono. Each row is 52px and ends in an `Open` link-button (chevron icon, 44px hit
area). Below `sm`, the same data renders as a stacked list: name plus industry, a two-column
definition list (Registration, SST, Unreviewed, Verified), and a full-width `Open` button. The
whole row is not clickable; the explicit control is the target.

**States.** Loading shows three skeleton table rows (and three stacked skeletons below `sm`). An
error shows a `role="alert"` strip with `Retry`. Empty, with the form closed, shows
`Add your first client`, `Create a client workspace to start uploading receipts.`, and an
`Add your first client` primary button; with the form open, the form itself. When clients exist
and the form is open, it sits above the table. The form is a `surface` block with a 2px
`brand-900` top rule.

**Client form (`ClientForm.tsx`).** Heading `New client`. Fields: Business name (required),
Registration number, SST number, Industry category. Labels are mono uppercase; inputs are 44px.
Validation is native-free (`noValidate`): an empty name produces `Business name is required.`,
sets `aria-invalid`, and is linked by `aria-describedby`. The submit label is `Add client`
(`Create client` in the empty state) and swaps to `Saving…` while posting; `Cancel` closes
without saving. There is no edit variant — clients are create-only in this UI.

### 2. `SCR-02`: Batch Inbox & Upload Dropzone (`/clients/:clientId/inbox`)

**Header.** Eyebrow `WORKSPACE · {registration_number ?? business_name ?? CLIENT}`; title
`Inbox`; meta shows the business name and, when the workspace has receipts, the mono range
`receipts {first}–{last} of {total}`. Actions: `Clients` (ghost, `arrow-left`) and `Capture`
(secondary, `camera`).

**Upload band.** A full-width band with top and bottom rules (minimum 52px,
`aria-label="Upload receipts"`) above the filters: `Drop receipts here, or click to browse. Max
50 files per batch.` and a `Browse` secondary button. Dragging switches the band to a dashed
`brand-700` border on `brand-100`. The hidden input accepts `image/jpeg`, `image/png`,
`image/heic`, and `.pdf`, and is disabled while a batch uploads. Uploads start immediately on
selection or drop. A polite live region reports `Uploading…`, then
`{n} file(s) queued for processing.` (singular `1 file`), lists per-file failures as
`{filename}: {error}`, or shows `Batch rejected: {message}`. Results here are a sentence, not a
stamp list — the stamped per-file result list belongs to `/upload`.

**Filters.** Five underlined tabs: `All`, `Needs review`, `Verified`, `Exported`, `Rejected`.
Each is a 40px button with `aria-pressed`; the active tab gets a 2px `brand-900` underline and
semibold text. The group is labelled `Status filter` and scrolls horizontally at 320px.

**Table.** One DOM for both breakpoints. The `<table>` keeps explicit `table`/`rowgroup`/`row`/
`cell` ARIA roles and switches from `block` to `table` at `sm`:

* **`sm`+ columns:** Preview (44px column holding the 32px thumbnail), Supplier, Date (96px),
  Items (64px), Grand total (right, 128px), Status (128px), Action (96px). Headers are sticky at
  `top-14 lg:top-0` on `canvas`.
* **Below `sm`:** each row becomes a three-column grid — `32px | minmax(0,1fr) | auto` — with
  the thumbnail spanning two rows; supplier and flags, date, total, stamp, and a full-width
  `Open` button follow. The item-count cell is hidden below `sm`.
* **Rows:** `surface` hover; a 2px left border in `warning-border` for needs-review rows and in
  `mismatch-border` for error rows. Cells use 10px vertical padding around a 22px stamp, so
  `sm` rows are ≈44px. Mobile stacked rows use 12px vertical padding.
* **Thumbnail:** 32×32 (`h-8 w-8`), 1px radius and border, `object-cover`. It is fetched lazily
  through an `IntersectionObserver` as an authenticated blob and revoked on unmount. Alt text is
  the filename; while absent, a `role="img"` placeholder is labelled `No preview for {filename}`.
* **Supplier cell:** `merchant_name ?? filename`, with humanized validation flags beneath in
  `warning` text joined by ` · `. Flags are humanized, never raw: `MATH_MISMATCH_DELTA_0.05` →
  `Math mismatch: Δ RM 0.05`; `LOW_CONFIDENCE_GRAND_TOTAL` → `Low OCR confidence: grand total`;
  `MISSING_CRITICAL_EVIDENCE_MERCHANT_NAME` → `No OCR evidence: merchant name`. Known flags
  (missing merchant name/date, invalid grand total, future date, date older than a year, missing
  subtotal, missing SST on a registered merchant) have explicit sentences; anything else becomes
  underscores-to-spaces.
* **Money/date:** date via `formatDate` (`-` when absent); total split into a small currency
  prefix (`RM`) in muted label type and a mono amount.
* **Action:** `Open` (44px tall, full-width below `sm`) navigates to the review route and is
  disabled for processing rows. The whole row is also clickable with a pointer (and shows a
  pointer cursor) unless the receipt is processing; thumbnail and action cells stop propagation.
  There is no bulk selection.

**Pagination.** 50 per page. A `.rule-total` footer shows `Showing {a}–{b} of {total}` in a
`role="status"` region with `Previous` / `Next` 36px buttons, disabled at the ends. No page
numbers.

**Polling and states.** The list refetches every 3s while any row is processing. Loading is five
skeleton rows. Error is a `role="alert"` strip with `Retry`. Empty is `No receipts yet — drop a
batch above.` with the hint `JPG, PNG, HEIC or PDF, up to 50 files per batch.` A failed upload
never removes existing rows.

**Status stamps (`StatusPill.tsx`).** `.stamp` is a 22px inline-flex box, 1px radius, 1px
border, 6px horizontal padding, mono 10px uppercase at `0.08em`. Icons are `aria-hidden`; the
text carries meaning. Variants are chosen in this exact precedence:

| Condition (in order) | Tokens | Text | Tooltip (`title`) |
|---|---|---|---|
| `STATUS_VERIFIED`, `STATUS_AUTO_VERIFIED` | `verified.*` | `Verified` | — |
| `STATUS_EXPORTED` | `surface-subtle` / `border-strong` / `brand-900` | `Exported` | — |
| `STATUS_REJECTED` | `mismatch.*` | `Rejected` | — |
| `STATUS_NEEDS_REVIEW` with a `MATH_MISMATCH_DELTA_` flag | `mismatch.*` | `Δ RM {suffix}` | `Math mismatch: Δ RM {suffix}` |
| `STATUS_NEEDS_REVIEW` with known confidence `< 0.8` | `warning.*` | `OCR check {n}%` | `Low OCR confidence` |
| `STATUS_NEEDS_REVIEW`, otherwise | `warning.*` | `Needs review` | — |
| `PENDING_UPLOAD`, `UPLOADED`, `PROCESSING_OCR`, `PROCESSING_LLM`, `VALIDATING_MATH` | `surface-subtle` / `border` / `text-secondary` | `Processing` | — |
| `ERR_UNREADABLE` | `mismatch.*` | `Unreadable` | `processingError ?? 'Unreadable'` |
| `ERR_TIMEOUT` | `mismatch.*` | `Timed out` | `processingError ?? 'Timed out'` |
| `ERR_EXTRACTION` | `mismatch.*` | `Extraction failed` | `processingError ?? 'Extraction failed'` |
| Any other status (`ERR_FILE_CORRUPT`, future enums) | `mismatch.*` | `File error` | `processingError ?? 'File error'` |

The score is the receipt's confidence only when it is defined, finite, and `>= 0`; otherwise it
is `null` and the pill falls through to `Needs review`. `0 <= score < 0.8` selects the
low-confidence variant. `formatConfidence` clamps at `1` and rounds, so `0.799` prints `80%`,
`0.64` prints `64%`, and a value above `1` prints `100%`. The suffix is the flag with
`MATH_MISMATCH_DELTA_` stripped.

Call sites differ: `/upload` passes the per-file `processingError`, so error stamps carry the
backend message in their tooltip; Inbox and Review pass only status, flags, and confidence, so
error stamps use their label as the tooltip. An unrecognised status falls through to the
`File error` stamp, so an unexpected enum never leaks as raw text.

### 3. `SCR-03`: Split-Screen Review Console (`/clients/:clientId/review/:receiptId`)

**Frame.** At `lg` the console is `lg:h-dvh lg:grid-cols-[46fr_54fr]` inside the shell: receipt
canvas left, scrolling form right, separated by a rule. Below `lg` the panes stack — the canvas
is `40dvh` above a flowing form. The form pane is `surface` and scrolls independently at `lg`.
There is no `PageHeader`; the action bar is the header.

**Loading/error.** Loading reuses the same 46/54 grid with a canvas skeleton and a form skeleton
(`role="status" aria-busy="true"`). A missing receipt renders a centred `Receipt unavailable`
block with a `mismatch` left rule, the error message, and `Back to inbox`.

**Action bar.** Sticky at `top-14 lg:top-0`, `surface`, bottom rule. Left: `Inbox`
(`arrow-left`, title `Back to inbox without saving`), a vertical rule, `ID: {first 8}` in mono
(`h1`), and the status stamp. Right: save error text, the `VERIFIED` stamp flash, the invalid
message `Fix {first invalid field} before verifying.` (`role="status"`), `Reject` (secondary,
`Esc` keycap), and `Verify & Next` (primary, `Ctrl/⌘ ↵` keycap). Save is disabled while saving
or while the audit is invalid; labels swap to `Rejecting…` / `Saving…` while a request is in
flight. The reject control opens an inline band, not a dialog.

**Reject band.** A `mismatch` alert band below the action bar with `role="alertdialog"`,
`aria-label="Confirm rejection"`, and `tabIndex={-1}`. Focus moves to the band on open. Copy:
`Reject this receipt? This cannot be undone.` Actions: `Cancel` and `Reject` (danger). `Escape`
cancels and returns focus to the trigger. Confirming calls the reject route and advances to the
next receipt.

**Form sections.** Three numbered sections, each with a mono `section-label` (`01`, `02`, `03`)
and a serif `section-title`:

1. **`01` Supplier & date.** At `sm`+, a two-column grid; Supplier Name spans both columns.
   Fields in order: Supplier Name, Merchant SST, Invoice Date, Invoice Number, Merchant BRN.
   Labels are mono uppercase; inputs are 44px.
2. **`02` Line items.** A horizontally scrollable grid (minimum 32rem) with Description, Qty,
   Unit (RM), Total (RM), and a delete column. Inputs are 34px dense, numeric fields are
   right-aligned mono, and every input has an explicit `aria-label` (`Line 2 description`).
   A server confidence below 0.8 tints the row `warning.bg`, adds a dashed `warning.border`
   underline, and shows an `alert` icon plus the percentage. The focused row is `brand-50`.
   Delete is a 44px icon button (`Remove line 2`); the footer's ghost button reads
   `Add Line (Alt+A)`. A mono `{n} lines` count sits opposite it.
3. **`03` Totals & audit.** A right-aligned column (`max-w-md`) of labelled totals: Subtotal,
   SST (6%), Grand Total. Inputs are `w-36` (144px), right-aligned mono, with an `aria-hidden`
   `RM` prefix; Grand Total prints at 22px above a `.rule-total` double rule. A summary
   definition list shows Line Items Total, Confidence (or `—`), and `Lines + Tax = Total`.

**Math banner (`MathBanner.tsx`).** A cardless strip with a 3px left border and a `Math check`
label, in one `role="status"` / `aria-live="polite"` region. Invalid input: `mismatch` border,
`Invalid amount: Line 2 total, SST` (the invalid field labels joined by `, `). Reconciles with
no SST warning: `verified` border, the breakdown without the audit's internal `Math Matches —`
prefix (`Line items total RM 100.00 + Tax RM 6.00 = Grand Total RM 106.00`). Mismatch: `mismatch`
border, `Math Mismatch: Line items total RM … ≠ Grand Total RM … (Difference: RM 0.03)`. A
zero-tax receipt whose merchant has an SST number switches the strip to `warning` and adds the
stamp `Missing SST on registered merchant`. Unsaved changes add `Unsaved changes`.

**Audit history.** A native `<details>` (`Audit history`) loads on first open, listing
`{field}: {old} → {new}` with the acting accountant's short ID (first 8) and the change date.
It scrolls within `max-h-64`; empty (`No changes recorded yet.`) and error states are one line
each.

**Draft safety.** Edits are mirrored to `localStorage` under
`kenyalang.draft.{receiptId}` and restored on reopen. Leaving with unsaved changes blocks
navigation (`useBlocker`), warns on `beforeunload`, and opens a native `<dialog>`:
`Leave without saving?` / `Your corrections on this receipt will be lost.`, with `Stay` (default)
and `Leave`. It is a modal `alertdialog` labelled by its heading; `Stay` receives initial focus,
`Escape` cancels the navigation, and focus returns to the element that triggered the blocked
navigation. Clicking the backdrop does nothing. The draft is cleared after a successful verify or
reject.

**Receipt canvas.** `charcoal` stage with a 44px `charcoal-raised` toolbar: zoom out, the mono
percentage, zoom in, and `Reset`. Controls are 44px with `charcoal-rule` borders and
`text-inverse` labels; the icon buttons are labelled `Zoom out` / `Zoom in`, and `Reset` is
`Reset zoom and center`. Wheel zoom is cursor-anchored; drag pans with pointer capture.

**Overlay colours** (viewBox `0 0 1000 1000`, `preserveAspectRatio="none"`):

| State | Stroke | Fill |
|---|---|---|
| Active field/token | `#147A6C`, 2px | `rgba(20,122,108,0.14)` |
| Mismatch field | `#B4452F`, 2px | `rgba(180,69,47,0.10)` |
| Low confidence (< 0.8) | `#B07A1E`, 1px dashed `4` | `rgba(176,122,30,0.10)` |
| Idle token | `rgba(23,26,24,0.45)`, 1px | none |

The overlay `<svg>` is `aria-hidden` and `pointer-events-none`; only its rects opt back into
pointer events, so hovering one shows `{token text} (Conf: 87%)` in a small `surface` tooltip
offset 12px from the cursor. Boxes without an overlapping token (IoU > 0.25) fall back to the
field name. Pressing on a box still bubbles to the stage, so panning works anywhere.

**Save payload.** `PUT` sends the eight header strings plus the line items (description,
quantity, unit price, line total) and then re-reads the receipt. The response's
`math_discrepancy` is stored on the row for the inbox tooltip/stamp.

### 4. `SCR-04`: Authenticated Capture (`/upload`)

**Header.** Eyebrow `CAPTURE`; title `Upload receipts`; meta is the selected client's name,
`Selected client`, or `Choose a workspace to begin`; an `Inbox` ghost action appears once a
workspace is selected.

**No workspace.** A ruled block (max 560px) with `Select a client workspace first`, one line of
copy, and a `Choose a client` primary button. Nothing is uploaded without a client ID.

**Capture controls.**

* `Take photo` — a 96px (`h-24`) filled `brand-900` target with a 24px `camera` icon, a hidden
  `capture="environment"` input, and a `focus-within` outline because the input itself is
  `sr-only`. On mobile this opens the OS camera.
* `Choose files` — a 56px (`h-14`) outlined target with an `upload` icon and a hidden multiple
  file input.
* Both accept `.jpg`, `.jpeg`, `.png`, `.heic`, `.pdf`, are disabled at 40% opacity while a batch
  uploads, and are remounted with a new `key` after each attempt so re-selecting the same file
  works.
* The mono limits line reads exactly:
  `JPEG, PNG, HEIC, PDF · 50 files per batch · 15 MiB each · 50 MiB per batch`.
  A note below reads `Processing continues in the background.`

**Feedback.** A `role="status" aria-live="polite"` mono line reports `Uploading…`, then
`{n} file(s) accepted.`, or the batch error. The per-file result list is a ruled stack of rows:
filename, the backend `error` (if any), and a `StatusPill` using the English stamps above.
Processing statuses show `Processing`; there is no raw-enum output. The header's `Inbox` ghost
action is the way back to the workspace.

**Duplicates.** The backend keys a duplicate on sanitized filename plus byte size within the
workspace and returns the existing receipt (same `id`, no second file, no reprocessing).
Duplicates inside one request are deduplicated with a `seen` set. Because the existing receipt
is returned as `PENDING_UPLOAD`/`UPLOADED`, the result list can show `Processing` for a file
that was not re-queued; the inbox row is the source of truth.

### 5. `SCR-05`: Export Hub (`/clients/:clientId/exports`)

**Header.** Eyebrow `WORKSPACE · {registration}` (or `WORKSPACE`); title `Exports`; meta is the
business name plus an `Inbox` link. Actions: the label `Accounting billing period`, a native
`month` input, and an `All time` toggle (`aria-pressed`) that clears the month.

**Strips.** Error: a `mismatch` strip with `role="alert"` and `Dismiss`. Success: a `verified`
strip with `role="status"` and `Dismiss`. Both are plain ruled bands, not floating toasts.

**Dispatch sheet.** One `<section aria-label="Export dispatch">` bounded by top and bottom
rules. Its header row shows the active filter
(`Filtering verified receipts for {month}` or `Exporting all verified receipts across all
billing dates`), the `Download both` primary button, and `Mark exported` (ghost) with the note
`Downloads leave receipt statuses unchanged. Marking is a separate, explicit action.` Buttons
disable individually while running; labels swap to `Generating bundle...`, `Downloading CSV...`,
`Downloading JSON...`, and `Marking...`.

Two ruled rows, each an 8/4 grid at `lg`:

| Row | Left | Right |
|---|---|---|
| **CSV** — `CSV` stamp, `Accounting batch CSV`, `Purchase journal batch import compatible with AutoCount and SQL Account desktop systems.` | Mono meta `Purchase journal · 11 columns · DocDate → TotalAmount`; `<details>` `Column mapping` listing `DocDate, DocNo, SupplierCode, SupplierName, Description, ItemCode, Qty, UnitPrice, TaxCode, TaxAmount, TotalAmount` | `Download accounting CSV (.csv)` secondary button |
| **JSON** — `JSON` stamp, `LHDN MyInvois multi-line JSON`, `UBL-shaped draft modelled on the official SDK sample; not validated against the LHDN schema, not signed, and never submitted.` | Mono meta `UBL 2.1 · 1.1-Invoice-MultiLineItem-Sample.json · draft envelope, unsigned`; `<details>` `Schema notes` (UBL namespaces, BRN/SST in `PartyIdentification`, line tax allocated to the document tax total, draft envelope — validate before submission) | `Download MyInvois JSON (.json)` secondary button |

**Copy and states.** Success messages: `Accounting CSV downloaded successfully.`,
`LHDN MyInvois JSON downloaded successfully.`,
`Both accounting CSV and LHDN MyInvois JSON downloaded successfully.`, and
`Marked {n} receipt(s) as exported.` With nothing verified, marking reports
`No verified receipts to mark as exported.` in the same verified strip. Without a workspace, the
page renders only an alert strip reading `No workspace client selected.` There is no page-level
spinner; the sheet stays visible while individual buttons work. The month input defaults to the
current month; `All time` clears it.

### 6. `SCR-06`: Spend Dashboard (`/clients/:clientId/dashboard`)

**Header.** Eyebrow `WORKSPACE · {registration ?? CLIENTS}`; title `Dashboard`; meta is the
business name, the note `verified and exported receipts only`, and an `Inbox` link. The action is
a labelled (`Month`) `month` input, defaulting to the current month, that drives
`GET …/dashboard/summary?month=YYYY-MM`.

**Stat strip.** A `<dl>` bounded by top and bottom rules, with 1px `border`-coloured gaps and
1/2/4 columns. Four `canvas` cells: `Spend this month` (mono money), `Receipts reviewed`,
`Needs review`, `Total receipts`. Labels are mono uppercase; values are mono at `title`, rising
to `display` at `sm`. A caption below reads
`Spend covers the selected month; receipt counts cover the whole workspace.`

**Tables.** Two ruled tables, no charts or bars:
`Top suppliers` (`Supplier`, `Receipts`, `Spend`; five rows maximum, empty copy
`No supplier totals for this month.`) and `Spend by category` (`Category`, `Spend`; all five
categories, pre-tax totals, caption `Pre-tax line totals; document tax is excluded.`). Both use
`.data-table` with explicit `aria-label`s and scroll horizontally on narrow screens. Category
labels are the backend's uppercase enums (`F&B`, `HARDWARE`, `WORKSHOP`, `RETAIL`, `OTHER`).

**States.** Loading is four skeleton rows. Error is a `role="alert"` strip with `Retry`. Empty is
`No dashboard data` with the hint `Verified receipts for this month will appear here.` Requests
are tagged so a late response for a previous month cannot overwrite the current one.

---

## 4.4 Form Control & Accessibility Standards

**Skip link.** The first focusable element is `Skip to content`; it is visually hidden until
focused, then pinned top-left as a 44px `surface` block with a 2px `brand-900` left rule,
targeting `<main id="main-content" tabIndex={-1}>`.

**Focus.** One global rule owns focus appearance:
`:where(a, button, input, select, textarea, summary):focus-visible` gets a 2px solid `#0E5A50`
outline at 2px offset. `.on-dark` regions (the charcoal canvas and the `brand-950` gate panel)
use `#DCEBE5`. There are no per-component rings. The only local focus treatment is the hidden
file input on `/upload`: because it is `sr-only`, its label shows a `focus-within` outline
(`brand-50` on the teal target, `brand-700` on the outlined target). Disabled controls are
excluded by the browser.

**Labels and errors.** `.field-label` is 10px mono uppercase. `LabelledInput` wires `htmlFor`
and `id`; totals inputs are wrapped by their `<label>`; line-item inputs carry explicit
`aria-label`s. Icon-only buttons have `aria-label`s (`Zoom in`, `Remove line 2`, `Sign out`).
The required field in `ClientForm` and the session-id field in `AccountantGate` set
`aria-invalid` and point `aria-describedby` at a stable error id; the session gate's error is
`role="alert"`. The review editor does not mark individual fields invalid: the action bar's
`Fix {field} before verifying.` message and the math banner carry the error, and neither is tied
to a specific input by `aria-describedby`.

**Target sizes.** Primary controls, inputs, delete/add, zoom, and toolbar buttons are 44px.
Line-item text inputs are 34px dense fields, but their delete control and `Add Line` remain
44px. Inbox filter tabs are 40px; inbox `Open` buttons are 44px and table rows are ≈44px at
`sm`. Pagination buttons are 36px. Thumbnails are 32×32 and are not interactive. Mobile tab
targets are at least 56px tall.

**Live regions.** Polite (`role="status"`): inbox upload feedback, inbox pagination range,
`/upload` upload feedback, review invalid-field message, math banner, export success. Assertive
(`role="alert"`): page-level error strips, client-form and gate errors, export errors. Loading
skeletons are `role="status" aria-busy="true"` with screen-reader text (`Loading page`). Status
stamps are ordinary text, so they are announced when the surrounding row is read.

**Dialogs.** The review leave prompt is a native `<dialog>` opened with `showModal()`: focus is
trapped by the platform, `Escape` fires `cancel`, the backdrop is `rgb(23 26 24 / 0.58)`, and
focus returns to the triggering control on close. The reject confirmation is an inline
`role="alertdialog"` band that receives focus and is cancelled with `Escape`; it is deliberately
not a second modal, so the receipt stays visible while rejecting.

**Structure and semantics.** The shell exposes two labelled `<nav>` landmarks (rail and mobile
tabs; one is hidden by breakpoint). Every page has exactly one `h1` (page title or receipt ID).
The inbox uses one table DOM with explicit ARIA roles so the mobile reflow remains a table to
assistive technology; its filter group is labelled `Status filter`. Clients uses a labelled
table at `sm`+ and a labelled list below. The receipt image carries the alt text
`Scanned receipt for review`, its OCR overlay SVG is `aria-hidden`, and the canvas toolbar is a
row of labelled 44px buttons.

**Images.** Inbox thumbnails use the filename as alt text and a labelled placeholder when the
blob is unavailable. The review image's alt is `Scanned receipt for review`; a failed load shows
a textual `Image unavailable` panel. No information is conveyed by colour alone: every stamp has
text, and every low-confidence or error state has an icon or sentence.

**Reduced motion and reflow.** The reduced-motion rule collapses transitions, animations, and
smooth scrolling. At 320px the page shell keeps 20px side padding, page-header actions wrap,
the inbox table becomes stacked rows, filter tabs scroll horizontally, the review panes stack
with a 40dvh canvas, line-item and dashboard tables scroll inside their sections, and the fixed
bottom tab bar never overlaps the last control because pages reserve its height.

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
  overall_confidence: number | null;
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
  overall_confidence: number | null;
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
