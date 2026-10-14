# Hyperframes Composition Brief: Kenyalang Ledger

## Objective
Create a short launch-style brag video for Kenyalang Ledger.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 18.5 seconds

## Source Material
- Project root: `.`
- Primary files read: `README.md`, `frontend/index.html`, `frontend/tailwind.config.js`, `frontend/src/pages/ReviewPage.tsx`, `frontend/src/components/MathBanner.tsx`, `docs/01_business_case.md`, `docs/04_ui_specs.md`
- Product name: Kenyalang Ledger
- Tagline / strongest claim: "Invoice and receipt digitizer tailored for Malaysian micro-SMEs and freelance accountants with LHDN MyInvois compliance."
- Key UI or visual moment to recreate: The High-Density Review Console with thermal receipt canvas, bounding box overlay, tabular Ringgit numerals, and the Math Reconciliation banner switching to verified emerald (`✓ Math Matches`).
- Copy that must appear verbatim:
  - "Global receipt scanners charge in USD. And fail completely on *kopi c peng*."
  - "LHDN MyInvois v1.1 Consolidated JSON"
  - "AutoCount / SQL Account Purchase Journal CSV"
  - "Math Matches — Subtotal RM 13.68 + SST RM 0.82 = RM 14.50"
  - "Kenyalang Ledger"

## Creative Direction
- Tone preset: `yc-parody`
- Creative direction: Deadpan fintech launch for local Sarawak micro-commerce
- Interpretation: Serious, razor-sharp, matter-of-fact delivery. The humor comes from applying ultra-rigorous accounting engineering to shoebox cash chits and WhatsApp photo dumps.
- Angle: Deadpan fintech precision applied to faded kopitiam chits and hardware store receipts. While enterprise software assumes clean PDFs and global scanners choke on Manglish, Kenyalang Ledger brings Bloomberg Terminal-grade density and penny-level math verification to "Kopi C Peng" and "Minyak Hitam".
- Hook: The stark paper reality: A crumpled, faded thermal chit and a WhatsApp photo dump with the deadpan observation: "Global receipt scanners charge in USD. And fail completely on *kopi c peng*."
- Outro / punchline: "From WhatsApp dump to tax compliance in under 10 seconds."
- Avoid:
  - Generic SaaS language ("streamline your workflow", "boost productivity")
  - Abstract filler visuals (generic floating 3D shapes or purple gradients)
  - Unrelated visual redesign (must strictly follow Slate 50 canvas + Sarawak Hornbill Teal `#134E4A` palette with JetBrains Mono numbers)

## Visual Identity
- Background: `#F8FAFC` (Slate 50) and `#0F172A` (Slate 900 for high-contrast accents)
- Text: `#0F172A` (Primary), `#475569` (Secondary), `#94A3B8` (Muted)
- Accent: `#134E4A` (Hornbill Teal 900), `#14B8A6` (Teal 500)
- Surface: `#FFFFFF` (Pure White), `#F1F5F9` (Slate 100)
- Verified: `#ECFDF5` (bg), `#10B981` (border), `#065F46` (text)
- Warning: `#FFFBEB` (bg), `#F59E0B` (border), `#92400E` (text)
- Display font: `Inter`, system-ui, sans-serif
- Body / Numbers font: `JetBrains Mono`, monospace (with tabular-nums lining-nums)
- Visual references from the project: High-density Review Console split-pane, MathBanner emerald status strip, status pills, and LHDN export cards.

## Storyboard
Use the storyboard in `brag-output/brag-plan.md` as the creative contract.

Scene summary:
1. Scene 1 — The Paper Reality — 3.7s — Faded thermal receipt and WhatsApp 120-photo dump with the kopi c peng hook.
2. Scene 2 — CV & Localized Token Extraction — 5.26s (3.7s – 8.96s) — CLAHE contrast recovery, normalized bounding boxes snapping to BRN, SST, and local item names.
3. Scene 3 — Review Console & Math Reconciliation — 5.54s (8.96s – 14.5s) — Full split-pane UI, active row focus, MathBanner snaps from amber to emerald `✓ Math Matches`.
4. Scene 4 — Dual Compliance Export & Outro — 4.0s (14.5s – 18.5s) — LHDN MyInvois JSON and AutoCount CSV export cards, Kenyalang Ledger brand mark.

## Audio
- Audio role: Warm business bed with crisp UI interaction accents and a confident verified payoff.
- Audio arc: Begins with steady rhythm, layers in precise bounding box clicks, peaks at the verified math reconciliation chime, and settles smoothly on the export cards.
- Music: `assets/music/happy-beats-business-moves-vol-11-by-ende-dot-app.mp3`
- Music treatment: Starts at 0.0s, volume 0.32, steady groove, gentle fade under final logo.
- Music cue guidance: Preset cue file at `<skill-dir>/assets/music/cues/happy-beats-business-moves-vol-11-by-ende-dot-app.music-cues.json`. Strong cues: 1.60s (hook slam), 3.70s (scene 2 cut), 8.96s (scene 3 cut), 12.65s (scene 4 export reveal), 17.91s (outro hold).
- Audio-reactive treatment: Subtle; use music bass/RMS to gently breathe warmth into the teal brand card borders and verified status glow.
- Audio-coupled moments:
  - 1.60s: Hook highlight arrival (`assets/sfx/impact/impactSoft_medium_001.ogg`)
  - 4.75s, 5.80s: Bounding box locks (`assets/sfx/interface/switch_001.ogg`)
  - 10.01s: Editor click (`assets/sfx/ui/mouseclick1.ogg`)
  - 11.06s: Math verified chime (`assets/sfx/impact/impactBell_heavy_000.ogg` + `assets/sfx/interface/drop_001.ogg`)
  - 14.76s: Export card slide (`assets/sfx/casino/card-slide-1.ogg`)
- SFX selection guidance: Crisp UI and interaction clicks matching button focus and math resolution. Restrained, professional, high-fidelity.
- Audio files: Copied into `brag-output/composition/assets/`.
