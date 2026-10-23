# Kenyalang Ledger — Hands-On Audit Report

**Date:** 2026-10-23
**Scope:** `kenyalang-ledger` — FastAPI backend, React/Vite frontend, docs, SROIE receipt dataset
**Method:** live app driven end-to-end as a demo user (real OCR + LLM extraction on real SROIE receipts) at 1440 / 768 / 390 / 320 px, plus four parallel read-only audits (docs drift, backend contract, frontend state, security), with every high-severity claim independently re-verified before inclusion.

---

## 1. Verdict

This is a well-built portfolio demo: clean tenant isolation, a real OCR pipeline, a real reconciliation engine, and 330 green tests across three suites.

But **one systemic bug sits directly on the product's core promise** and silently corrupts the compliance export. It should be fixed before this is shown to anyone who knows Malaysian accounting.

| Severity | Count | Theme |
|---|---|---|
| High | 4 | Tax-basis reconciliation, unvalidated money input, CSV injection, pre-auth body buffering |
| Medium | 7 | Status accounting, upload polling, focus handling, validation staleness, responsive/a11y |
| Low | 5 | Error announcement, audit-log detail, docs drift, health fingerprinting |
| Disproved | 3 | Sub-agent claims that did not survive verification |

---

## 2. Headline Defect — Tax-Inclusive Line Totals Treated as Tax-Exclusive

**Severity: High — systematic, affects every GST receipt and every export**

### The problem

Every Malaysian receipt in the dataset prints line amounts **inclusive** of GST. Both the reconciler and the export engine assume line amounts are **exclusive**.

`backend/app/services/reconciler.py:149-171`:

```python
@staticmethod
def _math_discrepancy(data: ParsedReceiptSchema) -> Decimal | None:
    """``|sum(line_total) + tax - grand_total|``, or None when unreconcilable."""
    if data.grand_total is None:
        return None
    tax = data.tax_amount or Decimal("0.00")

    if data.line_items:
        expected = sum(
            (item.line_total for item in data.line_items), Decimal("0.00")
        )
    elif data.subtotal is not None:
        expected = data.subtotal
    else:
        return None

    return abs((expected + tax) - data.grand_total)
```

`expected + tax` is only correct when `expected` is a tax-*exclusive* subtotal. When line totals are already tax-inclusive, `tax` is counted twice.

### Evidence

`100.jpg` prints:

```
BEG GUNI 10 NOS x 0.70 = 7.00
Subtotal                      7.00
GST 6%                        0.42
Total                         7.42
```

The line item total is **7.42**, not 7.00. So the app computes `7.42 + 0.42 = 7.84 ≠ 7.42` and raises `MATH_MISMATCH_DELTA_0.42`.

Confirmed across the batch:

| Receipt | Subtotal | Tax | Grand total | Reported discrepancy | Sum of lines |
|---|---|---|---|---|---|
| `100.jpg` | 7.00 | 0.42 | 7.42 | **0.42** | 7.42 |
| `101.jpg` | 28.00 | 1.68 | 29.68 | **1.68** | 29.68 |
| `102.jpg` | 69.15 | 4.15 | 73.30 | **4.15** | 73.30 |
| `105.jpg` | 28.58 | 1.72 | 30.30 | **1.72** | 30.30 |

In every case the reported delta is **exactly the tax amount**, and `subtotal + tax == grand_total` holds exactly. That is the signature of an inclusive/exclusive basis mix-up, not of OCR error.

`105.jpg` is the most damning, because the receipt states the basis in words:

```
Total (Excluding GST)     28.58
GST payable (6%)           1.72
Total (Inclusive of GST)  30.30
```

The console still demanded `30.30 + 1.72 = 30.30`.

### Why it matters operationally

1. The accountant sees **"Math Mismatch" on receipts that are perfectly correct**.
2. The only way to clear the check is to **falsify the printed line totals** down to a tax-exclusive figure. This was reproduced live: editing `7.00 → 6.60` cleared the flag. A tool whose reconciliation gate can only be satisfied by entering wrong numbers is worse than no gate — it trains users to defeat it.
3. `109.jpg`, an exclusive-style receipt, reconciles correctly (lines 6.60 + tax 0.40 = 7.00). So the logic is not universally broken — it is silently basis-dependent, which is the hardest kind of bug to notice.

### Downstream export corruption

The same assumption propagates into the MyInvois/UBL output. Each invoice contradicts itself:

| Document | Header `LineExtensionAmount` | Σ `InvoiceLine.LineExtensionAmount` | Σ(lines) + Σ(line tax) | `PayableAmount` |
|---|---|---|---|---|
| `CS00011955` | 7.00 | 7.42 | 7.84 | 7.42 |
| `CSOOO11926` | 28.00 | 29.68 | 31.36 | 29.68 |
| `0000OOO111000395667` | 69.15 | 73.30 | 77.45 | 73.30 |

A UBL document where the header `LineExtensionAmount` disagrees with the sum of its own `InvoiceLine/LineExtensionAmount` elements is rejected by LHDN validators. The CSV has the mirror problem: a RM 7.42 receipt is emitted as `TotalAmount 7.84`.

### Root cause and fix direction

The extraction prompt (`backend/app/pipeline/extractor.py:30-75`) never states whether extracted line totals are inclusive or exclusive, and the schema has no field to record the basis. So the model returns whatever the receipt prints — inclusive, for Malaysian retail — and the reconciler assumes exclusive.

There is no single correct code fix without a spec decision. Two viable options:

- **Treat lines as inclusive (matches Malaysian retail):** expected = `Σ line_total`, and verify `tax` separately against `subtotal × rate`.
- **Normalise at extraction:** divide inclusive line totals by `1 + rate`, store the basis explicitly, and keep the current reconciler.

Either way, `docs/05_trd.md` must state the basis. It currently does not mention "inclusive" anywhere.

---

## 3. High Severity

### H2 — A single API call permanently bricks a workspace

**Severity: High — persistent denial of service, no UI recovery path**

```
PUT /api/v1/clients/{cid}/receipts/{rid}   {"grand_total": "1e400"}  → 500
```

After that one request, every read of that workspace fails:

| Endpoint | Before | After |
|---|---|---|
| `GET .../receipts` (list) | 200 | **500** |
| `GET .../receipts/{rid}` (detail) | 200 | **500** |
| `POST .../receipts/{rid}/reject` | 200 | **500** |
| `GET .../dashboard/summary` | 200 | 200 (survives) |
| `GET .../exports/accounting-csv` | 200 | 200, silently empty |

Root cause, `backend/app/schemas/receipt.py:20-24`:

```python
def _finite_money(value: Decimal | None) -> Decimal | None:
    """Reject NaN/Infinity at the LLM trust boundary (docs/05_trd.md §5.4)."""
    if value is not None and not value.is_finite():
        raise ValueError("monetary value must be finite")
    return value
```

`Decimal("1e400").is_finite()` is **`True`** — a finite number with a large exponent. So the guard passes. But `Decimal("1e400").quantize(Decimal("0.01"))` raises `InvalidOperation`, which fires on every subsequent read when the row is serialised.

The row is persisted, so the failure is durable, not transient. Recovery requires manual SQLite surgery.

**Reachability:** not reachable from the UI — `MONEY_PATTERN` caps input at two decimal places. This is an API-only defect, but the API is documented and public within the app.

**Fix:** validate exponent range, not just finiteness — e.g. reject `abs(value) >= Decimal("1e9")` or guard the `quantize` call and map `InvalidOperation` to a 422.

### H3 — CSV formula injection survives a carriage return

**Severity: High — demonstrated, defeats the existing sanitizer**

`backend/app/services/export_engine.py:38` and `:137-146` implement a correct prefix blocklist:

```python
CSV_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

def _csv_text(value: str | None) -> str:
    text = "" if value is None else str(value)
    if text.startswith(CSV_DANGEROUS_PREFIXES):
        return "'" + text
    return text
```

But the writer at `:300` uses `lineterminator="\n"` with default `QUOTE_MINIMAL`:

```python
writer = csv.writer(output, lineterminator="\n")
```

Python's `csv` module does not quote a field containing a bare `\r`. The carriage return survives *inside* the cell and splits the record when Excel (or any RFC-4180 reader) parses it.

**Payload:** `"\r=cmd|' /C calc'!A0"` as a description produced:

```
0: DocDate,DocNo,SupplierCode,SupplierName,Description,...
1: 20/09/2026,INV-CR,SUPP-81109A,CR Vendor,'
2: =cmd|' /C calc'!A0,ITEM-01,1,10.00,SST-6,0.60,10.60
```

The apostrophe guard landed on line 1; the payload `=cmd|...` starts line 2 **unquoted and unescaped** — exactly the formula-execution shape the sanitizer exists to prevent.

Python's own `csv` module cannot parse the result: `new-line character seen in unquoted field`. So the file is simultaneously an injection vector and malformed.

**Note:** the security audit reported this as "fully covered" by reading the sanitizer. It is not — the defect lives in the writer's newline handling, not in the prefix list. Reading only `_csv_text` gives a false negative.

**Fix:** strip or escape `\r` and `\n` inside cell values before writing, and/or use `QUOTE_ALL`. Defence in depth: `lineterminator="\r\n"` with explicit `quoting=csv.QUOTE_ALL`.

### H4 — Unauthenticated request body fully buffered before auth

**Severity: High — unauthenticated resource exhaustion**

```
POST /api/v1/clients/{cid}/receipts/upload
(no X-Accountant-Id header, 200 MB body)
→ 401 in ~1.0 s
```

The body is read in full before the auth dependency runs. A 22 MB body is likewise accepted and buffered. There is no size cap at any layer — not at the ASGI server, not in middleware, not in the route.

The route's own 15 MiB / 50-file / 50 MiB limits are enforced *after* the body has already been materialised, so they do not protect the server.

**Impact:** an unauthenticated attacker can force unbounded memory allocation per concurrent request. Fine for a local demo; not safe on any public host.

**Fix:** reject on `Content-Length` in middleware before reading, and stream to disk with a hard cap rather than buffering.

---

## 4. Medium Severity

### M1 — `status_counts` buckets do not reconcile with `total`

`backend/app/api/receipts.py:771-797` builds the `ALL` bucket from `by_status.values()`, which covers every status present in the DB. But the individual buckets come from `INBOX_STATUS_FILTERS`, which has no entry for any `ERR_*` status (`ERR_UNREADABLE`, `ERR_TIMEOUT`, `ERR_FILE_CORRUPT`, …) — see `backend/app/models/receipt.py:32-46`.

Observed on a client with one corrupt upload:

```
total: 8
All 8 | Needs review 1 | Verified 2 | Exported 3 | Rejected 1   (sums to 7)
```

The corrupt receipt is visible only under **All**, shows `FILE ERROR`, and has no filter tab of its own. It also reports `processing_error: null`, so the row displays no reason at all — the spec expects the error reason to render.

Related: status strings are inconsistent across the enum (`STATUS_NEEDS_REVIEW` vs `PROCESSING_OCR` — one prefixed, one not).

**Fix:** add `ERR` to `INBOX_STATUS_FILTERS`, and populate `processing_error` for terminal error states.

### M2 — Upload page badges never settle

`frontend/src/pages/UploadPage.tsx` contains no `setInterval` and no polling. Batch rows stay at `PROCESSING` indefinitely — observed 25 s after the server had already settled the receipt to `STATUS_NEEDS_REVIEW`.

The Inbox page polls correctly, so this is a page-local gap. A user uploading a batch and waiting on that screen concludes the pipeline has hung.

**Fix:** reuse the Inbox polling hook, or link the batch row to the receipt's real status.

### M3 — Alt+Backspace deletes a line after focus has left the table

`frontend/src/pages/ReviewPage.tsx:140` declares `focusedLineKey`, used at `:368` and `:393-394`:

```tsx
const [focusedLineKey, setFocusedLineKey] = useState<string | null>(null);
...
if (!isLocked && focusedLineKey !== null) {
  removeDraftLine(focusedLineKey);
}
```

`focusedLineKey` is **never cleared on blur**. After moving focus out of the table (e.g. into the totals fields, or the browser chrome), Alt+Backspace still deletes the last-focused line.

Reproduced: blur the row via `document.activeElement.blur()`, press Alt+Backspace → line count went from **2 to 1**. No confirmation, no undo.

This is a destructive keyboard shortcut firing outside its visual context — the worst class of focus bug, because the user has no reason to believe the shortcut is still armed.

**Fix:** clear `focusedLineKey` on blur, and gate the handler on the table actually containing focus.

### M4 — Escape twice arms the irreversible reject band

First Escape blurs the active field; a second Escape opens the "Reject this receipt" confirmation band. A confirm click is still required, so this is not a data-loss bug — but it puts an irreversible action one keystroke away during normal review, and Escape is exactly the key users mash to dismiss things.

**Fix:** require an explicit action (button or a non-Escape chord) to arm rejection.

### M5 — Stale validation flags survive a line-item rewrite

After replacing 10 line items with 1 via `PUT`, the receipt still carried `LOW_CONFIDENCE_line_items[1]` … `[9]` — nine flags pointing at rows that no longer exist.

The update path in `backend/app/api/receipts.py` (~872-1000) refreshes `MATH_*` flags but does not recompute per-field confidence flags. Any client editing line items through the API accumulates phantom warnings.

**Fix:** re-run the full flag derivation on update, not just the math check.

### M6 — Filter strip clipping (partially disproved — see §6)

At 390 px the tab strip's right edge measured x=434 against a 390 px viewport. At 320 px, content width is 454 px in a 320 px viewport.

However, re-measurement showed the container is `overflow-x: auto` and scrolls, so the tabs are **reachable**, not clipped-off. The real residual issue is only that the strip requires horizontal scrolling with no visual affordance (no fade, no scrollbar hint) — a discoverability nit, not a blocker.

### M7 — Verify accepts an unresolved math mismatch

The review console permits verification while the live audit shows a non-zero delta. Reproduced by setting the grand total to `50.00` against lines summing to `6.00 + 0.34` tax: the banner reported the mismatch and the **Verify button stayed enabled**.

This may be intentional — an accountant may legitimately override a flagged receipt, and the audit trail records it. But if so it should be a deliberate, labelled override ("Verify anyway — RM 44.00 unexplained"), not an unremarked enabled button. As built, the check is advisory while looking authoritative.

---

## 5. Low Severity / Polish

| # | Issue | Location |
|---|---|---|
| L1 | Save-failure message renders but has no `role="alert"`, so screen readers do not announce it. The text itself is visible ("Failed to fetch") — the earlier "silent failure" claim was wrong. | `frontend/src/api/client.ts` |
| L2 | Audit log for a value edit records `line_items: 1 rows → 1 rows` — technically true, operationally useless. | audit trail |
| L3 | `GET /api/health/ready` discloses the DB dialect unauthenticated. Harmless locally; stack fingerprinting publicly. | `backend/app/main.py` |
| L4 | `statusCounts` is not reset when switching clients, so stale counts flash before the new fetch resolves. | `frontend/src/store/receiptStore.ts` |
| L5 | Mobile layout hides `thead` with no alternative labelling, so stacked cells lose their column names. | `frontend/src/index.css` |

---

## 6. Claims Investigated and Disproved

Every high-severity sub-agent claim was re-tested. Three did not survive.

**"The reject endpoint does not exist."** — **False.** `@router.post` is registered at `backend/app/api/receipts.py:1006-1007` and returns **200** with an audit row on a live call. This was the docs audit's top finding; it was wrong.

**"A failed save fails silently."** — **Overstated.** The UI does surface "Failed to fetch". The genuine defect is only the missing `role="alert"` (L1), an a11y gap rather than a UX failure.

**"Filter tabs are unreachable at 320 px."** — **False.** The strip is `overflow-x: auto` (454 px of content in a 320 px box) and scrolls normally. Reduced to M6.

**"Clients are create-only, so missing rename/delete is a bug."** — **Not a defect.** `docs/04_ui_specs.md` explicitly specifies "no edit variant — clients are create-only". The API does support `PUT`/`DELETE`; the UI deliberately does not expose them. Do not promise renaming in a demo.

**"The ERR row is invisible."** — **Overstated.** It is visible under the `All` tab. The real defect is the missing filter bucket and the null `processing_error` (M1).

---

## 7. What Works Well

Worth stating plainly, because these are the parts that make the demo land.

- **Tenant isolation is genuinely solid.** Cross-tenant list / detail / update / reject / audit / export all return 404. A second accountant entering a foreign client's URL from browser history gets "Client not found". `X-Accountant-Id` spoofing only unlocks that UUID's own namespace, and production startup refuses to boot without the env configured. This is the single best-engineered part of the system.
- **Real OCR pipeline.** Uploads run EasyOCR → LLM → reconcile with live `PROCESSING_OCR → PROCESSING_LLM → VALIDATING_MATH` transitions, settling in ~40 s for a 3-receipt batch. Not a stub, not a fixture replay.
- **Upload preflight.** Magic-byte validation (415 on a renamed `.md`), 15 MiB / 50-file / 50 MiB caps, no partial batch on failure, filename traversal neutralised. Thorough.
- **Bbox provenance overlay.** Clicking a field highlights its OCR bounding box on the receipt image. This is the feature that sells the product and it works.
- **Export mechanics.** Tax allocation sums exactly to document tax; `mark` is idempotent; exported receipts are genuinely locked (409 on `PUT`/`reject`, fields disabled in the UI); downloads do not mutate state.
- **Dashboard.** Empty month returns zeros with all five categories present; top suppliers capped and sorted spend-descending; the inclusive/exclusive spend note is correct.
- **Reconciliation UX.** The live audit banner updates on edit with the exact breakdown; Verify is disabled while a field is invalid; the 2¢ tolerance is honoured.
- **Money input guard.** Invalid money strings in the UI are blocked before submit ("Fix Line 1 total before verifying").
- **Read-only enforcement.** An exported receipt refuses edits and shortcuts, both in the UI and at the API.

---

## 8. Gate Results

All gates were re-run for this report.

| Gate | Command | Result |
|---|---|---|
| Backend tests | `pytest` | **237 passed**, 0 failed, 0 errors, 0 skipped — 49.5 s |
| Backend lint | `ruff check .` | **All checks passed** |
| Frontend types | `tsc --noEmit` | **Clean** (exit 0) |
| Frontend unit | `vitest run` | **43 passed** (5 files) |
| E2E | `playwright test` | **50 passed** (42.7 s) |
| Production build | `npm run build` | Succeeds |

**Total: 330 tests, 0 failures.**

> **Count caveat:** an earlier JUnit run reported 250 and `.pytest_cache/v/cache/nodeids` held 294 stale entries from prior sessions. The authoritative figure is the collected count of **237** (`pytest --collect-only`, 17 files). Do not quote 250 or 294.

The E2E suite includes a real WCAG 2.2 AA axe sweep across every surface, a 320 px reflow sweep, contrast checks, reduced-motion checks, and touch-target sizing — unusually thorough for a demo project, and it is why the a11y findings above are all minor.

---

## 9. Demo-Script Caveats

Things that will bite during a live walkthrough:

1. **`/upload` needs a workspace selected first**, or it renders the empty state. Visit Inbox before Upload when scripting the demo.
2. **Upload page badges never settle** (M2) — narrate around it or go straight to Inbox.
3. **Reject is one Escape away** (M4) — avoid mashing Escape while demonstrating.
4. **No client rename/delete in the UI** — create-only by design. Don't promise it.
5. **The tax mismatch will fire on every GST receipt** (H1). If demoing with real SROIE receipts, either pre-fix H1, choose `109.jpg`-style exclusive receipts, or explain it as a known bug — but do not let an accountant discover it live.
6. **Month picker requires real interaction.** Synthetic DOM `value` changes do not update React state; drive it with actual events.

---

## 10. Repo State

**Not caused by this session.** `git status` shows 11 modified files and a large deletion set under `videos/kenyalang-launch/`. File mtimes are 15:12–15:34, hours before this audit began (~19:30). No source file was edited during this audit.

```
 M .gitattributes
 M docs/03_appflow.md
 M docs/04_ui_specs.md
 M docs/e2e-evidence/README.md
 M frontend/e2e/03-inbox.spec.ts
 M frontend/e2e/05-exports.spec.ts
 M frontend/e2e/08-standards.spec.ts
 M frontend/src/index.css
 M frontend/src/pages/ExportsPage.tsx
 M frontend/src/pages/InboxPage.tsx
 M frontend/src/pages/ReviewPage.tsx
 D videos/kenyalang-launch/**   (43 files)
```

**Cleanup performed:** all demo databases (`backend/kenyalang*.db`), `backend/storage-demo`, `.tmp-*` scratch directories, JUnit XML, and pytest caches removed. All demo servers stopped (ports 8000 / 5173 / 8010 / 8011 / 5185 / 8020 free). Zero untracked files remain apart from this report.

**Stray files in repo root, pre-existing and unrelated to this audit:** `_audit-api.log`, `_audit-vite*.log`, `_demo-api.log`, `build-final.txt`, `chat.json`, `models.json`, `lint-final.txt`, `pytest-*.txt`, `receipt_crop.jpg`. These are leftovers from earlier sessions. All 15 are covered by `.gitignore` (`*.log`, `pytest-*.txt`, and explicit entries) and were verified with `git check-ignore`, so they will not land in a commit — but they are still clutter on disk.

---

## 11. Recommended Order of Work

1. **H1 — tax basis.** Decide inclusive vs exclusive, encode it in the schema and the extraction prompt, fix the reconciler and the UBL/CSV builders. This is the only defect that produces wrong numbers in a compliance document.
2. **H2 — `1e400`.** Guard the exponent range in `_finite_money`. Small, isolated, prevents permanent workspace loss.
3. **H3 — CSV `\r`.** Strip control characters in `_csv_text` and switch the writer to `QUOTE_ALL`. One-line class of fix, closes a demonstrated injection.
4. **H4 — pre-auth buffering.** `Content-Length` rejection in middleware. Required before any public deployment.
5. **M1, M2** — status bucket completeness and upload polling. Both are visible on a normal demo path.
6. **M3, M4** — focus and Escape handling. Cheap fixes, remove the two ways a user can destroy data by accident.
7. Everything else is polish.

---

*Prepared from live runtime observation and source verification. Every finding above was reproduced; every disproved claim is documented in §6.*
