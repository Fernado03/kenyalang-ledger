# Kenyalang Ledger — Step 1: Business Case & Commercial Strategy

## 1. Executive Summary & Strategic Business Case

### 1.1 Document Metadata

| Field | Value |
|---|---|
| Project Name | Kenyalang Ledger (Invoice & Receipt Digitiser) |
| Target Audience | Kuching micro-SMEs (end-users) & Freelance Accountants / Small Audit Firms (economic buyers) |
| Document Phase | Step 1 of 8 — Commercial Foundation & Business Case |
| Core Value | Convert messy paper receipts and WhatsApp photos into verified, structured line items and LHDN MyInvois-ready exports in under 10 seconds. |

### 1.2 The Core Problem

- **The Regulatory Squeeze:** Malaysia's LHDN MyInvois mandate is cascading down to all business tiers. Even exempt micro-SMEs must supply valid transaction data to B2B customers who require e-invoices for tax deductions.
- **The Kuching Paper Reality:** Local hardware stores, workshops, car washes, and eateries in Sarawak run on thermal paper receipts, carbon-copy handwritten chits, and cash transactions stored in shoeboxes.
- **The Data Handoff Friction:** Micro-SME owners dump batches of blurry receipt photos into WhatsApp chats with their freelance accountants at month-end.
- **The Software Gap:**
  - Enterprise/SME suites (AutoCount, SQL Account, Xero) cost RM 1,200–3,000+/year and assume structured digital bookkeeping.
  - Global receipt scanners (Dext, Expensify) charge in USD, fail completely on Manglish/Bahasa Melayu terms (e.g., "kopi c peng", "upah pasang", "minyak hitam"), and lack LHDN MyInvois schema exports.
- **Incumbent Solution:** The freelance accountant's junior clerk manually typing every single line item into Excel.

### 1.3 Value Proposition

```
┌──────────────────────────────────────┐     ┌──────────────────────────────────────┐
│       Micro-SME (Hardware/F&B)      │     │  Freelance Accountant / Small Firm   │
├──────────────────────────────────────┤     ├──────────────────────────────────────┤
│ • Pitch: "Stop losing tax deductions"│     │ • Pitch: "Cut data-entry time by 80%"│
│ • Snap photo via web/mobile          │     │ • Multi-client management console    │
│ • No complex accounting jargon       │     │ • Bulk upload 100+ receipts at once  │
│ • Instant monthly spend visibility   │     │ • Clean Excel & MyInvois JSON export │
└──────────────────────────────────────┘     └──────────────────────────────────────┘
```

**Quantified ROI for Freelance Accountants:**

- Status Quo: 1 client with 120 receipts ≈ 3.5 to 4 hours of manual data entry and invoice matching.
- With Kenyalang Ledger: Batch upload → automated OCR + LLM parse → 15 minutes of human review via keyboard shortcut UI.
- Direct Saving: Frees up ~3.5 hours per client per month, allowing a solo practitioner to double their client capacity without hiring extra clerks.

### 1.4 Market Sizing & Local Wedge

- **Total Addressable Market (TAM):** 1.17M MSMEs in Malaysia navigating digital compliance and accounting automation.
- **Serviceable Available Market (SAM):** ~65,000 registered micro-SMEs and ~1,200 freelance bookkeepers/accounting firms across Sarawak (Kuching, Miri, Sibu, Bintulu).
- **Serviceable Obtainable Market (SOM - 12 Months):**
  - 25 freelance accounting firms / solo bookkeepers (managing 20–40 clients each).
  - 150 direct micro-SMEs in the Kuching urban core.

**The Unfair Local Advantage:**

- **Manglish & Local Lexicon Support:** Trained/prompted to parse mixed Sarawakian/Malaysian receipts (SST registration numbers, handwritten chits, bilingual item names).
- **Direct On-the-Ground Trust:** Face-to-face onboarding in Kuching. In local commerce, personal relationships outperform remote SaaS marketing.
- **Accountant Distribution Flywheel:** Selling to 1 freelance accountant immediately unlocks 20 to 50 micro-SMEs without separate consumer acquisition costs.

### 1.5 Commercial Model & Unit Economics

| Metric | Target Value | Strategic Justification |
|---|---|---|
| Micro-SME Tier | RM 39 / month | Low friction, impulsively affordable for a single shop; includes 100 scans/mo. |
| Accountant Tier | RM 249 / month | Multi-client workspace (up to 15 client profiles), 1,000 scans/mo, bulk processing. |
| Additional Scans | RM 0.15 / scan | Over-quota pay-as-you-go rate. |
| Blended CAC | < RM 80 | Direct cold outreach to local Kuching audit firms + word-of-mouth referral. |
| Accountant LTV | RM 2,988 | Assumes 12-month minimum retention (accounting workflows are sticky). |
| LTV : CAC Ratio | > 30 : 1 | High leverage due to B2B accountant-as-distributor model. |
| Target Gross Margin | > 82% | Self-hosted EasyOCR/OpenCV preprocessing handles text bounding boxes; LLM is only called on extracted text snippets to minimize token costs. |

### 1.6 Stage-Gate 1 Sign-Off Criteria

Before writing code for Step 2 (PRD), verify these validation checkpoints:

1. **Three Real Receipt Samples Collected:** 1 thermal receipt (faded), 1 standard printed tax invoice, 1 handwritten chit from Kuching shops.
2. **Accountant Conversation:** Talk to at least 1 freelance accountant or bookkeeper to confirm their current per-client monthly receipt volume and export format preferences (e.g., CSV, SQL Account Excel format, AutoCount batch format).
3. **Regulatory Output Anchor:** Pinpoint the essential fields required by LHDN MyInvois (Supplier Name, TIN/BRN, Date, Total Amount, Tax/SST Amount, Line Item Description).
