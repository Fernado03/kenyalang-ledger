# Kenyalang Ledger — Dataset Folder

Central store for all receipt/OCR data used to build and evaluate Kenyalang Ledger
(Step 1 → Step 8). Every asset carries a **provenance label** — never describe a
`public_dataset` or `official_lhdn_sample` file as "collected from a shop".

## Provenance labels

| Label | Meaning |
|---|---|
| `official_lhdn_sample` | Published by LHDN for schema reference. Output-shape anchor only. |
| `public_dataset` | Open benchmark data. Test/eval input, NOT field evidence. |
| `real_*_redacted` | Physically collected by us, privacy-redacted, source-noted. Required for Stage-Gate 1 sign-off. |

## Layout

```
dataset/
├── README.md                  ← this file (catalog + future use)
├── fetch.py                   ← one-shot downloader (python fetch.py, idempotent)
├── official_lhdn_sample/      ← MyInvois v1.1 XML+JSON samples (all 11 document types ×2)
├── sroie/                     ← SROIE: receipt images + key-field KIE parquet (merchant/date/total/address)
├── funsd/                     ← FUNSD: form images + key-value NER parquet
├── coru/                      ← ReceiptSense/CORU line-item JSON labels (receipt → item list schema)
├── hand_captured_receipts/    ← Zenodo phone-photo restaurant receipts (blur/angle augmentation)
└── invoices_receipts_ocr/     ← mychen76 invoice+receipt test split
```

## What each dataset is for (future use)

| Folder | Source | Size | Use in Kenyalang Ledger |
|---|---|---|---|
| `official_lhdn_sample/` | [MyInvois SDK samples](https://sdk.myinvois.hasil.gov.my/sample/) | ~small | **Output contract for REQ export fields.** Diff our generated JSON against `1.1-Invoice-MultiLineItem-Sample.json` for MyInvois validation. Multi-line + consolidated samples define line-item array shape. |
| `sroie/` | HF `arvindrajan92/sroie_document_understanding` + `nhernandez99/sroie_dataset` | ~30 MB | Faded/scanned thermal-receipt baseline: merchant name, date, total extraction. Use as OCR regression set and few-shot prompt examples. |
| `funsd/` | HF `nielsr/funsd` | ~17 MB | Key-value field extraction (label↔value layout) → informs confidence-scoring rules (Step 2): low-confidence KV pairs route to human review. |
| `coru/` | HF `abdoelsayed/CORU` ([ReceiptSense](https://arxiv.org/abs/2406.04493)) | ~17 MB JSON | Line-item parsing schema reference (receipt → [(desc, qty, price)]). Test set = held-out parser eval. Large image zips intentionally not fetched (train 9.4 GB) — pull on demand. |
| `hand_captured_receipts/` | [Zenodo 13688441](https://zenodo.org/records/13688441) | ~19 MB | WhatsApp-style capture conditions: blur, skew, uneven light. Augmentation + robustness eval for the mobile photo path. |
| `invoices_receipts_ocr/` | HF `mychen76/invoices-and-receipts_ocr_v1` (test split) | ~19 MB | Mixed invoice/receipt OCR smoke set; includes SST-style printed tax invoice layouts. |

## Deliberately NOT fetched (documented, not missing)

| Dataset | Why not here | How to get when needed |
|---|---|---|
| **SROIE v2 (full, 1k)** | Kaggle needs credentials | `kaggle datasets download -d urbikn/sroie-datasetv2` |
| OCR Receipts Text Detection | Kaggle needs credentials | `kaggle datasets download -d trainingdatapro/ocr-receipts-text-detection` |
| **CORD v2** (Indonesian receipts, item bboxes) | 2.3 GB parquet — too big for default | `huggingface-cli download naver-clova-ix/cord-v2` when training/fine-tuning |
| CORU OCR/Receipt image zips | 260 MB OCR / 11 GB receipts | Pull only `OCR/val.zip` (39 MB) for prompt-shot images |
| Malay handwriting `ocr.zip` | **S3 link dead (404, checked 2026-09-29)** | Malaya docs: https://malaya.readthedocs.io — or skip; not receipt-shaped anyway |

## The gap no public dataset fills (Stage-Gate 1)

No public data has Manglish terms (*kopi c peng*, *upah pasang*, *minyak hitam*),
SST registration numbers, or Kuching handwritten chits. These MUST be collected:

- `real_thermal_receipt_redacted` — faded thermal (buy something, shoot your own receipt)
- `real_tax_invoice_redacted` — printed tax invoice from a Kuching supplier
- `real_kuching_chit_redacted` — handwritten chit via contact; redact name/phone/address/payment refs/invoice no./QR

Drop them in `dataset/field_collected/` with a source note per file:
`"Received from <merchant type>, Kuching, <date>; customer/payment details redacted; permission: yes"`.
3 files pass the gate; ~10–15 give a defensible holdout for Step 2 confidence-scoring.
