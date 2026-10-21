---
workflow: product-launch-video
flow: automation
storyboard: no
message: "Photograph the receipt. Ship the journal."
destination: web
aspect: 1920x1080
language: en
audience: "Malaysian micro-SME owners and the freelance accountants who keep their books"
length: 32s
angle: demo
style_preset: cartesian
---

## Intent

A launch and demo film for **Kenyalang Ledger**, a receipt digitizer and accounting review
workspace for Malaysian micro-SMEs and freelance accountants. The audience is the hardware-shop
owner with a shoebox of thermal receipts and the bookkeeper who has to key every one of them in
twice. The film should feel like the product itself: warm paper, deep green ink, hairline rules,
nothing shouting. Confident and quiet, closer to a well-set ledger page than a SaaS launch ad.

The core argument is not "we have OCR". It is that the review step is where trust is won or lost:
every extracted field can be traced back to the pixels it came from, and the arithmetic is checked
by code before anything is exported.

## Assets

- `.tmp-shots/inbox-2x.png` — real inbox with async processing rows (3840×2160).
- `.tmp-shots/review-focus-2x.png` — review console with the provenance box lit on the scan (3840×2160).
- `.tmp-shots/exports-2x.png` — real export screen: accounting CSV + MyInvois draft JSON (3840×2160).
- `.tmp-shots/dashboard-2x.png` — verified-only monthly spend dashboard (3840×2160).
- `.tmp-shots/clients-2x.png` — client workspace index (3840×2160).
- `backend/storage/tenants/.../receipt.jpg` — the actual photographed thermal receipt behind the demo record.
- `frontend/public/favicon-hornbill.svg` — the hornbill mark.

All UI plates are captures of the running application at 2× device scale, driven against the
seeded demo tenant. No screen in this film is a mockup.

## Customizations

- Numbers on screen must match the seeded demo data exactly: RM 265.00 grand total, four line
  items, RM 120.00 + RM 60.00 + RM 35.00 + RM 50.00, SST RM 0.00.
- Show the provenance overlay as a real product behaviour, not decoration.
- Name the export targets plainly (AutoCount / SQL Account CSV, MyInvois-shaped draft JSON) and
  keep the draft/not-submitted qualifier visible, because the README is explicit about it.

## Notes

- This is a portfolio demo, not a hosted service: the CTA is "run it locally", never "sign up".
- Do not claim LHDN certification, PDPA compliance, or any customer/testimonial. The repo states
  these are out of scope.
- No narration provider is signed in and no local TTS engine is installed; the film must read
  completely on mute, with on-screen type carrying the argument.
- Brand ground is warm paper `#F6F1E7`, ink `#171A18`, primary green `#0B3F3A`, UI accent
  `#147A6C`. Hairline rules only, 2px radius, no drop shadows on content.
