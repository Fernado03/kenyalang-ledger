"""Deterministic reconciliation audit (docs/05_trd.md §5.4, REQ-104).

The two contract cases from the sprint brief are ``test_math_reconciliation_pass``
(Case A) and ``test_math_delta_triggers_review`` (Case B); the rest pin the
individual rules the status is derived from.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.receipt import ReceiptStatus
from app.schemas.receipt import (
    ExtractedField,
    ExtractedReceiptData,
    LineItemSchema,
    ParsedReceiptSchema,
)
from app.services.reconciler import (
    CONFIDENCE_THRESHOLD,
    MATH_TOLERANCE,
    MAX_RECEIPT_AGE_DAYS,
    ReconcilerService,
    extract_sst_number,
)

TODAY = date(2026, 10, 5)


def _line(
    index: int, description: str, total: str, confidence: float = 1.0
) -> LineItemSchema:
    return LineItemSchema(
        line_index=index,
        description=description,
        quantity=Decimal("1.00"),
        unit_price=Decimal(total),
        line_total=Decimal(total),
        confidence=confidence,
    )


def _parsed(**overrides) -> ParsedReceiptSchema:
    """A fully consistent receipt: RM 99.50 of lines + RM 5.97 SST = RM 105.47."""
    base = {
        "merchant_name": "Kim Guan Hardware",
        "merchant_brn": "202001012345",
        "merchant_sst": "W10-1808-32000018",
        "invoice_date": TODAY - timedelta(days=7),
        "invoice_number": "INV-99120",
        "subtotal": Decimal("99.50"),
        "tax_amount": Decimal("5.97"),
        "grand_total": Decimal("105.47"),
        "line_items": [
            _line(0, 'PVC Pipe 2"', "14.50"),
            _line(1, "Minyak Hitam 4L", "85.00"),
        ],
    }
    base.update(overrides)
    parsed = ParsedReceiptSchema(**base)
    if "fields" not in overrides:
        parsed.fields = [
            ExtractedField(name=name, confidence=0.95)
            for name in (
                "merchant_name",
                "invoice_date",
                "grand_total",
                "subtotal",
                "tax_amount",
            )
        ]
    return parsed


# --------------------------------------------------------------------------- #
# Case A: the arithmetic identity holds -> auto-verified
# --------------------------------------------------------------------------- #


def test_math_reconciliation_pass() -> None:
    """Matching line items + tax is auto-verified with a zero discrepancy."""
    result = ReconcilerService.audit_receipt(_parsed(), today=TODAY)

    assert result.status is ReceiptStatus.STATUS_AUTO_VERIFIED
    assert result.flags == []
    assert result.math_discrepancy == Decimal("0.00")


# --------------------------------------------------------------------------- #
# Case B: the arithmetic identity breaks -> human review
# --------------------------------------------------------------------------- #


def test_math_delta_triggers_review() -> None:
    """RM 50 of lines against a RM 70 total must flag the RM 20.00 gap."""
    result = ReconcilerService.audit_receipt(
        _parsed(
            merchant_sst=None,
            subtotal=Decimal("50.00"),
            tax_amount=Decimal("0.00"),
            grand_total=Decimal("70.00"),
            line_items=[_line(0, "Upah Pasang", "50.00")],
        ),
        today=TODAY,
    )

    assert result.status is ReceiptStatus.STATUS_NEEDS_REVIEW
    assert "MATH_MISMATCH_DELTA_20.00" in result.flags
    assert result.math_discrepancy == Decimal("20.00")


def test_delta_at_tolerance_is_not_flagged() -> None:
    """Rounding slack up to the documented RM 0.02 must not route to review."""
    result = ReconcilerService.audit_receipt(
        _parsed(
            merchant_sst=None,
            tax_amount=Decimal("0.00"),
            grand_total=Decimal("99.52"),  # lines sum to 99.50
        ),
        today=TODAY,
    )

    assert result.math_discrepancy == MATH_TOLERANCE
    assert result.status is ReceiptStatus.STATUS_AUTO_VERIFIED


def test_delta_just_over_tolerance_is_flagged() -> None:
    result = ReconcilerService.audit_receipt(
        _parsed(
            merchant_sst=None,
            tax_amount=Decimal("0.00"),
            grand_total=Decimal("99.53"),
        ),
        today=TODAY,
    )

    assert "MATH_MISMATCH_DELTA_0.03" in result.flags
    assert result.status is ReceiptStatus.STATUS_NEEDS_REVIEW


def test_raw_delta_is_compared_before_quantizing() -> None:
    """RM 0.024 exceeds RM 0.02 on the raw delta, not on the stored 0.02 value."""
    result = ReconcilerService.audit_receipt(
        _parsed(
            merchant_sst=None,
            tax_amount=Decimal("0.00"),
            grand_total=Decimal("99.524"),
        ),
        today=TODAY,
    )

    assert ReconcilerService._math_discrepancy(
        _parsed(
            merchant_sst=None, tax_amount=Decimal("0.00"), grand_total=Decimal("99.524")
        )
    ) == Decimal("0.024")
    assert "MATH_MISMATCH_DELTA_0.02" in result.flags
    assert result.status is ReceiptStatus.STATUS_NEEDS_REVIEW


def test_faded_receipt_reconciles_subtotal_against_total() -> None:
    """No readable line items: the printed subtotal is the fallback (§5.4 line 142)."""
    result = ReconcilerService.audit_receipt(
        _parsed(line_items=[], subtotal=Decimal("99.50"), tax_amount=Decimal("5.97")),
        today=TODAY,
    )

    assert result.status is ReceiptStatus.STATUS_AUTO_VERIFIED


def test_unreconcilable_receipt_is_flagged_missing_subtotal() -> None:
    result = ReconcilerService.audit_receipt(
        _parsed(line_items=[], subtotal=None), today=TODAY
    )

    assert "MISSING_SUBTOTAL" in result.flags
    assert result.status is ReceiptStatus.STATUS_NEEDS_REVIEW


def test_missing_grand_total_is_flagged_invalid_not_missing_subtotal() -> None:
    """A null total is INVALID_GRAND_TOTAL, never a subtotal problem."""
    result = ReconcilerService.audit_receipt(
        _parsed(grand_total=None, line_items=[], subtotal=Decimal("99.50")),
        today=TODAY,
    )

    assert "INVALID_GRAND_TOTAL" in result.flags
    assert "MISSING_SUBTOTAL" not in result.flags
    assert result.math_discrepancy == Decimal("0.00")
    assert result.status is ReceiptStatus.STATUS_NEEDS_REVIEW


# --------------------------------------------------------------------------- #
# Mandatory fields and date sanity
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("overrides", "expected_flag"),
    [
        ({"merchant_name": None}, "MISSING_MERCHANT_NAME"),
        ({"merchant_name": " "}, "MISSING_MERCHANT_NAME"),
        ({"invoice_date": None}, "MISSING_DATE"),
        ({"grand_total": Decimal("0.00")}, "INVALID_GRAND_TOTAL"),
    ],
)
def test_missing_mandatory_field_routes_to_review(overrides, expected_flag) -> None:
    result = ReconcilerService.audit_receipt(_parsed(**overrides), today=TODAY)

    assert expected_flag in result.flags
    assert result.status is ReceiptStatus.STATUS_NEEDS_REVIEW


def test_future_dated_receipt_is_flagged() -> None:
    result = ReconcilerService.audit_receipt(
        _parsed(invoice_date=TODAY + timedelta(days=1)), today=TODAY
    )

    assert "DATE_IN_FUTURE" in result.flags


def test_receipt_older_than_one_year_is_flagged() -> None:
    result = ReconcilerService.audit_receipt(
        _parsed(invoice_date=TODAY - timedelta(days=MAX_RECEIPT_AGE_DAYS + 1)),
        today=TODAY,
    )

    assert "DATE_EXCEEDS_1_YEAR" in result.flags


def test_receipt_exactly_one_year_old_is_accepted() -> None:
    result = ReconcilerService.audit_receipt(
        _parsed(invoice_date=TODAY - timedelta(days=MAX_RECEIPT_AGE_DAYS)), today=TODAY
    )

    assert "DATE_EXCEEDS_1_YEAR" not in result.flags


# --------------------------------------------------------------------------- #
# Confidence gate
# --------------------------------------------------------------------------- #


def test_low_confidence_field_routes_to_review() -> None:
    parsed = _parsed()
    parsed.fields = [
        ExtractedField(name="merchant_name", confidence=CONFIDENCE_THRESHOLD - 0.01),
        ExtractedField(name="invoice_date", confidence=0.95),
        ExtractedField(name="grand_total", confidence=0.95),
    ]

    result = ReconcilerService.audit_receipt(parsed, today=TODAY)

    assert "LOW_CONFIDENCE_merchant_name" in result.flags
    assert result.status is ReceiptStatus.STATUS_NEEDS_REVIEW
    assert result.overall_confidence == pytest.approx(
        CONFIDENCE_THRESHOLD - 0.01, abs=0.01
    )


def test_low_confidence_line_item_routes_to_review() -> None:
    parsed = _parsed(
        line_items=[_line(0, "Teh O Peng", "4.00", confidence=0.55)],
        subtotal=Decimal("4.00"),
        tax_amount=Decimal("0.00"),
        grand_total=Decimal("4.00"),
    )

    result = ReconcilerService.audit_receipt(parsed, today=TODAY)

    assert "LOW_CONFIDENCE_line_items[0]" in result.flags


def test_two_low_confidence_fields_produce_one_flag_each() -> None:
    parsed = _parsed()
    parsed.fields = [
        ExtractedField(name="merchant_name", confidence=0.50),
        ExtractedField(name="merchant_sst", confidence=0.60),
        ExtractedField(name="invoice_date", confidence=0.55),
        ExtractedField(name="grand_total", confidence=0.95),
    ]

    result = ReconcilerService.audit_receipt(parsed, today=TODAY)

    # Names must never be concatenated into "merchant_sst_invoice_date".
    assert [f for f in result.flags if f.startswith("LOW_CONFIDENCE_")] == [
        "LOW_CONFIDENCE_merchant_name",
        "LOW_CONFIDENCE_merchant_sst",
        "LOW_CONFIDENCE_invoice_date",
    ]


def test_confidence_exactly_at_threshold_passes() -> None:
    parsed = _parsed()
    parsed.fields = [
        ExtractedField(name="merchant_name", confidence=0.95),
        ExtractedField(name="invoice_date", confidence=0.95),
        ExtractedField(name="grand_total", confidence=CONFIDENCE_THRESHOLD),
    ]

    result = ReconcilerService.audit_receipt(parsed, today=TODAY)

    assert result.status is ReceiptStatus.STATUS_AUTO_VERIFIED


def test_absent_critical_evidence_blocks_auto_verification() -> None:
    """No provenance for a critical field means no OCR evidence: fail closed."""
    parsed = _parsed()
    parsed.fields = [
        ExtractedField(name="merchant_name", confidence=0.95),
        ExtractedField(name="invoice_date", confidence=0.95),
    ]

    result = ReconcilerService.audit_receipt(parsed, today=TODAY)

    assert "MISSING_CRITICAL_EVIDENCE_grand_total" in result.flags
    assert result.status is ReceiptStatus.STATUS_NEEDS_REVIEW


def test_critical_field_with_unsupported_value_is_flagged() -> None:
    """A provenance entry whose value is absent carries no evidence either."""
    parsed = _parsed()
    parsed.fields = [
        ExtractedField(name="merchant_name", confidence=0.95),
        ExtractedField(name="invoice_date", confidence=0.95),
        ExtractedField(name="grand_total", confidence=0.95),
    ]
    parsed.grand_total = None

    result = ReconcilerService.audit_receipt(parsed, today=TODAY)

    assert "MISSING_CRITICAL_EVIDENCE_grand_total" in result.flags
    assert result.status is ReceiptStatus.STATUS_NEEDS_REVIEW


def test_missing_critical_evidence_floors_overall_confidence() -> None:
    """Unknown critical evidence is 0.0, not the 0.95 the other fields report."""
    parsed = _parsed()
    parsed.fields = [
        ExtractedField(name="merchant_name", confidence=0.95),
        ExtractedField(name="invoice_date", confidence=0.95),
    ]

    result = ReconcilerService.audit_receipt(parsed, today=TODAY)

    assert result.overall_confidence == 0.0


# --------------------------------------------------------------------------- #
# SST-specific rule
# --------------------------------------------------------------------------- #


def test_sst_registered_merchant_without_tax_is_flagged() -> None:
    """A registered SST number plus zero tax is a data-entry error, not a tax-free sale.

    This is a review heuristic only: it does not assert that every SST-registered
    receipt must charge SST.
    """
    result = ReconcilerService.audit_receipt(
        _parsed(
            merchant_sst="W10-1808-32000018",
            tax_amount=Decimal("0.00"),
            subtotal=Decimal("105.47"),
            grand_total=Decimal("105.47"),
            line_items=[],
        ),
        today=TODAY,
    )

    assert "MISSING_SST_ON_REGISTERED_MERCHANT" in result.flags


def test_unregistered_merchant_without_tax_is_not_flagged() -> None:
    result = ReconcilerService.audit_receipt(
        _parsed(
            merchant_sst=None,
            merchant_brn="123456-X",
            tax_amount=Decimal("0.00"),
            subtotal=Decimal("105.47"),
            grand_total=Decimal("105.47"),
            line_items=[],
        ),
        today=TODAY,
    )

    assert "MISSING_SST_ON_REGISTERED_MERCHANT" not in result.flags


def test_sst_number_wrapped_with_brn_still_counts_as_registered() -> None:
    """Receipts print the SST ID beside the BRN; the audit must still see it.

    ``"200401032489 / Y24-1808-31015655"`` is what extraction produces from a
    header like "No. Pendaftaran (BRN) / SST ID". Requiring the whole field to
    match the registration pattern silently suppresses the missing-tax flag on a
    genuinely SST-registered merchant.
    """
    result = ReconcilerService.audit_receipt(
        _parsed(
            merchant_sst="200401032489 / y24-1808-31015655",
            tax_amount=Decimal("0.00"),
            subtotal=Decimal("105.47"),
            grand_total=Decimal("105.47"),
            line_items=[],
        ),
        today=TODAY,
    )

    assert extract_sst_number("200401032489 / y24-1808-31015655") == "Y24-1808-31015655"
    assert "MISSING_SST_ON_REGISTERED_MERCHANT" in result.flags


# --------------------------------------------------------------------------- #
# Bounding box validation at the extraction boundary
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "bbox",
    [
        [0.1, 0.2, 0.9],  # too few corners
        [0.1, 0.2, 0.9, 0.4, 0.5],  # too many corners
        [0.1, 0.2, 1.4, 0.5],  # not normalized
        [0.9, 0.2, 0.1, 0.5],  # inverted x corners
        [0.1, 0.8, 0.9, 0.2],  # inverted y corners
    ],
)
def test_malformed_bbox_is_rejected(bbox) -> None:
    with pytest.raises(ValidationError):
        ExtractedField(name="grand_total", confidence=0.95, bbox=bbox)


def test_well_formed_bbox_is_accepted() -> None:
    field = ExtractedField(
        name="grand_total", confidence=0.95, bbox=[0.1, 0.2, 0.9, 0.5]
    )

    assert field.bbox == [0.1, 0.2, 0.9, 0.5]


def test_non_finite_money_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ExtractedReceiptData(merchant_name="Kopi Shop", grand_total=Decimal("NaN"))
