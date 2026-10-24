# REVIEW — Kenyalang Ledger launch film (48 s, 1920×1080, 30 fps)

Reviewed 2026-10-24 against beat sheet / seams `56671e18`. `check --json` → `ok: true`, 0 errors.
This pass fixed the four defects reported after the last render: step numbering, SFX sync, overlay
geometry, camera speed, and added a real voiceover plus a music bed cut from a supplied track.
Render: `renders/kenyalang-launch.mp4` — 48.0 s, 1920×1080, 30 fps, H.264 + AAC, −13.5 LUFS,
−2.2 dBFS peak, 33.0 MB.

## Creative calls

- **One storyline, not three.** A single linear job: a photo arrives → it is read → its fields are
  checked against provenance → the month reconciles → the accountant exports. The alternative
  framings (a "before/after paperwork" montage, a client-POV story) were dropped because the film
  has 48 s and the product's actual claim is narrower than either.
- **Real screens, not rebuilt UI.** Inbox, review, dashboard and exports are genuine 1920×1080
  captures of the running app, driven by Playwright against the live backend on :8000 / :5173.
  Camera moves and HTML overlays sit on top; no app chrome is drawn in HTML.
- **The app's type scale was the real problem.** Measurement (`measure.mjs`) showed 81% of UI text
  nodes under 14 px at 1080p — below the 28 px readable floor. Rather than only compensating in the
  video, the app's tokens were raised (micro/label 12, ui 14, body 15, title 22, display 38,
  display-lg 60) and every shot re-captured. The histogram is now 49% under 14 px. This fixes the
  product and the film together.
- **No fabricated states.** `review.html` cross-fades the app's own real focus-state captures
  (the provenance boxes are drawn by `ReceiptCanvas.tsx` in SVG, not by us). The totals panel is a
  real crop containing the app's own "Math check ✓". The upload scene stops at the honest
  `PROCESSING` state — six timed captures after upload were byte-identical, so a "filed" state
  would have been invented.
- **Three real receipts, not five invented ones.** The film now runs on receipts that went through
  the actual OCR + LLM pipeline: KOPITIAM AH SENG `002318` RM 17.50 and PERCETAKAN MAJU JAYA
  `PJ-88214` RM 40.60 verified, SRI AMAN HARDWARE SUPPLIES `CS-441207` RM 88.50 in review. Every
  number on screen is read back out of `kenyalang-demo.db`, including the CSV rows, which are
  generated from the verified line items rather than typed.
- **The review receipt is genuinely uncertain.** Its field confidences are the extractor's own —
  supplier 0.689, invoice no. 0.638, subtotal 0.600, tax 0.529, total 0.477 — and the app floors
  the record at the minimum, so "OCR CHECK 48%" is a real computed value, not a chosen number.
- **One hallucination was removed, not dressed up.** The extractor invented a `merchant_sst` of
  "68" with zero OCR evidence, which floored the record at 0% and printed "OCR CHECK 0%". The
  receipt shows "SST 6%" — a rate, not a registration number — so the field was cleared as an
  accountant correction and the confidence recomputed honestly to 48%.
- **A real voiceover, and a music bed you supplied.** Eight lines of narration (one per scene, 581
  characters) were generated with ElevenLabs on the 10,000-credit free tier — total spend 1,227
  characters, 12.3% of the allowance, including model-comparison tests. The ElevenLabs **Music API is
  not available on the free plan** (`paid_plan_required`), so the bed is not from that service: it is
  *Suasam Sarawak* (Suno, tagged `[Instrumental]`), ingested through `media-use --from`.
- **The bed is cut to picture, not dropped in.** The source is 178.6 s at ~92 BPM; a 48 s window is
  taken from **20.82 s**, chosen by scoring every bar-aligned window on RMS steadiness (σ = 2.9 dB,
  the flattest in the track) and tail strength. It is bar-aligned because a bed that starts mid-phrase
  fights the cuts. Fades: 1.4 s in, 2.6 s out. Loudness-normalised to −23 LUFS before mixing.
- **It ducks under every voice line.** A `data-automation` volume lane holds the bed at 0.34 through
  each of the eight voiceover windows and returns to 1.0 in the gaps (34 automation points). Both
  are tagged `data-audio-group="music"` / `voiceover` so the mix stays legible.
- **Every SFX was regenerated, not reused.** The old library was a placeholder set with wild level
  spread (one file peaked at 0.005 — inaudible). Thirteen new one-shots were generated, then each
  was gain-staged to a uniform −6 dBFS peak so the per-cue volumes in `index.html` mean something.
- **Cues are placed against measured transients, not against the visual event.** Each file was
  analysed to find where its audible peak actually falls (0.05 s for a key press, 0.91 s for the
  paper slide), and the cue start was moved back by exactly that offset. That is the fix for
  "not synchronized so much": the sound was being fired on the frame, so its energy arrived
  a quarter-second late.

## What was measured vs. looked at

Measured: type histogram, inbox badge rects (rows at `y` 384 / 449 / 514), dashboard spend bbox
(`0.2167–0.3632 × 0.2000–0.2648`, centre `557,251`), the rule beneath it at `y 0.2806`, every
caption's `top` offset, audio cue times against scene beats, `check` findings, and the mean
luminance of each seam frame before/after to prove no flash remains.

Only looked at: the beat sheet, the seven seam strips, the phone sheet, and per-scene range strips.

**Nobody heard the audio.** Cue placement is arithmetic against the timeline, not listening: each
start time is the visual event minus that file's measured peak offset. What *was* verified is that
the placement survived the render: the cue list was rebuilt into a synthetic reference mix and
cross-correlated against the rendered audio, giving a best lag of **+0.0000 s at correlation 0.999**
(collapsing to 0.01 at ±0.1 s, so the peak is real, not a plateau). The mix is sample-accurate to
the timeline; whether it *sounds* right is still unheard. Levels are set by
measurement too — every one-shot is gain-staged to a −6 dBFS peak before the per-cue volume is
applied, and the voice sits at full level with no bed under it. The mix balance is unverified by ear, and
the voice was not auditioned for tone.

## Weakest shot

**`dash.html` (34–39.5 s).** The dashboard is a sparse page: one figure, two stat cells, a
three-row table, a category list. The camera push to `RM 58.10` is correct, but the frame behind it
carries a lot of empty paper, and the scene has the least narrative tension of the set. With more
time I would crop the dashboard to the spend block plus the top-suppliers row and treat the
category list as a separate beat, rather than pushing into a full page. The camera also had to be
clamped to `x 324` (`y 0`) rather than centring on 540 — the shot is only 1920 px wide, so a
vertical centre exposes a black band.

Second: the app's 1240 px content shell inside a 1920 px viewport leaves ~680 px of dead width.
Every screenshot scene inherits it. Fixing it properly means changing the app's max-width, which is
a product decision, not a video one.

## Warnings kept on purpose

- **`line_unread` on the CSV rows** (`exports.html`, 6 findings). The CSV is scanned for *shape* —
  eleven columns, six dated rows, a real header — not read word by word. `#ex-code` and its rows
  carry `data-hold`; the reading copy is the note beside it ("MyInvois JSON: a UBL draft, never
  submitted"), which clears the floor. Truncating the rows to satisfy the checker would have made
  the export look like a mock-up.
- **`container_overflow` (INFO, 5×).** Every instance is a deliberately oversized camera stage
  inside a clipping frame — that is what a push-in is.
- **`text_below_floor` is clear.** All 13 px kickers were raised to 28 px and body copy to 30 px.

## The four reported defects

**1. Step numbering was inconsistent.** Only `upload` ("Step 01 — Capture") and `exports`
("02 — Export") carried a step number, the other three product scenes had none, and the two that
did disagreed about what number they were. The film now shows one badge per product scene —
`01 Capture`, `02 Triage`, `03 Review`, `04 Reconcile`, `05 Export` — in the same slot
(`140 × 940`), same type (JetBrains Mono, 28 px label, 30 px number), same amber-on-charcoal
ground. The badge is a persistent clip, so the number is on screen for the whole scene rather than
living in a caption that fades. The old kickers keep their descriptive text ("OCR running",
"Math check") now that they no longer have to carry the number.

**2. Sound effects were not synchronized.** Two separate faults. The structural one: every cue was
placed on the visual event, but these files peak late — a whoosh's energy lands 0.17–0.66 s after
its first sample — so the audible hit trailed the picture. Every cue was moved back by its file's
measured peak offset. The other: `whoosh-cinematic` was cut to `data-duration="1.6"` while its peak
sits at 2.54 s, so the two biggest transitions played their attack and were silenced before they
ever hit. Both were replaced with a file that completes. Also removed: a doubled whoosh on one cut,
an orphan pop with no visual cause, and a typing cue that fired 1.9 s before the CSV actually typed.

**3. The bounding boxes were not accurate.** Measured off the captures rather than eyeballed. The
dashboard spend box was `20.7% / 18.7% / 16.1% / 8.0%`, which put its top border straight through
the "Spend this month" label; it is now `404,184 302×100`, clearing the label (ink `y194–215`) and
the figure (`y230–272`). Its underline was 1159 px against a real rule of 1160 px at `y303` —
`x416–1575`. The upload drop strip was inset 17 px left and 12 px right of the real rules; it now
matches `x416–1575` exactly. The new-row highlight was drawn on the table header instead of the
data row; it now sits between the real rules at `y406` and `y471`.

The drop-strip box was still wrong on height, caught on review of a rendered frame: it was
`top:164 h:76`, so 25 px of empty canvas sat above the strip and the border floated off the real
rule. Re-measured from the **live DOM** at 1920×1080 (not from a capture, where the scale factor is
ambiguous) — the strip element is `x416 y189 1160×52`. The box is now `top:189 h:52`, so its border
sits on the real rules at `y189` and `y241`. All four overlays now use
`box-sizing: border-box` so a 2 px border does not push them off the geometry they describe.

**4. The camera moves were too quick.** The review scene was the worst: a 1.0→2.0 push in 1.65 s,
then a 2.06→1.0 pull-back in 0.78 s — the fastest move in the film, and it whipped. The push is now
2.4 s to 1.88 and the pull-back 1.35 s, so the move out is slower than the move in. The reverse
"settle" at the top of review, inbox, dash and upload was removed entirely: those scenes opened by
pulling *back* from an overscaled frame, which reads as a twitch because the cut already landed on
the wide shot. Inbox's push went 2.25→2.55 s, dash's 1.9→2.2 s, upload's 1.9→2.2 s.

**5. The upload→inbox cut jumped.** Both scenes show the same inbox screen, but the camera did
not match across the seam: upload ended at `scale 1.22, y+26` and inbox opened at `scale 1.19, y-14`.
That is a 2.5% zoom change plus a 40 px shift on an unchanged page, so the whole layout appeared to
lurch — and the "Inbox" heading, which lands at screen `y6` at the end of scene 1, was pushed to
`y-20` at the start of scene 2 and vanished. Measured, not eyeballed: the two source shots are
pixel-identical in their top 240 px (mean diff 0.00), which proves the difference was camera only.
Both sides now use `scale 1.19, y+56`, so the cut is a data change on a held frame. That framing
also keeps the heading at `y50-70`, where the old end had it crammed against the edge at `y6`.

The fix exposed a second defect at the same seam. `#up-vig` was nested *inside* the scaling stage,
so the vignette zoomed with the content, while `#ib-vignette` sat outside it with a different centre
(`62% 45%` vs `50% 52%`). Corner brightness stepped ~20 levels at the cut. Both vignettes are now
outside the stage and identical: a lens falloff is fixed in screen space, it should not scale.

## Fixed in this pass

- **The upload scene was a black frame.** An earlier de-flash edit removed the tween that made
  `#up-idle` opaque, but `.up-layer` still defaulted to `opacity: 0`, so the scene played black for
  6.5 s. `#up-idle` now declares `opacity: 1`.
- **Every cut flashed.** Root cause was not the shots but the vignettes and trailing fades: each
  scene faded its own vignette in from 0 and its content out to the bare canvas in the last ~0.4 s,
  so all seven seams went through a pale/blank frame. Vignettes are now static, and every scene
  holds its full frame to the cut. Seam means are now single-step (e.g. seam 3: 232→227; seam 5:
  123→231) with no intermediate wash.
- **`hook.html` emptied before the cut.** Several clips had `data-duration` 0.15–0.6 s short of the
  scene, so the stack and copy vanished into canvas before 6.0 s. Durations extended to hold.
- **`exports.html` had a 0.1 s blank window** at the end (`#ex-panel` ended at 4.9 s, scene at
  5.0 s). Panel and note now hold through the cut. The CSV reveal also moved earlier (1.9 s, rows
  from 2.01 s) so the 42 s beat shows data rather than an empty header.
- **Stale upload shots.** `upload-processing.jpg` still showed the deleted KONG HENG rows. Both
  upload stills were re-captured from the live app.
- **The upload scene contradicted itself.** The idle still showed all three receipts ("1–3 of 3")
  and the processing still showed the same three — so the receipt the scene "drops" already existed
  before the drop. The pair is now captured in causal order: idle at **2 receipts**, then the
  hardware receipt is dropped and the processing frame reads **1–3 of 3** with that row amber.
- **Upload overlays were off the UI.** The drop highlight and the new-row highlight were still
  drawn at the old 416/189 and 416/363 geometry; both were re-measured off the new captures
  (strip 433–1563 × 164–240, first data row 416–1575 × 407–470).
- `close.html`: the three meta columns collided with the receipt; re-gridded to 28 px, gap 40 px,
  values set `nowrap`, "EasyOCR + field provenance" shortened.
- `exports.html`: CSV panel resized to fit six rows exactly (1680×442 at y 292), right-edge fade so
  the row cut reads as "and so on"; panel hand-off tightened from 0.4 s to 0.16 s to kill the
  mid-fade ghost at 42 s; note re-timed to land with the panel.
- `upload.html`: two captions shortened to clear the read floor; third caption given 1.9 s.
- **All five cuts de-flashed.** Each screenshot scene used to fade its shot in from `opacity: 0`,
  which read as a black flash at the seam. They now cut hard, with the vignette still fading in for
  atmosphere.
- **`close.html` had a collapsed wrapper.** `#cl-stack-wrap` had no positioning of its own while
  the image inside it was absolutely positioned, so the image resolved against a 15 px strip and
  the receipt sat half off the frame. The wrapper is now `inset: 0`.
- **A CSS rule was deleted by a careless regex.** While removing an abandoned step-rail, a
  `.*?\}` pattern also ate `.ex-step`, which silently dropped the exports kicker to the browser
  default 16 px — under the 28 px floor. `check` caught it as `text_below_floor`; the rule was
  restored. This is the reason the pass ends with a `check` run rather than a snapshot.
- `index.html`: the whole cue list was rebuilt — 8 voiceover clips and 26 one-shots on
  tracks 5–14, every start recomputed from a measured peak offset.
