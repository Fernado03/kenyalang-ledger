# Kenyalang Ledger — Step 3: Interaction Architecture & Appflow

---

## 3.1 Global Information Architecture (IA) & Route Hierarchy

The application runs two distinct user personas with distinct device contexts:

1. **Micro-SME Mobile Capture:** Single-action mobile-optimized upload (`/upload`).
2. **Accountant Multi-Client Console:** High-density, keyboard-driven desktop workspace (`/clients/:clientId/...`).

```
[ Root (/) ]
 ├── [/login] — Email Magic Link / Passwordless Session
 ├── Mobile Context (Micro-SME)
 │    └── [/upload] — Fast Camera Capture & Recent Upload Status
 └── Desktop Console (Accountant Context)
      ├── [/clients] — Client Workspace Switcher (Tenancy Partition)
      └── [/clients/:clientId]
           ├── [/inbox] — Batch Upload Dropzone & Processing Queue (Default Landing)
           ├── [/review/:receiptId] — Split-Screen Keyboard Review Console
           ├── [/dashboard] — Monthly Spend & Supplier Breakdown
           └── [/exports] — CSV (AutoCount/SQL) & MyInvois v1.1 JSON Generation
```

### Route Guard & Authorization Rules

* **Tenant Isolation:** Every request to `/clients/:clientId/*` validates that the active session owns or has delegated access to `:clientId`.
* **Session Gate & Frontend Implementation:** The desktop console is implemented as a React 18 + Vite SPA in `frontend/` (proxied to `/api` on `http://127.0.0.1:8000`). Until a full IdP is integrated, the app uses an `<AccountantGate>` component that stores the accountant UUID in `localStorage` (`kenyalang.accountant_id`) and transmits it as the `X-Accountant-Id` header on all requests.
* **State Preservation:** Navigating between receipts in `/review/:receiptId` preserves dirty form fields in local cache (Zustand store persisted to `localStorage` under `kenyalang.draft.{receiptId}`) to prevent accidental data loss if the browser refreshes.
---

## 3.2 End-to-End State Machine & Pipeline Lifecycle

Every uploaded receipt transitions through an asynchronous state machine:

```
                  ┌──────────────────────┐
                  │ 1. PENDING_UPLOAD    │ (File queued on client)
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │ 2. UPLOADED          │ (Saved to storage, DB row created)
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │ 3. PROCESSING_OCR    │ (EasyOCR bounding box extraction)
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │ 4. PROCESSING_LLM    │ (Structured entity JSON extraction)
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │ 5. VALIDATING_MATH   │ (Arithmetic reconciliation & sanity check)
                  └──────────┬───────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
   [Math Valid & Conf ≥ 0.80]       [Math Mismatch OR Conf < 0.80]
            │                                 │
            ▼                                 ▼
┌────────────────────────┐       ┌────────────────────────┐
│  STATUS_AUTO_VERIFIED  │       │  STATUS_NEEDS_REVIEW   │
└───────────┬────────────┘       └───────────┬────────────┘
            │                                │
            │                     ┌──────────┘ (Accountant edits & Cmd+Enter)
            │                     ▼
            │            ┌────────────────────────┐
            │            │    STATUS_VERIFIED     │
            │            └───────────┬────────────┘
            │                        │
            └───────────┬────────────┘
                        ▼
             ┌──────────────────────┐
             │   STATUS_EXPORTED    │ (Included in CSV / MyInvois batch)
             └──────────────────────┘
```

### Terminal Error States

* `ERR_UNREADABLE`: OCR detected $< 5$ text tokens (e.g., photo of blank table or pitch-black image).
* `ERR_TIMEOUT`: OCR or LLM pipeline exceeded 15 seconds.
* `ERR_FILE_CORRUPT`: Image decoding failed at OpenCV level.
* *Error Handling:* The UI renders a dedicated error badge with a "Re-upload" or "Force Manual Entry" button.

---

## 3.3 Screen Inventory (`SCR-01` to `SCR-05`)

In adherence to production standards, every view must explicitly handle all **5 UX States**: Empty, Loading, Populated, Flagged/Review, and Error.

### `SCR-01`: Client Workspace Switcher (`/clients`)

* **Target Audience:** Freelance Accountant.
* **Primary Purpose:** Select or create client profiles (e.g., "Ah Teck Hardware Sdn Bhd", "Uncle Lim Kopi").
* **States:**
    * *Empty:* Zero clients configured $\rightarrow$ "Add your first client" modal with business name and SST/BRN inputs.
    * *Loading:* High-density table skeleton with subtle shimmer (`LoadingSkeleton`).
    * *Populated:* Table showing: Client Name, Registration, SST, Industry, Unreviewed Receipt Count, Verified Count, and Open action. Counts are queried per client via `GET /api/v1/clients/{clientId}/receipts` (`limit=1`, status `NEEDS_REVIEW` and `VERIFIED`).
    * *Error:* Inline banner if workspace metadata fails to load with Retry action.

### `SCR-02`: Batch Inbox & Upload Dropzone (`/clients/:clientId/inbox`)

* **Target Audience:** Accountant & Desktop SME users.
* **Primary Purpose:** Drag-and-drop batch upload area (up to 50 files) + receipt status list.
* **Key Actions:**
    * Drag & Drop receipt images (`.jpg`, `.png`, `.pdf`, `.heic`).
    * Filter list by: `All`, `Needs Review`, `Verified`, `Exported`.
    * Multi-select for bulk delete or bulk verify.
* **States:**
    * *Empty:* Large drag-and-drop target with label: *"Drop receipts here, or click to browse. Max 50 files per batch."*
    * *Loading:* High-density loading skeleton rows during fetch or upload.
    * *Populated:* Dense tabular list (`h-dense-row`, 40px) showing Thumbnail (streamed from authenticated `image_url`), Merchant, Date (`font-mono-numbers`), Line Items count, Grand Total (`font-mono-numbers`, text-right), Status Badge (`StatusPill`), and Review action (`Review (↵)`).
    * *Flagged:* Rows with `STATUS_NEEDS_REVIEW` render an amber left border (`border-l-2 border-warning-border`) and display specific warning badges (e.g., `[Math Mismatch: Δ RM 2.40]`, `[Missing Date]`). Error states render a red left border (`border-l-2 border-mismatch-border`).
    * *Error:* Inline banner (`ErrorBanner`) with Retry action if receipt list fetch fails.

### `SCR-03`: Split-Screen Review Console (`/clients/:clientId/review/:receiptId`)

* **Target Audience:** Accountant (Optimized for speed and minimal mouse movement).
* **Primary Purpose:** Correct and verify OCR/LLM extracted fields against the physical receipt image.
* **Layout:**
    * **Left Pane (50% width):** High-resolution receipt viewport with canvas-based Pan & Zoom, and bounding box highlights.
    * **Right Pane (50% width):** Structured form containing header fields and a dynamic line-item table.

```
┌────────────────────────────────────────┬────────────────────────────────────────┐
│ RECEIPT IMAGE VIEWPORT (Left 50%)       │ DATA ENTRY & VERIFICATION (Right 50%)  │
├────────────────────────────────────────┼────────────────────────────────────────┤
│ [Zoom In (+)] [Zoom Out (-)] [Reset]   │ Status: [ NEEDS REVIEW ]   ID: REC-1082│
│                                        │                                        │
│  ┌──────────────────────────────────┐  │ Merchant:  [ Kim Guan Hardware      ]  │
│  │ KIM GUAN HARDWARE                │  │ BRN / SST: [ 002938192-K            ]  │
│  │ Date: 12/09/2026                 │  │ Date:      [ 2026-09-12             ]  │
│  │                                  │  │ Inv No:    [ INV-99120              ]  │
│  │ 1. PVC Pipe 2"      RM 14.50     │  ├────────────────────────────────────────┤
│  │ 2. Minyak Hitam 4L  RM 85.00     │  │ Line Items:                 [+ Add Row]│
│  │                                  │  │ Description    Qty   Price    Total    │
│  │ Subtotal:           RM 99.50     │  │ [PVC Pipe 2" ] [ 1 ] [14.50]  [14.50]  │
│  │ SST 6%:             RM  5.97     │  │ [Minyak Hitam] [ 1 ] [85.00]  [85.00]  │
│  │ Grand Total:        RM 105.47    │  ├────────────────────────────────────────┤
│  └──────────────────────────────────┘  │ Subtotal:  RM 99.50                    │
│                                        │ SST (6%):  RM  5.97                    │
│ [Hovering over "PVC Pipe" highlights   │ Total:     RM 105.47  [✓ Math Matches] │
│ bounding box on image in teal]         │                                        │
│                                        │ [Reject / Esc]   [Verify & Next (⌘↵)]  │
└────────────────────────────────────────┴────────────────────────────────────────┘
```

### `SCR-04`: Mobile Quick Capture (`/upload`)

* **Target Audience:** Micro-SME Shop Owner (Phone in hand).
* **Primary Purpose:** One-tap camera upload with zero friction.
* **Layout:**
    * Large full-width camera trigger: *"Ambil Gambar Resit" (Take Photo)*.
    * File picker fallback: *"Pilih dari Galeri" (Select from Gallery)*.
    * Recent uploads carousel (last 5 receipts with status pill: `Memproses...`, `Selesai`, `Perlu Semak`).

### `SCR-05`: Export Hub (`/clients/:clientId/exports`)

* **Target Audience:** Accountant.
* **Primary Purpose:** Generate accounting files and LHDN compliance payloads.
* **Components:**
    * **Date Range Selector:** Month-end filter (e.g., `September 2026`).
    * **Export Option A (CSV/Excel):** Radio options for *AutoCount Batch Format*, *SQL Account Purchase Journal*, and *Generic Clean CSV*.
    * **Export Option B (LHDN MyInvois v1.1 JSON):** Formatted multi-line JSON conforming to `1.1-Invoice-MultiLineItem-Sample.json`. Includes schema validator badge showing `Schema Check: 100% Valid`.

---

## 3.4 Keyboard-First Interaction Engine (For `SCR-03`)

To guarantee the **10-second review goal**, the AI agent implementing the frontend must wire these native keyboard bindings without mouse dependency:

| Keybinding | Scope | Function |
| --- | --- | --- |
| `Tab` / `Shift+Tab` | Form Inputs | Move focus forward/backward between inputs. |
| `Cmd + Enter` / `Ctrl + Enter` | Global Review | Mark receipt as `STATUS_VERIFIED` and advance immediately to the next flagged receipt. |
| `Alt + A` | Form Inputs | Append a new blank line-item row. |
| `Alt + Backspace` | Line Items | Delete currently focused line-item row. |
| `[` and `]` | Canvas | Zoom receipt image in (`+`) and out (`-`). |
| `R` | Canvas | Reset image zoom to fit-to-width. |
| `Esc` | Global Review | Return to Inbox list (`SCR-02`). |
| `Tab` focus on field | Canvas Link | When an input field gains focus, smoothly pan the canvas to that field's bounding box coordinates. |

---

## 3.5 Math Reconciliation Rules & UI Alerts

The validation engine must execute on every client-side keystroke in `SCR-03`:

1. **The Core Formula:**

$$\Delta = \left| \sum (\text{item.qty} \times \text{item.unit\_price}) + \text{sst\_amount} - \text{grand\_total} \right|$$

2. **Reconciliation States:**
    * **$\Delta \le 0.02$:** Field displays green checkmark `[✓ Math Matches]`.
    * **$\Delta > 0.02$:** Field turns high-contrast Amber/Red and displays discrepancy calculation: `[⚠️ Math Mismatch: Line items total RM 99.50 + Tax RM 5.97 ≠ Grand Total RM 108.00 (Difference: RM 2.53)]`.

3. **Missing Tax Logic:**
    * If `sst_amount` is 0 or null, check if `brn_tin` contains an SST registration number. If yes, flag: `[Missing SST on Registered Merchant]`.
