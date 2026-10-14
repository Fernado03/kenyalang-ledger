# Brag Plan: Kenyalang Ledger

## What is this app?
An invoice and receipt digitizer tailored for Malaysian micro-SMEs and freelance accountants, bridging faded thermal receipts, handwritten Kuching chits, and WhatsApp photo dumps with LHDN MyInvois e-invoicing compliance and accounting software exports.

## The angle
Deadpan fintech precision applied to faded kopitiam chits and hardware store receipts. While enterprise software assumes structured digital bookkeeping and manual entry costs 4 hours per client, Kenyalang Ledger brings Bloomberg Terminal-grade density and penny-level math verification to WhatsApp receipt photo dumps and local Manglish items (*kopi c peng*, *minyak hitam*).

## Hook (first 2-3 seconds)
The stark paper reality: A client dumps 120 blurry receipt photos into WhatsApp at month-end, right as the LHDN MyInvois mandate requires structured, penny-verified line items.
- Line 1: "Clients dump 120 blurry thermal chits into WhatsApp."
- Line 2: "And LHDN requires every single line item verified."

## Key moments (the middle)
- **Computer Vision & Manglish OCR:** Faded receipt text sharpened by CLAHE contrast recovery, normalized bounding boxes snapping onto local Malaysian business identifiers (BRN, SST) and bilingual items like *kopi c peng*.
- **High-Density Review Console:** Split-pane accountant workspace with canvas pan/zoom, bounding box highlighting, and tabular Ringgit numerals.
- **Deterministic Math Reconciliation:** The live math audit strip recalculates in real-time, flashing from warning state to verified emerald: `✓ Math Matches — Subtotal RM 13.68 + SST RM 0.82 = RM 14.50`.

## Outro / punchline
Dual one-click compliance export: LHDN MyInvois v1.1 Consolidated JSON + AutoCount / SQL Account CSV generated instantly. "From WhatsApp dump to tax compliance in under 10 seconds."

## User flow worth showing
1. **Entry:** WhatsApp receipt photo dump (120 chits) / faded thermal receipt uploaded into the review inbox.
2. **Key action:** High-density review console highlights line items, corrects low-confidence token, math banner verifies penny-level subtotal + SST balance.
3. **Result:** One-click generation of validated LHDN MyInvois v1.1 JSON and accounting journal CSV.

## Tone
- Preset: `yc-parody`
- Creative direction: Deadpan fintech launch for local Sarawak micro-commerce
- Interpretation: Serious, razor-sharp, matter-of-fact delivery. The humor comes from applying ultra-rigorous accounting engineering to shoebox cash chits and WhatsApp photo dumps.

## Format: landscape — 1920x1080
## Duration: 18.5s

## Visual identity (from the project)
- Background: `#F8FAFC` (Slate 50 canvas) / `#0F172A` (Slate 900 for dark contrast moments)
- Surface: `#FFFFFF` (Pure White) and `#F1F5F9` (Slate 100)
- Accent / Brand: `#134E4A` (Sarawak Hornbill Teal 900) & `#14B8A6` (Teal 500)
- Borders: `#CBD5E1` (Slate 300)
- Text Primary: `#0F172A` (Slate 900)
- Text Secondary: `#475569` (Slate 600)
- Verified: `#ECFDF5` (bg) / `#10B981` (border) / `#065F46` (text)
- Warning: `#FFFBEB` (bg) / `#F59E0B` (border) / `#92400E` (text)
- Mismatch: `#FEF2F2` (bg) / `#EF4444` (border) / `#991B1B` (text)
- Display font: `Inter`, system-ui, sans-serif
- Body / Numbers font: `JetBrains Mono`, monospace (with tabular-nums lining-nums)
- Strongest visual element: The high-density split-pane review console with bounding-box canvas overlay and the emerald Math Reconciliation banner.

## Share copy (draft)
Clients dump 120 blurry thermal chits into WhatsApp at month-end. Kenyalang Ledger recovers faded paper, parses local Manglish items like "kopi c peng", and generates penny-reconciled LHDN MyInvois e-invoices in under 10 seconds.

## Audio direction
- Role: Warm business bed with crisp UI interaction accents and a confident verified payoff.
- Music: `happy-beats-business-moves-vol-11-by-ende-dot-app.mp3`
- Music treatment: Starts at 0.0s, steady volume at 0.32, subtle fade under final logo punchline.
- Music cue guidance: Preset cue file at `<skill-dir>/assets/music/cues/happy-beats-business-moves-vol-11-by-ende-dot-app.music-cues.json`. Key strong cues: 1.60s (hook slam), 3.70s (transition to CV pipeline), 8.96s (review console math match), 12.65s (export card pop), 17.91s (outro logo hold).
- Audio-reactive treatment: Subtle; use music RMS/bass to gently warm the Teal brand card borders and verified status glow.
- SFX posture: Moderate, crisp UI and interaction clicks matching button focus and math resolution.
- Audio-coupled moments:
  - 1.60s: Hook highlight arrival (`impactSoft_medium_001.ogg`)
  - 4.75s, 5.80s, 6.86s: Bounding box locks (`interface/switch_001.ogg`)
  - 10.01s: Editor click (`ui/mouseclick1.ogg`)
  - 11.06s: Math verified chime (`impactBell_heavy_000.ogg` + `interface/drop_001.ogg`)
  - 14.76s: Export card slide (`casino/card-slide-1.ogg`)
- Restraint rule: No cartoon whooshes, no harsh buzzers; maintain serious fintech dignity.

## Storyboard

### Scene 1 — The Paper Reality — 3.7s
- **Visual:** Clean Slate canvas. A simulated faded thermal receipt Chit ("KIM GUAN HARDWARE") appears beside a WhatsApp chat badge ("120 receipt photos received").
- **Headline:**
  Line 1: "Clients dump 120 blurry thermal chits into WhatsApp."
  Line 2: "And LHDN requires every single line item verified."
- **Sequential/interaction:** Faded chit card slides in, WhatsApp message badge pops up, headline settles cleanly.
- **Audio intent:** Dry, understated setup establishing the local dilemma.
- **Audio-coupled idea:** Subtle soft landing hit at 1.60s strong beat (`impactSoft_medium_001.ogg`).
- **Music:** `happy-beats-business-moves-vol-11-by-ende-dot-app.mp3` establishing steady groove.
- **Transition mood:** Clean cut at 3.70s → Scene 2.

### Scene 2 — CV & Localized Token Extraction — 5.26s (3.70s – 8.96s)
- **Visual:** CV Preprocessing & EasyOCR engine in action. The faded receipt contrast is restored via CLAHE. Green/teal normalized bounding boxes snap across fields: `MERCHANT: Kim Guan Hardware`, `BRN: 202001012345`, `SST: W10-1808-32000018`.
- **Items highlighted:** `PVC PIPE 2"` (RM 14.50) and `KOPI C PENG` (RM 2.80).
- **Sequential/interaction:** 3 bounding boxes snap consecutively onto the receipt coordinates.
- **Audio intent:** Precision, technical competence.
- **Audio-coupled idea:** Crisp UI switch/clicks on bounding box locks (`interface/switch_001.ogg` at 4.75s, 5.80s).
- **Music:** Rhythm driving forward across beat grid.
- **Transition mood:** Fast slide wipe at 8.96s → Scene 3.

### Scene 3 — Review Console & Penny-Level Math Reconciliation — 5.54s (8.96s – 14.50s)
- **Visual:** The full high-density Accountant Review Console. Left: Pan/zoom canvas with receipt bounding box. Right: High-density line items editor with tabular numerals.
- **Action:** A row with quantity `1` and amount `RM 13.68` updates tax `RM 0.82`. The MathBanner snaps from warning amber to crisp emerald:
  `✓ Math Matches — Subtotal RM 13.68 + SST RM 0.82 = RM 14.50`
- **Sequential/interaction:** Accountant cursor focuses line item, digit updates, Math Banner flips to verified emerald state with a checkmark badge.
- **Audio intent:** Immensely satisfying accounting catharsis.
- **Audio-coupled idea:** Mouse click (`ui/mouseclick1.ogg`) at 10.01s, followed by the emerald match chime (`impactBell_heavy_000.ogg` + `interface/drop_001.ogg`) at 11.06s.
- **Music:** Continues at full energy.
- **Transition mood:** Snappy cut at 14.50s → Scene 4.

### Scene 4 — Dual Compliance Export & Outro — 4.0s (14.50s – 18.50s)
- **Visual:** Two export action cards slide in:
  1. `LHDN MyInvois v1.1 Consolidated JSON` (Valid XML/JSON Schema)
  2. `AutoCount & SQL Account Purchase Journal CSV`
- **Punchline / CTA:**
  **Kenyalang Ledger**
  *Invoice & receipt digitizer for Malaysian micro-SMEs & freelance accountants.*
  "From WhatsApp dump to tax compliance in under 10 seconds."
- **Sequential/interaction:** Export cards pop in at 14.76s and 15.28s, Kenyalang Ledger hornbill teal brandmark locks in center.
- **Audio intent:** Confident resolution.
- **Audio-coupled idea:** Card slides (`casino/card-slide-1.ogg`), gentle outro finish.
- **Music:** Clean fade out to 18.50s.

**Music mood for this video:** Warm, business-y, confident startup groove (`happy-beats-business-moves-vol-11-by-ende-dot-app.mp3`).
**Audio summary:** Starts on a clean corporate bed, punctuates CV token detection with precise clicks, celebrates penny-level math verification with a clear chime, and resolves on a dual-export brand card.
