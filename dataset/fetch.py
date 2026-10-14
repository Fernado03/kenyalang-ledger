#!/usr/bin/env python3
"""Kenyalang Ledger — one-shot dataset fetcher (stdlib only, idempotent).

Run:  python dataset/fetch.py
Re-run skips files already present. No auth required for any URL below.
Datasets needing Kaggle credentials are documented in dataset/README.md, not fetched here.
"""
import os
import sys
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))

# (url, relative destination) — every URL verified reachable 2026-09-29.
LHDN = "https://sdk.myinvois.hasil.gov.my"
LHDN_V11 = [
    "1.1-Invoice-Sample", "1.1-Invoice-ForeignCurrency-Sample",
    "1.1-Invoice-MultiLineItem-Sample", "1.1-Invoice-Consolidated-Sample",
    "1.1-Credit-Note-Sample", "1.1-Debit-Note-Sample",
    "1.1-Refund-Note-Sample", "1.1-Self-Billed-Invoice-Sample",
    "1.1-Self-Billed-Credit-Sample", "1.1-Self-Billed-Debit-Sample",
    "1.1-Self-Billed-Refund-Sample",
]

FILES = [
    # --- Official LHDN MyInvois schema anchors (provenance: official_lhdn_sample) ---
    *[
        (f"{LHDN}/files/sdksamples/{n}.{ext}",
         f"official_lhdn_sample/{n}.{ext}")
        for n in LHDN_V11 for ext in ("xml", "json")
    ],
    # --- SROIE: scanned receipt key-field KIE (provenance: public_dataset) ---
    ("https://huggingface.co/datasets/arvindrajan92/sroie_document_understanding/"
     "resolve/main/data/train-00000-of-00001-66201d4afd6b73ca.parquet",
     "sroie/sroie_document_understanding_train.parquet"),
    ("https://huggingface.co/datasets/nhernandez99/sroie_dataset/resolve/main/test/metadata.jsonl",
     "sroie/nhernandez99_test_metadata.jsonl"),
    *[
        (f"https://huggingface.co/datasets/nhernandez99/sroie_dataset/resolve/main/test/{n}.jpg",
         f"sroie/images/{n}.jpg")
        for n in range(100, 120)
    ],
    # --- FUNSD: form key-value pairs (provenance: public_dataset) ---
    ("https://huggingface.co/datasets/nielsr/funsd/resolve/main/data/train-00000-of-00001.parquet",
     "funsd/funsd_train.parquet"),
    ("https://huggingface.co/datasets/nielsr/funsd/resolve/main/data/test-00000-of-00001.parquet",
     "funsd/funsd_test.parquet"),
    # --- CORU / ReceiptSense: line-item extraction labels, AR-EN receipts (public_dataset) ---
    ("https://huggingface.co/datasets/abdoelsayed/CORU/resolve/main/Receipt/train.json",
     "coru/receipt_train.json"),
    ("https://huggingface.co/datasets/abdoelsayed/CORU/resolve/main/Receipt/test.json",
     "coru/receipt_test.json"),
    ("https://huggingface.co/datasets/abdoelsayed/CORU/resolve/main/Receipt/val.json",
     "coru/receipt_val.json"),
    ("https://huggingface.co/datasets/abdoelsayed/CORU/resolve/main/Receipt/labels.txt",
     "coru/receipt_labels.txt"),
    # --- Hand-captured (phone) restaurant receipts, labelled (public_dataset) ---
    ("https://zenodo.org/api/records/13688441/files/Dataset.zip/content",
     "hand_captured_receipts/Dataset.zip"),
    # --- mychen76 invoice+receipt OCR test split (public_dataset) ---
    ("https://huggingface.co/datasets/mychen76/invoices-and-receipts_ocr_v1/resolve/main/"
     "data/test-00000-of-00001-af2d92d1cee28514.parquet",
     "invoices_receipts_ocr/invoices_receipts_test.parquet"),
]


def main() -> int:
    ok = skip = fail = 0
    for url, rel in FILES:
        dest = os.path.join(BASE, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            skip += 1
            continue
        try:
            print(f"downloading {rel} ...", flush=True)
            tmp = dest + ".part"
            urllib.request.urlretrieve(url, tmp)
            os.replace(tmp, dest)
            ok += 1
        except Exception as e:  # noqa: BLE001 — report and continue; README lists misses
            print(f"FAILED {rel}: {e}", file=sys.stderr)
            if os.path.exists(dest + ".part"):
                os.remove(dest + ".part")
            fail += 1
    print(f"done: {ok} new, {skip} skipped, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
