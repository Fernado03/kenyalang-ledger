"""Deterministic rule-based math and verification engine (docs/05_trd.md §5.4, REQ-104).

Pure functions over a ``ParsedReceiptSchema``: no I/O, no clock injection beyond
``today``, no LLM. Every flag string this module emits is persisted verbatim into
``receipts.validation_flags`` and rendered by the review console, so the names are
part of the API surface (docs/06_schema_api.md §6.3.2).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.receipt import ReceiptStatus
from app.schemas.receipt import (
    AMOUNT_BASIS_EXCLUSIVE,
    AMOUNT_BASIS_INCLUSIVE,
    ParsedReceiptSchema,
    normalize_amount_basis,
)

# docs/05_trd.md §5.4 line 140: rounding slack on the arithmetic identity.
MATH_TOLERANCE: Decimal = Decimal("0.02")
# docs/05_trd.md §5.4 line 161: below this, a human confirms the field.
CONFIDENCE_THRESHOLD: float = 0.80
# docs/05_trd.md §5.4 line 131: receipts older than this are out of period.
MAX_RECEIPT_AGE_DAYS: int = 365

# SST registration format, e.g. W10-1808-32000018 (docs/05_trd.md §5.3.1).
SST_NUMBER_RE = re.compile(r"^[A-Z]\d+-\d+-\d+$")
# The registered shape: state letter + 2-digit state code, 4-digit branch, 8-digit
# serial. Stricter than SST_NUMBER_RE, which only has to find a token inside a
# compound field; this one decides whether the value is a usable registration.
# There is no check digit in the format, so it catches structural damage only --
# a well-formed digit substitution (1808 -> 7808) still passes.
SST_REGISTRATION_RE = re.compile(r"^[A-Z]\d{2}-\d{4}-\d{8}$")
# Receipts print the SST ID next to the BRN ("200401032489 / Y24-1808-31015655"),
# so extraction and manual entry both concatenate the two. Search anywhere in the
# field for the first well-formed SST number instead of demanding the whole string.
_SST_TOKEN_RE = re.compile(r"[A-Z]\d+-\d+-\d+")


def extract_sst_number(value: str | None) -> str | None:
    """Return the canonical SST number inside ``value``, or ``None``.

    The registration format is fixed, so a value that carries other identifiers
    alongside it (a BRN, "SST ID:" label, separators) still yields the real SST
    number. Used by both the audit (is this merchant SST-registered?) and the
    MyInvois export (which must not ship a compound party ID).
    """
    if not value:
        return None
    match = _SST_TOKEN_RE.search(value.strip().upper())
    return match.group(0) if match else None


MONEY = Decimal("0.01")

# Fields a receipt cannot be auto-verified without: no provenance entry for one
# of these means the value has no OCR evidence, so the audit fails closed.
CRITICAL_FIELDS: tuple[str, ...] = ("merchant_name", "invoice_date", "grand_total")

# Values that count as "no evidence" for a critical field.
_ABSENT: tuple[object, ...] = (None, "")


def _is_unsupported(data: ParsedReceiptSchema, name: str) -> bool:
    """True when a critical field's provenance carries no OCR evidence."""
    return getattr(data, name) in _ABSENT


class AuditResult(BaseModel):
    """Outcome of the §5.4 audit, shaped for direct persistence onto ``receipts``."""

    status: ReceiptStatus
    flags: list[str] = Field(default_factory=list)
    math_discrepancy: Decimal = Decimal("0.00")
    overall_confidence: float = 0.0


class ReconcilerService:
    """Stateless audit engine (docs/05_trd.md §5.4)."""

    @staticmethod
    def audit_receipt(
        data: ParsedReceiptSchema, today: date | None = None
    ) -> AuditResult:
        """Run every deterministic check and return the receipt's status."""
        flags: list[str] = []

        # 1. Mandatory fields
        if not data.merchant_name or len(data.merchant_name.strip()) < 2:
            flags.append("MISSING_MERCHANT_NAME")
        if not data.invoice_date:
            flags.append("MISSING_DATE")
        if data.grand_total is None or data.grand_total <= 0:
            flags.append("INVALID_GRAND_TOTAL")

        # 2. Date sanity: never in the future, never out of period
        if data.invoice_date:
            reference = today or date.today()
            if data.invoice_date > reference:
                flags.append("DATE_IN_FUTURE")
            elif (reference - data.invoice_date).days > MAX_RECEIPT_AGE_DAYS:
                flags.append("DATE_EXCEEDS_1_YEAR")

        # 3. Arithmetic reconciliation: sum(line_total) + tax == grand_total
        discrepancy = ReconcilerService._math_discrepancy(data)
        if discrepancy is None:
            # Only unreconcilable when there is nothing to reconcile against: no
            # readable lines and no printed subtotal. A subtotal is valid evidence.
            if not data.line_items and data.subtotal is None:
                flags.append("MISSING_SUBTOTAL")
        elif discrepancy > MATH_TOLERANCE:
            # Compare the raw Decimal delta before any formatting or rounding.
            flags.append(f"MATH_MISMATCH_DELTA_{discrepancy:.2f}")

        # 3b. SST-registered merchant that charged no tax (docs/05_trd.md §5.4)
        if not data.tax_amount and ReconcilerService._is_sst_registered(data):
            flags.append("MISSING_SST_ON_REGISTERED_MERCHANT")

        # 3c. An SST number was printed but does not fit the registration format.
        # This catches structurally broken reads (dropped group, letter where a
        # digit belongs). It cannot catch a plausible-looking digit substitution
        # such as 1808 -> 7808: the format carries no check digit, so only the
        # confidence gate stands between a wrong-but-well-formed ID and the
        # export. Flagged rather than silently accepted.
        sst_number = extract_sst_number(data.merchant_sst)
        if sst_number is not None and not SST_REGISTRATION_RE.match(sst_number):
            flags.append("SST_FORMAT_INVALID")

        # 4. Confidence gate
        # One flag per field: joining the names produced a single chip reading
        # "LOW_CONFIDENCE_merchant_sst_invoice_date", which is indistinguishable
        # from a field genuinely called that.
        for field in data.get_fields():
            if field.confidence < CONFIDENCE_THRESHOLD:
                flags.append(f"LOW_CONFIDENCE_{field.name}")

        # 5. Critical-field provenance: a value with no OCR evidence behind it
        # cannot be auto-verified, whatever the arithmetic says.
        provenance = {f.name for f in data.fields}
        unsupported = [
            name
            for name in CRITICAL_FIELDS
            if name in provenance and _is_unsupported(data, name)
        ]
        missing = [name for name in CRITICAL_FIELDS if name not in provenance]
        if unsupported or missing:
            flags.append(
                f"MISSING_CRITICAL_EVIDENCE_{'_'.join([*unsupported, *missing])}"
            )

        status = (
            ReceiptStatus.STATUS_NEEDS_REVIEW
            if flags
            else ReceiptStatus.STATUS_AUTO_VERIFIED
        )
        return AuditResult(
            status=status,
            flags=flags,
            math_discrepancy=discrepancy or Decimal("0.00"),
            overall_confidence=ReconcilerService._overall_confidence(data),
        )

    @staticmethod
    def resolve_amount_basis(data: ParsedReceiptSchema) -> str:
        """Which arithmetic identity this receipt's line totals satisfy.

        The printed basis wins when the extractor reported one. Otherwise infer
        it from the numbers: an exclusive receipt satisfies ``Σlines + tax ==
        total``, an inclusive one satisfies ``Σlines == total``. Exclusive is
        tested first so a receipt with no tax (where both hold) is unchanged from
        the pre-basis behaviour. A receipt that satisfies neither is treated as
        exclusive, which is what the reconciler has always assumed, so an
        unreconcilable record still reports the same delta it did before.
        """
        explicit = normalize_amount_basis(data.amount_basis)
        if explicit is not None:
            return explicit

        if data.grand_total is None or not data.line_items:
            return AMOUNT_BASIS_EXCLUSIVE

        tax = data.tax_amount or Decimal("0.00")
        line_sum = sum(
            (item.line_total for item in data.line_items), Decimal("0.00")
        )
        if abs((line_sum + tax) - data.grand_total) <= MATH_TOLERANCE:
            return AMOUNT_BASIS_EXCLUSIVE
        if abs(line_sum - data.grand_total) <= MATH_TOLERANCE:
            return AMOUNT_BASIS_INCLUSIVE
        return AMOUNT_BASIS_EXCLUSIVE

    @staticmethod
    def _math_discrepancy(data: ParsedReceiptSchema) -> Decimal | None:
        """``|expected - grand_total|``, or None when unreconcilable.

        Line items are authoritative; a faded receipt with no readable lines falls
        back to the printed subtotal (docs/05_trd.md §5.4 line 142).

        ``expected`` depends on the tax basis (docs/05_trd.md §5.4): when the
        printed line totals are GST-inclusive they already contain the tax, so
        adding ``tax`` counts it twice — the bug that flagged every correct
        Malaysian retail receipt with a delta exactly equal to the tax.

        A printed till-rounding line is part of the receipt's own arithmetic, so
        it joins the identity rather than being absorbed by a wider tolerance.
        Without it a correctly-printed receipt that rounds 75.79 down to 75.75
        reports a RM 0.04 error that the accountant cannot fix.
        """
        if data.grand_total is None:
            return None
        tax = data.tax_amount or Decimal("0.00")
        rounding = data.rounding or Decimal("0.00")
        basis = ReconcilerService.resolve_amount_basis(data)

        if data.line_items:
            expected = sum(
                (item.line_total for item in data.line_items), Decimal("0.00")
            )
            if basis == AMOUNT_BASIS_EXCLUSIVE:
                expected += tax
        elif data.subtotal is not None:
            # A printed subtotal is the tax-exclusive figure on the receipt
            # layouts this app targets, so tax is added on top either way.
            expected = data.subtotal + tax
        else:
            return None

        expected += rounding

        # Raw delta: the RM 0.02 tolerance is compared against this unquantized
        # value, so a 0.024 gap is not silently rounded down to 0.02 first.
        return abs(expected - data.grand_total)

    @staticmethod
    def _is_sst_registered(data: ParsedReceiptSchema) -> bool:
        return extract_sst_number(data.merchant_sst) is not None

    @staticmethod
    def _overall_confidence(data: ParsedReceiptSchema) -> float:
        """Confidence of the whole record: the least-trusted field bounds it.

        A receipt is never more trustworthy than its shakiest audited field, and a
        record with no measurable provenance gets 0.0 so it cannot slip through the
        gate on an empty evidence set. A critical field with no evidence at all is
        unknown, not high-confidence, so it floors the whole record at 0.0.
        """
        provenance = {f.name for f in data.fields}
        if any(
            name not in provenance or _is_unsupported(data, name)
            for name in CRITICAL_FIELDS
        ):
            return 0.0
        confidences = [f.confidence for f in data.get_fields()]
        return round(min(confidences), 2) if confidences else 0.0


__all__ = [
    "CONFIDENCE_THRESHOLD",
    "MATH_TOLERANCE",
    "MAX_RECEIPT_AGE_DAYS",
    "AuditResult",
    "ReconcilerService",
    "extract_sst_number",
]
