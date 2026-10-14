# Kenyalang Ledger — Step 4: UI/UX Design System Specifications

---

## 4.1 Visual Anti-Slop Foundations & Design Tokens

Kenyalang Ledger is an enterprise data-entry workhorse, not a lifestyle landing page. The interface must look like **Linear, Stripe Dashboard, or Bloomberg Terminal**: ultra-dense, razor-sharp borders, zero generic AI purple gradients, zero glassmorphism, and instant tactile feedback.

### Color Tokens (Tailwind CSS Palette)

We use a high-contrast **Slate & Deep Hornbill Teal** theme. The teal accent grounds the brand in Sarawak without relying on generic tech-blue.

```javascript
// tailwind.config.js snippet
module.exports = {
  theme: {
    extend: {
      colors: {
        // Neutral Slate Foundation (High contrast, clean borders)
        canvas: '#F8FAFC',       // Slate 50
        surface: '#FFFFFF',      // Pure White
        'surface-subtle': '#F1F5F9', // Slate 100
        border: '#CBD5E1',       // Slate 300 (Crisp, defined outlines)
        'border-focus': '#0F172A', // Slate 900

        // Typography
        'text-primary': '#0F172A',   // Slate 900
        'text-secondary': '#475569', // Slate 600
        'text-muted': '#94A3B8',     // Slate 400

        // Brand Wedge: Sarawak Hornbill Teal (Single intentional accent)
        brand: {
          50: '#F0FDFA',
          500: '#14B8A6',
          700: '#0F766E',
          900: '#134E4A',       // Primary active brand color
        },

        // Semantic Confidence & Financial Status Tokens (WCAG 2.2 AA compliant)
        verified: {
          bg: '#ECFDF5',        // Emerald 50
          border: '#10B981',    // Emerald 500
          text: '#065F46',      // Emerald 800
        },
        warning: {
          bg: '#FFFBEB',        // Amber 50 (Low-confidence OCR)
          border: '#F59E0B',    // Amber 500
          text: '#92400E',      // Amber 800
        },
        mismatch: {
          bg: '#FEF2F2',        // Red 50 (Math reconciliation failure)
          border: '#EF4444',    // Red 500
          text: '#991B1B',      // Red 800
        }
      }
    }
  }
}
```

### Typography Scale & Tabular Numerals

* **Primary Interface Font:** System Sans Stack or `Inter` (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`).
* **Financial & Data Font:** `JetBrains Mono` or `ui-monospace`.
* **Mandatory CSS Rule for all Ringgit values and quantities:**

```css
.font-mono-numbers {
  font-family: 'JetBrains Mono', monospace;
  font-variant-numeric: tabular-nums lining-nums;
  letter-spacing: -0.02em;
}
```

*(Tabular numerals guarantee that decimal points and Ringgit digits align vertically in accounting tables without jumping horizontally).*

---

## 4.2 Motion Architecture & Micro-Interactions

Per the production performance guidelines: **no Framer Motion or GSAP bloat**. We use pure native CSS transitions. An accountant reviewing 100 receipts per hour will be slowed down by fade-ins and staggered entrance effects.

* **Global Interaction Speed:** $\le 100\text{ms}$ ease-out for hover, focus, and modal triggers.
* **Review Console Transitions:** $0\text{ms}$ (Instant) when cycling through receipts using `Cmd+Enter`. Form fields update synchronously.
* **Reduced Motion Guarantee:**

```css
@media (prefers-reduced-motion: reduce) {
  *, ::before, ::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

* **Receipt Image Canvas (Left Pane of `SCR-03`):**
    * Hardware-accelerated CSS transforms (`transform: translate3d(x, y, 0) scale(z); will-change: transform;`) to allow 60fps pan and zoom on images up to 15MB without layout recalculations.

---

## 4.3 Screen-by-Screen Component Specifications

### 1. `SCR-02`: Batch Inbox & Dropzone Layout (`/clients/:clientId/inbox`)

* **Density:** Row height `40px` (dense data grid).
* **Grid Columns:**
    1. Multi-select Checkbox (`32px`)
    2. Thumbnail preview (`48px`)
    3. Supplier Name (`text-primary`, font-semibold, truncate)
    4. Date (`font-mono-numbers`, `text-secondary`, `100px`)
    5. Line Item Count (`text-secondary`, `80px`)
    6. Grand Total (RM) (`font-mono-numbers`, text-right, `110px`)
    7. Status Pill (`130px`)
    8. Quick Action: "Review (↵)" (`80px`)

#### Status Pill Design Matrix:

* **Verified:** `bg-verified-bg border border-verified-border text-verified-text` $\rightarrow$ `● Selesai`
* **Needs Review (Math Mismatch):** `bg-mismatch-bg border border-mismatch-border text-mismatch-text` $\rightarrow$ `⚠️ Δ RM 2.40`
* **Needs Review (Low Confidence):** `bg-warning-bg border border-warning-border text-warning-text` $\rightarrow$ `⚡ Semak OCR (64%)`
* **Processing:** `bg-surface-subtle border border-border text-text-secondary` $\rightarrow$ `⏳ Memproses...`

### 2. `SCR-03`: Split-Screen Review Console Layout (`/review/:receiptId`)

A balanced 50/50 desktop split view:

```
┌───────────────────────────────────────────────┬───────────────────────────────────────────────┐
│ LEFT PANE: Canvas Viewport (w-1/2)            │ RIGHT PANE: Verification Form (w-1/2)         │
├───────────────────────────────────────────────┼───────────────────────────────────────────────┤
│ • Top Bar: [Zoom -] [100%] [Zoom +] [Rotate]  │ • Header Bar: ID: REC-0412                    │
│                                               │   Status Pill | [Reject] [Verify & Next ⌘↵]   │
│ • Canvas Body:                                ├───────────────────────────────────────────────┤
│   - High-res receipt image rendered on Canvas │ • Form Section 1: Merchant & Date             │
│   - Bounding Box Layer:                       │   [Supplier Name]       [BRN / SST Number]    │
│     * Red box = Math mismatch item            │   [Invoice Date]        [Invoice Number]      │
│     * Amber box = Low-confidence token        ├───────────────────────────────────────────────┤
│     * Teal box = Currently active input field │ • Form Section 2: Line Items Table (Dense)    │
│                                               │   | Description | Qty | Unit (RM) | Total (RM)|
│                                               │   |-------------|-----|-----------|-----------|
│                                               │   | Minyak 4L   | 1   | 85.00     | 85.00     |
│                                               │   | Upah pasang | 1   | 20.00     | 20.00     |
│                                               │   [+ Add Line (Alt+A)]                        │
│                                               ├───────────────────────────────────────────────┤
│                                               │ • Form Section 3: Totals & Tax Audit          │
│                                               │   Subtotal:  RM 105.00                        │
│                                               │   SST (6%):  RM   0.00                        │
│                                               │   Grand Total: RM 105.00 [✓ Math Reconciled]  │
└───────────────────────────────────────────────┴───────────────────────────────────────────────┘
```

#### Bounding Box Visual Encoding:

When an accountant focuses on a specific input field on the right (e.g. `Invoice Date`), the corresponding coordinate box on the left receipt image lights up:

* **Active Field Focus:** `stroke: #14B8A6; fill: rgba(20, 184, 166, 0.15); stroke-width: 2px;`
* **Low Confidence ($< 0.80$):** `stroke: #F59E0B; fill: rgba(245, 158, 11, 0.10); stroke-dasharray: 4;`
* **Math Mismatch:** `stroke: #EF4444; fill: rgba(239, 68, 68, 0.10); stroke-width: 2px;`
* **Hover Interaction:** Hovering over a bounding box on the image displays a tooltip with OCR raw text and confidence score: `"KIM GUAN HARDWARE (Conf: 94%)"`.

### 3. `SCR-04`: Mobile Quick Capture Layout (`/upload`)

Designed for an SME owner standing in a hardware shop with a phone in one hand:

* **Viewport:** Mobile-locked single column (`max-w-md mx-auto`).
* **Primary Touch Target:** Giant circular capture button (`h-24 w-24 rounded-full bg-brand-900 text-white shadow-lg active:scale-95`).
* **Visual Guides:** A dashed overlay guide on the camera viewfinder helping the user align receipts to avoid extreme perspective skew.
* **Instant Feedback Sheet:** Once snapped, an instant bottom sheet slides up showing:
    * Upload status: `Gambar berjaya dimuat naik (Processing in background...)`
    * Action: `[Ambil Resit Seterusnya]` (Snap Next) or `[Kembali]`.

---

## 4.4 Form Control & Accessibility Standards

* **Visible Focus:** No default browser outlines. Custom crisp outline: `focus-visible:ring-2 focus-visible:ring-brand-900 focus-visible:ring-offset-1 focus-visible:outline-none`.
* **Field Validation Error Placement:** Errors render directly underneath the field with `id="error-{field_name}"` and the input holds `aria-invalid="true"` and `aria-describedby="error-{field_name}"`.
* **Touch Target Size:** All buttons on mobile and desktop have a minimum touch/click target of `44px x 44px`.

---

## 4.5 Component Props Contracts (TypeScript)

These TypeScript interfaces define the exact state shapes the AI agent will code in React:

```typescript
// Types for SCR-03 Review Console
export interface BoundingBox {
  x_min: number; // Normalized 0.0 to 1.0
  y_min: number;
  x_max: number;
  y_max: number;
}

export interface ExtractedField<T> {
  value: T;
  confidence: number; // 0.00 to 1.00
  bbox?: BoundingBox;
  is_flagged: boolean;
}

export interface LineItem {
  id: string;
  description: ExtractedField<string>;
  quantity: ExtractedField<number>;
  unit_price: ExtractedField<number>;
  line_total: ExtractedField<number>;
}

export interface ReceiptReviewData {
  receipt_id: string;
  client_id: string;
  image_url: string;
  status: 'STATUS_NEEDS_REVIEW' | 'STATUS_AUTO_VERIFIED' | 'STATUS_VERIFIED' | 'STATUS_EXPORTED';
  merchant_name: ExtractedField<string>;
  brn_tin: ExtractedField<string>;
  invoice_date: ExtractedField<string>;
  invoice_number: ExtractedField<string>;
  line_items: LineItem[];
  subtotal: ExtractedField<number>;
  tax_amount: ExtractedField<number>;
  grand_total: ExtractedField<number>;
  math_discrepancy: number; // |sum(line_items qty * unit_price) + tax_amount - grand_total| (flag if > 0.02)
}
```
