---
format: 1920x1080
duration: 32.7s
message: "Photograph the receipt. Ship the journal."
arc: Hook → Reveal → Intake → Provenance → Audit → Export → Close
audience: Malaysian micro-SME owners and freelance accountants who keep a shoebox of receipts
mode: autonomous
---

# Kenyalang Ledger — launch film

**Thesis.** Every other receipt app asks you to trust its extraction. This one shows you the
pixels each field came from, and checks the arithmetic in code before anything is exported.

**Tone.** Dry, unhurried, accountant-adjacent. The product is the evidence; the type does the
arguing. Nothing is sold. The CTA is an invitation to run it locally.

**Design law (from `frame.md`).** Warm paper ground, ink Garamond display, mono labels, 1px taupe
hairlines, one green. Radius ≤2px. Zero shadows, zero gradients, zero 3D tilt. Declarative frames
run 50–60% empty. Every numeral traces to the seeded demo receipt.

**Motion law.** Nothing moves without a reason. Elements enter by *resolving* — a hairline draws,
a label types on, a plate settles a few pixels — never by sliding in from off-canvas. The camera
moves twice in the whole film: once into the receipt (Frame 4) and once out of it (Frame 5).
Everything else holds still and lets the cuts do the work.

**Cut law.** Every seam is a hard cut, and every cut lands composed. Because the transition
happens *inside* the incoming frame — a plate 48px off its mark sliding into register, a match cut
where Frame 4 ends at 1.14 on the total and Frame 5 opens at 1.055 on the same block — no
inter-frame dissolve is needed or wanted. A crossfade would start each frame at `opacity: 0`,
which is precisely the blank-flash defect this cut law exists to prevent; and the registry's
`zoom-through` (2.5× outgoing scale plus an 8px blur) is alien to a design built on hairlines and
zero shadow. The one full-bleed colour change — paper to `bg-deep` at Frame 7 — is stronger as a
cut than as a dissolve, which would only muddy the flip. Easing is `power2.out`/`power3.out`
for entries, `none` for draws and counts.

**Plate law.** All product imagery is real capture from the running app at 1920×1080, cropped
from 2× masters. No mockups, no fake browser chrome, no invented UI. UI is shown at ≥1:1 so
16px product text stays legible on a 1080p frame.

---

## Frame 1 — Hook: the shoebox

- scene: Two lines of ink type on warm paper. A stack of receipts fanned at the right edge, mostly cropped away.
- duration: 4.2s
- poster: 3.2s
- transition_in: cut
- status: outline
- voiceover: "A shoebox of receipts. A month of typing."
- src: compositions/frames/01-hook.html
- focal: receipt-hero.png
- roles: receipt-hero.png = background (bleeds off the right edge, dimmed to 0.92 opacity, 62cqw wide; text occupies the left 46% and never overlaps it)
- asset_candidates: assets/receipt-hero.png — the photographed receipt, 1024x572 native, the hook still

The film opens cold on the problem, stated flatly. No logo, no music sting, no "introducing".

**Shot sequence**

- `0.0–0.55` Ground is `bg-primary`. Empty. A single 1px hairline at `pad-x` from `y=46cqh`, drawing left→right in 0.55s (`scaleX 0.82→1`, `transform-origin: left`).
- `0.0–0.75` Mono label `A MONTH OF RECEIPTS` is already present at 55% on the cut and rises 8px into register, tracking already at 0.16em (never animated — tracking animation reads as amateur).
- `0.25–0.95` Line one of the headline resolves: **"A shoebox of receipts."** EB Garamond 500, `h1` 5.2cqw, ink, sentence case. Words enter as a single block: `opacity 0→1`, `y 14px→0`, 0.7s `power2.out`. No per-word stagger — this is a statement, not a title sequence.
- `1.15–1.75` Line two: **"A month of typing."** Same treatment, 0.6s, offset 0.15s. Both lines share one text block, `line-height 1.08`, max-width 44cqw, left-aligned at `pad-x`.
- `0.55–1.45` The receipt photograph enters at the right: `receipt-hero.png` (1024×572 native), scaled to **62cqw wide**, rotated 0deg, positioned so its left third is cropped by the right frame edge. It arrives at `opacity 0→0.92` over 0.9s with `y 26px→0` — it *settles* onto the page like a print dropped on a desk. A 1px `line-strong` border traces its visible edge only.
- `3.3–4.2` Hold. Nothing moves. The silence before the turn is the point.

**Video direction**

- Left 46% is type, right 54% is the photograph bleeding off-canvas. The headline never overlaps the photo.
- The photo is desaturated to ~40% and lifted to `opacity 0.92` so it reads as evidence, not decoration — it must not compete with the headline.
- Do not animate the receipt's rotation. A tilting photo is a stock-motion cliché and breaks the flat-paper law.
- Keep the bottom 22% empty. The frame should feel like the top of a page, not a poster.

---

## Frame 2 — Reveal: the wordmark

- scene: Typographic wordmark and one-line definition, centred on paper. Hairline above and below the lockup.
- duration: 5.7s
- poster: 4.0s
- transition_in: cut
- status: outline
- voiceover: "This is Kenyalang Ledger — a receipt workspace for small Malaysian businesses."
- src: compositions/frames/02-reveal.html
- focal: hornbill.svg
- roles: hornbill.svg = cutout (centred mark above the wordmark, 5.2cqw, the only mark in the film)
- asset_candidates: assets/hornbill.svg — the app favicon mark, used for the typographic lockup

The turn. Name the thing, define it in one clause, get out.

**Shot sequence**

- `0.0–0.4` Hard cut from Frame 1. Ground stays `bg-primary`, so the mark and wordmark land in register on the same paper the photograph was sitting on — the composition empties and refills in one frame. The 0.4s is a settle, not a dissolve.
- `0.0–0.7` The hornbill mark (`hornbill.svg`) draws in at 5.2cqw, centred, above the wordmark. It scales `0.94→1` in 0.7s with no opacity fade, so the mark is on screen at the cut. It is the only mark in the film and appears once.
- `0.0–0.8` Wordmark: **"Kenyalang Ledger"** at `display` 7.0cqw, EB Garamond 500, ink, centred. Letters rise 10px as one block over 0.8s from full opacity.
- `1.4–2.2` Hairline draws beneath the wordmark, centred, `scaleX 0→1` from centre, 44cqw wide.
- `1.8–2.7` Definition line: **"A receipt workspace for small Malaysian businesses."** Inter 400 at `subtitle` 1.35cqw, `text-secondary`, centred, max-width 52cqw, 1.5 line-height. Fades up 8px over 0.7s.
- `2.7–3.6` Second hairline draws beneath the definition. The lockup is now bracketed by two rules — a printed colophon.
- `3.6–5.7` Hold. The mark breathes very slightly (`scale 1→1.008` over 1.8s) — the only continuous motion in the frame, imperceptible unless you look for it.

**Video direction**

- Perfectly centred composition. 58% empty. This frame is the film's breath.
- No tagline, no "introducing", no version number, no date. The definition clause is the whole sell.
- Do not put the mark in a circle or a badge. It sits on the page as drawn.
- If the hard cut from Frame 1 leaves the receipt reading as though it ghosts through, pull the wordmark's settle back to 0.35s rather than speeding up the lockup.

---

## Frame 3 — Intake: the inbox

- scene: The real inbox table, two receipts read and queued. Cropped to the rows so the type is legible.
- duration: 4.2s
- poster: 3.0s
- transition_in: cut
- status: outline
- voiceover: "Photograph the receipt. It lands in the inbox, already read."
- src: compositions/frames/03-inbox.html
- focal: inbox-rows.png
- roles: inbox-rows.png = focal supporting plate (the two read rows, 1:1, bleeds off right); inbox-head.png = supporting (column heads, 1:1, sits flush above the rows to form one surface)
- asset_candidates: assets/inbox-head.png — inbox page header at 2x, table chrome and column heads; assets/inbox-rows.png — inbox table rows at 2x, two receipts already read

First product proof. The claim is intake speed, shown as a populated queue — not an empty state.

**Shot sequence**

- `0.0–0.45` Hard cut from Frame 2. The plate is already 48px off its mark and slides into register over 0.45s — the lateral motion the seam needs happens *inside* the frame, so the cut itself is clean and the product surface appears at full opacity.
- `0.0–0.65` `inbox-head.png` (3025×350 at 2×) enters as a plate at 1:1 CSS scale, top-anchored at `pad-x`, 1px `line-strong` border. It fades up 12px.
- `0.25–1.15` `inbox-rows.png` (3000×513 at 2×) enters beneath it, same width, staggered 0.25s. Together they form one continuous surface — the seam is invisible because both were captured from the same render.
- `0.15–0.75` A mono label at left, outside the plate: `INBOX · ALL RECEIPTS` — types on character by character over 0.6s (`steps(24)`), then holds. No count: the plate already states `receipts 1–2 of 2` and a second numeral would both duplicate it and breach the numeral budget.
- `1.6–2.6` Two 1px `accent` tick marks appear at the left edge of the two rows, 0.12s apart — a quiet "these are done" signal. They are drawn *outside* the plate's border, in the gutter, so no product pixels are covered.
- `0.55–1.35` One Inter line under the label: **"Photographed, read, and queued — before you sit down."** 1.05cqw, `text-secondary`, max-width 30cqw. Rises 8px from 45% opacity — present at the cut, because it carries the frame's claim.
- `3.2–4.2` Hold. No scroll, no cursor. The table is the argument.

**Video direction**

- The plate is the hero: it occupies the right 68% of the frame at true 1:1, bleeding off the right edge so the table's rightmost columns are cropped rather than shrunk.
- Left 32% holds the label and the one line of copy, vertically centred against the plate.
- Never show the whole browser window. The app's own chrome (sidebar, top bar) is not the story; the rows are.
- Resist adding a cursor. This frame is about the *state* of the inbox, not an interaction.

---

## Frame 4 — Provenance: every field has a pixel

- scene: The receipt scan with provenance brackets lit, beside the extracted fields. Camera pushes in on the total.
- duration: 4.9s
- poster: 3.6s
- transition_in: cut
- status: outline
- voiceover: "Every field is traced back to the pixels it came from."
- src: compositions/frames/04-provenance.html
- focal: receipt-clean.png
- roles: receipt-clean.png = cutout (the scan, 1:1 on bg-secondary, brackets and connectors are drawn as HTML over it); review-fields.png = supporting (the extracted field strip, 1:1, top-aligned with the scan); receipt-provenance.png = reference only (shows where the app's own overlay lands, do not place it in the frame)
- asset_candidates: assets/receipt-provenance.png — receipt scan with the app provenance overlay drawn on it, 2x; assets/receipt-clean.png — the same receipt scan without the overlay, 2x; assets/review-fields.png — extracted field strip (supplier, SST, date, BRN) at 2x

The core claim of the product, and the reason this film exists. The brackets are real product
behaviour — they are drawn by the app over the scan.

**Shot sequence**

- `0.0–0.5` Hard cut from Frame 3. The scan and its field plate are already on screen at partial opacity and settle 12–16px into register; nothing fades up from nothing.
- `0.0–0.6` `receipt-clean.png` (1698×948 at 2×, native 849×474 CSS) enters left at 1:1, sitting on a `bg-secondary` field with a 1px `line-strong` border and generous margin — a print on a mat. It The cut lands on it at full opacity, offset 12px, and it settles into place.
- `0.0–0.7` `review-fields.png` (1996×590 at 2×) enters right at 1:1, top-aligned with the receipt's top edge. It is the *actual* extracted fields for this receipt: supplier, SST, date, BRN.
- `1.12–3.0` Three `bracket` elements (1px `accent`, no fill) draw over the receipt, one per field, starting 0.22s apart (1.12 / 1.34 / 1.56). Each draws as four `scaleX`/`scaleY` edges — top, then right, then bottom, then left — 0.22s per edge, so a bracket takes 0.88s to close. The brackets land on the supplier block, the SST line, and the total.
- `2.02–2.66` The supplier and SST brackets each emit, once closed, a 1px `accent` connector that runs right to the corresponding field in `review-fields.png`. The total bracket emits no connector: the fields strip carries no total row, so a leader would terminate beside the empty INVOICE NUMBER box and imply the total maps to a blank field. The bracket alone marks it. Each connector is preceded by a 0.12s elbow, then drawn not faded (`scaleX 0→1`, `transform-origin: left`, 0.30s `power1.out`), the two staggered 0.22s apart. This is the money shot: pixels → field, made literal.
- `1.43–1.88` The claim sets beneath the label as a second mono line, `Each field, traced to its source pixels`, 13px `text-secondary` at 0.14em. It does **not** fade out with the label: it is the frame's only statement of the point, so it has to outlive the connectors.
- `2.95–4.35` Camera push: the whole composition scales `1→1.14` with `transform-origin` at the receipt's total (bottom-right of the scan), easing `power2.inOut` over 1.4s. The total `RM 265.00` ends centred in frame, brackets still attached.
- `4.35–4.9` Hold on the pushed-in total with its bracket still live. No connector runs from it — the fields strip has no total row, so the bracket alone marks it. The push lifts the claim into the clear top strip (rows 35–48), 65px clear of the scan, so the frame is never wordless.

**Video direction**

- The connectors are the point. If they read as decoration, the frame has failed — they must clearly originate at a bracket edge and terminate at a field's left edge.
- Keep the receipt and the fields at the same vertical scale so the connectors are horizontal, not diagonal.
- Do not label the brackets with confidence percentages. The product shows a 0% OCR-check badge on this receipt; foregrounding it would undercut the claim and invite a question the film doesn't answer.
- The push must be slow enough to read as a camera, not a zoom effect. 1.4s minimum.

---

## Frame 5 — Audit: the arithmetic is checked

- scene: Detail crop of the totals block and the MATH CHECK strip. One number dominates.
- duration: 4.3s
- poster: 3.2s
- transition_in: cut
- status: outline
- voiceover: "The arithmetic is checked by code, not by eye."
- src: compositions/frames/05-audit.html
- focal: review-totals.png
- roles: review-totals.png = focal supporting plate (detail crop from the SST row through the MATH CHECK strip, 1996×384 at 2x, 1:1, right 62% of frame)
- asset_candidates: assets/review-totals.png — totals block and MATH CHECK strip at 2x

The second half of the trust argument: extraction can be wrong, so the maths is verified
independently. This frame is a detail crop, not a screen.

**Shot sequence**

- `0.0–0.5` Match cut from Frame 4. Frame 4 ends pushed to 1.14 on the grand total; Frame 5 opens at 1.055 on that same block and settles to 1.0. The camera reads as continuing across the seam — the zoom is split between the two frames rather than dissolved between them.
- `0.2–1.0` `review-totals.png` (1996×336 at 2× → 998×168 CSS) enters as a detail crop at 1:1, occupying the right 62% of frame, 1px `line-strong` border. It starts at the `SST (6%)` row and ends on the rule beneath the `MATH CHECK` strip — cropped above the next section's `AUDIT HISTORY` heading, so no bisected glyphs sit on the plate's bottom edge. The audit column's confidence row is deliberately outside the crop — it would contradict this frame's claim. Use the PNG as-is; do not crop further, the `MATH CHECK` line and the `MISSING SST ON REGISTERED MERCHANT` chip must both stay fully visible.
- `0.1–0.6` Mono label at left: `ARITHMETIC AUDIT` — rises 10px from 50% opacity, present on the cut.
- `0.25–0.95` Headline at left, `h2` 3.4cqw: **"Checked by code, not by eye."** EB Garamond 500, ink. Two lines, max-width 28cqw.
- `0.65–1.25` Under it, one Inter line: **"Line items sum to the total, or the export is blocked."** 1.05cqw, `text-secondary`, max-width 26cqw. Present on the cut at 50% and rising 14px — it does not fade up from nothing.
- `2.0–3.2` Inside the plate, a 1px `accent` bracket draws around the `MATH CHECK` strip only — the product's own verification line, `Line items total RM 265.00 + Tax RM 0.00 = Grand Total RM 265.00`. This is the single green element in the frame.
- `2.8–3.6` A 1px `accent` rule draws beneath the `GRAND TOTAL 265.00` value, left→right, 0.4s. It is the only motion inside the plate.
- `3.7–4.3` Hold.

**Video direction**

- The plate must be legible: `GRAND TOTAL 265.00` and the MATH CHECK sentence are the two things a viewer must be able to read at 1080p. Crop until they are.
- Do not animate the numbers counting up. They are already correct; counting implies they were computed for the camera.
- The `MISSING SST ON REGISTERED MERCHANT` warning chip stays visible in the crop — it is honest, it is real, and it shows the tool flags problems rather than hiding them. Do not crop it out.
- Keep the left column's text block to three elements maximum.

---

## Frame 6 — Export: the journal

- scene: The exports screen — a finished batch, two formats, one download. Full-bleed plate with a label.
- duration: 4.0s
- poster: 2.4s
- transition_in: cut
- status: outline
- voiceover: "Then export a purchase journal your accountant can import."
- src: compositions/frames/06-export.html
- focal: exports-batch.png
- roles: exports-batch.png = focal supporting plate (the batch row, 1:1, whole panel visible and flush to the right edge); exports-head.png = supporting (page header, 1:1, flush above the batch, same width)
- asset_candidates: assets/exports-batch.png — October 2026 export batch at 2x, both formats and Download both; assets/exports-head.png — exports page header at 2x

The payoff. Show the artefact, name the formats, and be precise about what it is not.

**Shot sequence**

- `0.0–0.4` Hard cut from Frame 5. Both export plates arrive 26–30px off their marks and settle into register over 0.65s — vertical motion inside the frame, cut on the beat.
- `0.1–0.7` `exports-head.png` (3000×325 at 2× → 1200×130 CSS) enters top at 1:1. Its right edge lands on the frame edge, so the panel's own border is the only thing touching 1920.
- `0.4–1.1` `exports-batch.png` (3000×1200 at 2× → 1200×480 CSS) enters beneath it, staggered 0.2s, same treatment. The batch row, the format names, `Download both`, `Mark exported`, and both per-format download buttons sit fully inside the plate — nothing is cropped.
- `0.0–0.6` Mono label at left: `OCTOBER 2026 · VERIFIED ONLY` — rises 10px from 55% opacity, on screen at the cut.
- `0.05–0.60` Headline at left, `h2` 3.4cqw: **"A purchase journal your accountant can import."** Three lines, max-width 26cqw. The three lines rise 18px from 50% opacity, staggered 0.05s — present at the cut.
- `0.30–0.90` One Inter line: **"AutoCount and SQL Account CSV, plus a MyInvois-shaped draft."** 1.05cqw, `text-secondary`, max-width 25cqw. Rises 12px from 50%.
- `2.7–4.0` Hold.

**Video direction**

- The plate carries two format names that matter; both sit inside the visible panel, which ends flush on the frame edge. 718px left + 1200px wide + 2px border = 1920 exactly, so no glyph is ever sliced.
- The word "draft" must stay legible next to MyInvois — the export is unsigned and never submitted, and the film must not imply otherwise.
- No download animation, no progress bar, no checkmark flourish. The batch is already marked exported; the frame is a receipt of work done.
- Left column: label, headline, one line. Nothing else.

---

## Frame 7 — Close: run it locally

- scene: Inverted deep-green plate. Wordmark, the promise, the CTA. One paper rule.
- duration: 5.4s
- poster: 3.4s
- transition_in: cut
- status: outline
- voiceover: "Verified once. Exported clean. Run it locally — it's open source."
- src: compositions/frames/07-close.html
- focal: hornbill.svg
- roles: hornbill.svg = cutout (small paper mark above the wordmark, 3.6cqw, 80% opacity)
- asset_candidates: assets/hornbill.svg — the app favicon mark, used for the typographic lockup

The only inverted frame. It is a sign-off, not a pitch — there is no hosted product to sign up for.

**Shot sequence**

- `0.0–0.5` Hard cut from Frame 6. The ground flips paper → `bg-deep` `#0B3F3A` on the beat and type inverts to paper `#F6F1E7`. A dissolve here would muddy the one full-bleed colour change in the film; the cut is the event.
- `0.0–0.6` Wordmark: **"Kenyalang Ledger"** at `h2` 3.4cqw, EB Garamond 500, paper colour, centred. Rises 10px from 75% opacity — the cut lands with the lockup already legible.
- `0.25–0.85` Hornbill mark above it at 3.6cqw, in paper at 80% opacity. Rises 8px from 45% opacity over 0.6s.
- `1.0–1.8` Paper rule draws beneath the wordmark, centred, `scaleX 0→1`, 36cqw, `rgba(246,241,231,0.5)`.
- `1.4–2.2` The promise, two short lines, `h3` 2.1cqw, paper at 88%: **"Verified once. Exported clean."** Centred.
- `2.2–3.0` CTA line, `body-strong` 1.05cqw, paper: **"Run it locally — it's open source."** Centred, with `MIT licensed` in mono `micro` beneath it at 60% opacity.
- `2.6–3.4` A 1px paper rule draws beneath the CTA, 12cqw, centred — a terminal underline.
- `3.4–5.4` Hold to black-free end. No fade to black; the green plate is the last thing on screen.

**Video direction**

- Exactly three text elements plus the mark and two rules. Nothing else.
- Do not add a URL. There is no hosted instance and no remote; inventing one would be a lie.
- Do not add "built with" credits, a date, or a version number.
- The final hold is deliberate — 1.2s of stillness on the green plate lets the narration land.

---

## Continuity notes

- **Grounds.** Frames 1–2 `bg-primary`; 3 `bg-primary` with product plates; 4 `bg-secondary` behind the receipt; 5 `bg-primary`; 6 `bg-primary`; 7 `bg-deep`. Only Frame 7 inverts.
- **Green budget.** One green element per frame: F1 none, F2 none (mark is ink), F3 the three gutter ticks, F4 the brackets + connectors, F5 the MATH CHECK bracket + underline, F6 none, F7 the ground itself.
- **Hairlines.** Every separator is 1px `#D9D2C3`. The only 2px rules are the ink-rule on F1 (if used) and the paper rule on F7.
- **Numbers on screen.** RM 265.00, 120.00, 60.00, 35.00, 50.00, RM 0.00, 12/10/2026, Y24-1808-31015655, 200401032489 (665243-X), October 2026. No other numerals anywhere — no percentages, no counts of users, no time savings.
- **Claims.** The film says: receipt digitisation, per-field provenance, arithmetic verification, AutoCount/SQL Account CSV export, MyInvois-shaped draft JSON (unsigned, never submitted), MIT licence, runs locally. It does not say: LHDN-certified, PDPA-compliant, accurate to N%, saves N hours, trusted by N businesses.
