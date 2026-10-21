---
version: alpha
name: Kenyalang — Frame (video / frame layer)
description: >
  Frame-scale design system for Kenyalang Ledger, remixed onto the captured product brand. Warm
  paper ground, ink type, one deep-green accent, taupe hairlines as the only structural device.
  Editorial and quiet: a well-set ledger page, not a SaaS deck. Composition and motion are free;
  the atoms below are fixed.
unit: the frame — 1920×1080 primary; 9:16 and 1:1 documented
principle: warm paper · hairline structure · one green · numbers come from the product

colors:
  bg-primary: "#F6F1E7"
  bg-secondary: "#EFE8DA"
  bg-card: "#FBF8F1"
  bg-deep: "#0B3F3A"
  text-primary: "#171A18"
  text-secondary: "#4A4F4A"
  text-muted: "#8A8274"
  accent: "#147A6C"
  accent-deep: "#0B3F3A"
  line: "#D9D2C3"
  line-strong: "#B9B0A0"
  white-overlay: "rgba(255,255,255,0.42)"

typography:
  # — reading ramp (Inter) —
  body:        { fontFamily: "Inter", cqw: 1.05, weight: 400, lineHeight: 1.6, color: "text-secondary" }
  body-sm:     { fontFamily: "Inter", cqw: 0.86, weight: 400, lineHeight: 1.55 }
  body-strong: { fontFamily: "Inter", cqw: 1.05, weight: 500, lineHeight: 1.5, color: "text-primary" }
  subtitle:    { fontFamily: "Inter", cqw: 1.35, weight: 400, lineHeight: 1.5 }
  label:       { fontFamily: "JetBrains Mono", px: 15, weight: 500, tracking: "0.16em", upper: true, color: "accent" }
  micro:       { fontFamily: "JetBrains Mono", px: 13, weight: 400, tracking: "0.14em", upper: true, color: "text-muted" }
  data:        { fontFamily: "JetBrains Mono", px: 20, weight: 500, tracking: "0.01em", color: "text-primary" }
  # — display ramp (EB Garamond 400/500, sentence case) —
  h3:          { fontFamily: "EB Garamond", cqw: 2.1, weight: 500, lineHeight: 1.16 }
  h2:          { fontFamily: "EB Garamond", cqw: 3.4, weight: 500, lineHeight: 1.12 }
  h1:          { fontFamily: "EB Garamond", cqw: 5.2, weight: 500, lineHeight: 1.08 }
  display:     { fontFamily: "EB Garamond", cqw: 7.0, weight: 500, lineHeight: 1.04 }
  figure:      { fontFamily: "EB Garamond", cqw: 9.0, weight: 400, lineHeight: 1.0 }

spacing:
  pad-x: "6.5cqw"
  pad-y: "5.5cqw"
  gap-xl: "5cqw"
  gap-lg: "3.2cqw"
  gap-md: "1.8cqw"

components:
  hairline:
    rule: "1px solid {colors.line}"
    description: "The universal structural device. Every separator, card edge, rail and table rule is this one line. Nothing is thicker except the single ink accent rule."
  ink-rule:
    backgroundColor: "{colors.text-primary}"
    size: "~14cqw × 2px"
    description: "The one strong rule. Cover and closer only."
  card:
    backgroundColor: "{colors.bg-card}"
    border: "1px solid {colors.line}"
    rounded: "2px"
    shadow: "none"
    description: "The product's own surface. Radius never exceeds 2px."
  chip:
    backgroundColor: "{colors.bg-secondary}"
    border: "1px solid {colors.line}"
    rounded: "2px"
    typography: "{typography.micro}"
    description: "Status chip, as in the real inbox (OCR CHECK, EXPORTED)."
  screen:
    border: "1px solid {colors.line-strong}"
    rounded: "2px"
    shadow: "none"
    description: "A captured product plate. Always at native aspect, never distorted, never with fake browser chrome."
  bracket:
    border: "1px solid {colors.accent}"
    description: "Provenance marker: a 1px green box drawn over the scan to show where a value came from."
  rule-column:
    borderLeft: "1px solid {colors.line}"
    description: "Drafting guide at the left gutter, used on cover and closer only."

fonts:
  display: { family: "EB Garamond", file: "assets/fonts/eb-garamond-latin-500-normal.woff2", weight: 500 }
  display-regular: { family: "EB Garamond", file: "assets/fonts/eb-garamond-latin-400-normal.woff2", weight: 400 }
  body: { family: "Inter", file: "assets/fonts/inter-latin-400-normal.woff2", weight: 400 }
  body-medium: { family: "Inter", file: "assets/fonts/inter-latin-500-normal.woff2", weight: 500 }
  body-semibold: { family: "Inter", file: "assets/fonts/inter-latin-600-normal.woff2", weight: 600 }
  mono: { family: "JetBrains Mono", file: "assets/fonts/jetbrains-mono-latin-400-normal.woff2", weight: 400 }
  mono-medium: { family: "JetBrains Mono", file: "assets/fonts/jetbrains-mono-latin-500-normal.woff2", weight: 500 }
---

# Kenyalang — Frame

## Brand adaptation (READ FIRST — the frontmatter is the source of truth)

This is a remix of the **cartesian** preset onto Kenyalang Ledger's captured brand. The YAML
frontmatter is normative. The prose below has been rewritten to match it — if anything in the prose
contradicts the frontmatter, the frontmatter wins.

- **Fonts.** `EB Garamond` (display, 400/500) + `Inter` (body, 400/500/600) + `JetBrains Mono`
  (labels, data). Every family has a real `.woff2` in `assets/fonts/`; declare each one with an
  `@font-face` in the frame that uses it. Never name a family without a file.
- **Colour.** Warm paper `#F6F1E7`, card `#FBF8F1`, stone `#EFE8DA`, ink `#171A18`, secondary
  `#4A4F4A`, muted `#8A8274`, hairline `#D9D2C3` / `#B9B0A0`, green `#147A6C` and `#0B3F3A`.
  There is no blue, no cyan, no purple. Green is an accent, not a field colour — except the
  deliberate deep-green plate.
- **Structure.** 1px taupe hairlines only. Radius ≤ 2px. Zero shadows, zero gradients on type.
- **Voice.** Sentence case for headlines. Mono uppercase with wide tracking for labels and data.

## Overview

The system is a **quiet editorial ledger**: warm paper, ink type, hairline rules, and one green.
Hierarchy comes from type contrast (Garamond display against Inter body against mono data) and from
negative space — not from weight, fill, or shadow. Atmosphere comes from the product itself: the
photographed receipt, the hairline table, the small tracked label.

The reference is a well-printed annual report or a museum wall label, not a startup deck.

**Key characteristics at frame scale:**

- 1px taupe hairline as the only separator.
- Garamond display at 500, sentence case, ink. Never bold, never uppercase, never green.
- Mono uppercase labels at 13–15px with 0.14–0.16em tracking in green or muted taupe.
- Sparse, breathing layouts. Declarative frames run 50–60% empty.
- Real product surfaces, presented flat and legible — no perspective, no tilt, no fake depth.

## The Frame

### Frame Craft Bar

- **Squint** — one element dominates at 3–6× its neighbour. Usually a Garamond headline or a number.
- **Silence** — declarative frames read 50–60% empty. A crowded frame is a broken frame.
- **Restraint** — at most one green element and one ink rule per frame. No decorative gradients.
- **Legibility** — any load-bearing text ≥ 1.4cqw. UI plates must be readable at 1920×1080 without zooming into noise; crop into the region that carries the point instead of shrinking a whole app window.

### Canvas

- **Primary:** 1920×1080 (16:9). Author in `cqw` (`px ÷ 1920 × 100`).
- **Safe area:** `pad-x` 6.5cqw. Nothing load-bearing outside it.
- **Container law.** Every frame ground sets `container-type: size`; all frame-relative units are
  `cqw`/`cqh` against it — never `vw`.

## Colours

`bg-primary` is the ground. `bg-card` is a raised paper surface. `bg-deep` is the single inverted
plate (green field, paper type) used once, for the closing. `text-primary` is headlines and numbers.
`text-secondary` is body. `text-muted` is captions. `accent` is labels, brackets, and small marks.
`line` is every hairline. Never place green text on green; never place muted taupe on stone.

## Typography

Two ramps plus a data voice.

- **Display ramp** — EB Garamond 400/500, sentence case, ink. `h3` 2.1cqw for supporting lines,
  `h2` 3.4cqw for statements, `h1` 5.2cqw for the hook, `display` 7.0cqw reserved for a single
  short phrase, `figure` 9.0cqw for a number that is the whole point.
- **Reading ramp** — Inter 400 body at 1.05cqw, 500 for emphasis. Line height 1.6.
- **Data voice** — JetBrains Mono. Uppercase 13–15px at 0.14–0.16em for labels and chips; 20px
  for figures inside tables. This is what makes the film read as software rather than a poster.

Fit the headline to its measure: ≤3 words → `h1`/`display`; 4–6 → `h2`; 7+ → `h3`. Cap any text
block at 78cqw.

## Depth & Surface

Flat. Hierarchy comes from paper tone, hairline, type size, and space. A card is distinguished by
`bg-card` plus a 1px line — nothing else. The only permitted "elevation" is a UI plate sitting on
`bg-secondary` with a 1px `line-strong` border.

**Ceiling:** no box-shadow, no blur, no gradient fills, no 3D transforms on text, no rounded
corners above 2px, no glow.

## Shapes

- `2px` radius — cards, chips, plates.
- `1px` lines — everything structural.
- `50%` — only for the hornbill mark's enclosing ring, if used at all.
- No other geometry. No blobs, no floating orbs, no abstract mesh.

## Components

- **hairline** — the identity. Table rules, card edges, section dividers, the baseline under a label.
- **card** — paper surface with a hairline edge.
- **chip** — status pill from the product (`OCR CHECK 0%`, `EXPORTED`).
- **screen** — a real captured plate, native aspect, hairline border.
- **bracket** — 1px green provenance box over a scan region. This is a real product behaviour.
- **ink-rule** — the single strong rule, cover and closer only.
- **rule-column** — drafting guide at the left gutter, cover and closer only.

## Frame Treatments

### 1 · Hook (statement · left)

Ground `bg-primary`. Label above, `h1` or `display` headline in ink, one short Inter line beneath,
hairline under the block. Optional ink-rule. 55–60% empty. No imagery.

### 2 · Product plate (proof · full-bleed or inset)

A real captured screen. Either full-bleed with a hairline inset frame, or inset on `bg-secondary`
with generous margin. A mono label and one sentence sit outside the plate, never on top of
load-bearing UI. Crop to the region that carries the claim.

### 3 · Two-column editorial (explanation · asymmetric)

Text column at 38cqw with label, `h2`, body; visual column with a plate or a detail crop. Gutter
`gap-xl`. Hairline between columns is optional and usually unnecessary.

### 4 · Detail crop (proof · zoom)

A tight crop of the real UI — a table row, a totals block, a provenance box. Presented at 1:1 or
4:3 with a hairline border and a mono caption naming what the viewer is looking at. This is how the
film shows small type without shrinking the whole app.

### 5 · Number plate (data · centred or left)

One figure at `figure` scale in Garamond with a mono label and one Inter line of context. Numbers
must trace to the product. Hairline above the cluster, nothing else.

### 6 · Closing (sign-off · centred, inverted)

Ground `bg-deep`. Paper-coloured type. The product name, one line of promise, the CTA. One ink or
paper rule. This is the only inverted frame in the film.

## Composition Rules

### Do

- Use one hairline weight everywhere.
- Keep Garamond headlines ink, sentence case, at 500.
- Let the receipt and the UI carry the visual interest; the type does the arguing.
- Leave real empty space. Silence is the brand.
- Keep captured UI at native aspect and honest scale.

### Don't

- Don't add glow, shadow, gradient, or 3D tilt.
- Don't put a headline on top of a UI plate where it covers data.
- Don't use green as a large field except the closing plate.
- Don't invent metrics, customers, certifications, or dates.
- Don't crowd. If it needs a fourth element, cut one.

## Aspect-Ratio Behaviour

| Treatment      | 16:9                     | 9:16                        | 1:1                        |
| -------------- | ------------------------ | --------------------------- | -------------------------- |
| Hook           | headline left, air right | headline top, air below     | headline upper, air below  |
| Product plate  | full-bleed or inset      | inset, cropped vertically   | inset, square crop         |
| Two-column     | side by side             | stacked, text first         | stacked                    |
| Detail crop    | 4:3 or 1:1 inset         | full width                  | full width                 |
| Number plate   | left figure, right label | figure above label          | figure above label         |
| Closing        | centred                  | centred, tighter            | centred                    |

## Approved Entities

Only what the repository shows: Kenyalang Ledger, Kenyalang Hardware & Supply (seeded demo tenant),
SYARIKAT CHUN HING HARDWARE (the photographed supplier), AutoCount, SQL Account, LHDN MyInvois.
No other logos, customers, or vendor marks. Never imply endorsement by LHDN or by any accounting
vendor.

## Numerals & Claims (hard rule)

Every number on screen traces to the seeded demo data or the repository:

- Grand total **RM 265.00**; subtotal **RM 265.00**; SST **RM 0.00**.
- Line items: Minyak Hitam 4L 1 × 120.00 = 120.00; Spark Plug 4 × 15.00 = 60.00;
  Opah Pasang 1 × 35.00 = 35.00; Minyak Gear 2 × 25.00 = 50.00.
- Invoice date **12/10/2026**; supplier SST **Y24-1808-31015655**; BRN **200401032489 (665243-X)**.
- No performance claims, no time savings, no accuracy percentages, no customer counts.

## Pre-Render Self-Audit

- **Squint** — one dominant element per frame.
- **Silence** — declarative frames 50–60% empty.
- **Palette** — paper, ink, taupe, one green. No blue, no cyan.
- **Lines** — every separator is 1px taupe; one ink rule at most.
- **Type** — Garamond 500 sentence case; mono labels tracked; ≥1.4cqw for anything load-bearing.
- **Depth** — no shadow, no gradient, radius ≤2px.
- **Fabrication** — every numeral traces to the demo data or the repo.
- **Legibility** — the UI plate is readable, or it is cropped until it is.

## Known Gaps

- Motion is out of scope here; it is specified per frame in the shot sequence.
- The product has no logo lockup beyond the hornbill SVG; the film uses a typographic wordmark.
- 9:16 and 1:1 are guidance; only 16:9 is built.
