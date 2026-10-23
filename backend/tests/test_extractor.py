"""Token pruning and per-field provenance (docs/05_trd.md §5.3.2, REQ-103/109).

The LLM completion itself is not exercised here: it needs a live model. What is
tested is the deterministic half of the extractor -- the reading-order sort, the
prompt rendering, and the mapping from extracted values back to the OCR tokens
that back them, which is where per-field confidence actually comes from.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.pipeline.extractor import (
    UNSUPPORTED_CONFIDENCE,
    _clean_line_item_descriptions,
    _strip_price_from_description,
    attach_provenance,
    render_tokens,
    sort_tokens,
)
from app.pipeline.ocr_engine import OCRToken
from app.schemas.receipt import ExtractedReceiptData, LineItemSchema


def _token(
    text: str, confidence: float, x: float, y: float, line_num: int = 0
) -> OCRToken:
    return OCRToken(
        text=text,
        confidence=confidence,
        bbox=[x, y, x + 0.2, y + 0.03],
        line_num=line_num,
    )


# --------------------------------------------------------------------------- #
# §5.3.2 token pruning
# --------------------------------------------------------------------------- #


def test_sort_tokens_reads_top_to_bottom_then_left_to_right() -> None:
    tokens = [
        _token("BOTTOM", 0.9, 0.1, 0.80),
        _token("RIGHT", 0.9, 0.70, 0.10),
        _token("LEFT", 0.9, 0.10, 0.10),
        _token("MIDDLE", 0.9, 0.10, 0.40),
    ]

    assert [t.text for t in sort_tokens(tokens)] == [
        "LEFT",
        "RIGHT",
        "MIDDLE",
        "BOTTOM",
    ]


def test_render_tokens_groups_rows_in_reading_order() -> None:
    tokens = [
        _token("KIM GUAN HARDWARE", 0.96, 0.05, 0.10, line_num=0),
        _token("SDN BHD", 0.94, 0.60, 0.10, line_num=0),
        _token("TOTAL", 0.95, 0.05, 0.40, line_num=1),
        _token("14.50", 0.93, 0.70, 0.40, line_num=1),
    ]

    assert render_tokens(tokens).splitlines() == [
        "[0.100] KIM GUAN HARDWARE SDN BHD",
        "[0.400] TOTAL 14.50",
    ]


def test_render_tokens_orders_rows_by_vertical_position() -> None:
    """Row order follows geometry, not the order the OCR engine emitted lines in."""
    tokens = [
        _token("SECOND", 0.9, 0.1, 0.50, line_num=7),
        _token("FIRST", 0.9, 0.1, 0.10, line_num=3),
    ]

    assert [line.split("] ")[1] for line in render_tokens(tokens).splitlines()] == [
        "FIRST",
        "SECOND",
    ]


def test_render_tokens_never_moves_a_token_out_of_its_visual_row() -> None:
    """A scrambled ``line_num`` must not regroup tokens that share a row."""
    tokens = [
        _token("KIM GUAN", 0.96, 0.05, 0.10, line_num=5),
        _token("HARDWARE", 0.95, 0.40, 0.10, line_num=2),
        _token("SDN BHD", 0.94, 0.70, 0.10, line_num=9),
        _token("TOTAL", 0.93, 0.05, 0.40, line_num=1),
        _token("14.50", 0.92, 0.70, 0.40, line_num=4),
    ]

    assert render_tokens(tokens).splitlines() == [
        "[0.100] KIM GUAN HARDWARE SDN BHD",
        "[0.400] TOTAL 14.50",
    ]


def test_render_tokens_keeps_interleaved_line_numbers_in_geometric_order() -> None:
    """Interleaved ``line_num`` values still render top-to-bottom by ``y_min``."""
    tokens = [
        _token("B", 0.9, 0.1, 0.50, line_num=0),
        _token("A", 0.9, 0.1, 0.10, line_num=1),
        _token("C", 0.9, 0.1, 0.90, line_num=2),
    ]

    assert [line.split("] ")[1] for line in render_tokens(tokens).splitlines()] == [
        "A",
        "B",
        "C",
    ]


# --------------------------------------------------------------------------- #
# Provenance: confidence is measured, not self-reported
# --------------------------------------------------------------------------- #


def test_attach_provenance_uses_the_supporting_token_confidence() -> None:
    tokens = [
        _token("KIM GUAN HARDWARE", 0.96, 0.05, 0.10),
        _token("TOTAL", 0.99, 0.05, 0.40),
        _token("RM 105.47", 0.88, 0.70, 0.40),
    ]
    data = ExtractedReceiptData(
        merchant_name="Kim Guan Hardware", grand_total=Decimal("105.47")
    )

    parsed = attach_provenance(data, tokens)
    confidence = {field.name: field for field in parsed.fields}

    assert confidence["merchant_name"].confidence == 0.96
    assert confidence["grand_total"].confidence == 0.88
    assert confidence["grand_total"].bbox == pytest.approx([0.70, 0.40, 0.90, 0.43])


def test_unsupported_value_gets_zero_confidence() -> None:
    """A hallucinated total no token mentions must not pass the review gate."""
    tokens = [_token("KIM GUAN HARDWARE", 0.96, 0.05, 0.10)]
    data = ExtractedReceiptData(
        merchant_name="Kim Guan Hardware", grand_total=Decimal("999.99")
    )

    parsed = attach_provenance(data, tokens)

    assert {f.name: f.confidence for f in parsed.fields}[
        "grand_total"
    ] == UNSUPPORTED_CONFIDENCE


def test_absent_fields_are_not_given_provenance() -> None:
    """Only populated fields are audited; the mandatory-field check owns the rest."""
    data = ExtractedReceiptData(merchant_name="Kopi Shop", grand_total=Decimal("4.00"))

    parsed = attach_provenance(data, [_token("KOPI SHOP", 0.9, 0.1, 0.1)])

    assert [field.name for field in parsed.fields] == ["merchant_name", "grand_total"]


@pytest.mark.parametrize("rendering", ["12/09/2026", "12-09-2026", "2026-09-12"])
def test_date_provenance_matches_common_malaysian_renderings(rendering: str) -> None:
    tokens = [_token(rendering, 0.91, 0.1, 0.2)]
    data = ExtractedReceiptData(
        grand_total=Decimal("10.00"), invoice_date=date(2026, 9, 12)
    )

    parsed = attach_provenance(data, tokens)

    assert {f.name: f.confidence for f in parsed.fields}["invoice_date"] == 0.91


def test_line_item_confidence_is_bounded_by_its_weakest_evidence() -> None:
    tokens = [
        _token("MINYAK HITAM 4L", 0.95, 0.05, 0.2),
        _token("85.00", 0.62, 0.70, 0.2),
    ]
    data = ExtractedReceiptData(
        grand_total=Decimal("85.00"),
        line_items=[
            LineItemSchema(
                line_index=0,
                description="Minyak Hitam 4L",
                quantity=Decimal("1.00"),
                unit_price=Decimal("85.00"),
                line_total=Decimal("85.00"),
            )
        ],
    )

    parsed = attach_provenance(data, tokens)

    assert parsed.line_items[0].confidence == 0.62


def test_line_item_without_any_supporting_token_gets_zero_confidence() -> None:
    data = ExtractedReceiptData(
        grand_total=Decimal("4.00"),
        line_items=[
            LineItemSchema(
                line_index=0, description="Teh O Peng", line_total=Decimal("4.00")
            )
        ],
    )

    parsed = attach_provenance(data, [_token("UNRELATED", 0.9, 0.1, 0.1)])

    assert parsed.line_items[0].confidence == UNSUPPORTED_CONFIDENCE


# --------------------------------------------------------------------------- #
# Conservative provenance: no token, no confidence
# --------------------------------------------------------------------------- #


def test_partial_merchant_name_does_not_certify_a_fuller_name() -> None:
    """A substring match is not evidence for the unsupported part of the name."""
    tokens = [_token("KIM GUAN", 0.96, 0.05, 0.10)]
    data = ExtractedReceiptData(
        merchant_name="Kim Guan Hardware Sdn Bhd", grand_total=Decimal("10.00")
    )

    parsed = attach_provenance(data, tokens)

    assert {f.name: f.confidence for f in parsed.fields}[
        "merchant_name"
    ] == UNSUPPORTED_CONFIDENCE


def test_line_item_with_amount_but_no_description_gets_zero_confidence() -> None:
    """A readable total with no readable description is not a verified line."""
    tokens = [_token("50.00", 0.95, 0.70, 0.25)]
    data = ExtractedReceiptData(
        grand_total=Decimal("50.00"),
        line_items=[
            LineItemSchema(
                line_index=0,
                description="PVC Pipe",
                quantity=Decimal("1.00"),
                unit_price=Decimal("50.00"),
                line_total=Decimal("50.00"),
            )
        ],
    )

    parsed = attach_provenance(data, tokens)

    assert parsed.line_items[0].confidence == UNSUPPORTED_CONFIDENCE


def test_line_item_with_description_but_no_amount_gets_zero_confidence() -> None:
    """A readable description with no readable amount is not a verified line."""
    tokens = [_token("PVC PIPE", 0.95, 0.05, 0.25)]
    data = ExtractedReceiptData(
        grand_total=Decimal("50.00"),
        line_items=[
            LineItemSchema(
                line_index=0,
                description="PVC Pipe",
                quantity=Decimal("1.00"),
                unit_price=Decimal("50.00"),
                line_total=Decimal("50.00"),
            )
        ],
    )

    parsed = attach_provenance(data, tokens)

    assert parsed.line_items[0].confidence == UNSUPPORTED_CONFIDENCE


def test_repeated_total_does_not_certify_a_different_total() -> None:
    """The same amount printed twice is still one piece of evidence, not two."""
    tokens = [
        _token("50.00", 0.95, 0.70, 0.25),
        _token("50.00", 0.94, 0.70, 0.40),
    ]
    data = ExtractedReceiptData(grand_total=Decimal("70.00"))

    parsed = attach_provenance(data, tokens)

    assert {f.name: f.confidence for f in parsed.fields}[
        "grand_total"
    ] == UNSUPPORTED_CONFIDENCE


def test_date_digits_are_not_evidence_for_a_total() -> None:
    """A date's digits must not certify an unrelated amount."""
    tokens = [_token("12/09/2026", 0.95, 0.1, 0.2)]
    data = ExtractedReceiptData(grand_total=Decimal("12.09"))

    parsed = attach_provenance(data, tokens)

    assert {f.name: f.confidence for f in parsed.fields}[
        "grand_total"
    ] == UNSUPPORTED_CONFIDENCE


def test_brn_digits_are_not_evidence_for_a_total() -> None:
    """A registration number's digits must not certify an unrelated amount."""
    tokens = [_token("202001012345", 0.95, 0.1, 0.2)]
    data = ExtractedReceiptData(grand_total=Decimal("2020.01"))

    parsed = attach_provenance(data, tokens)

    assert {f.name: f.confidence for f in parsed.fields}[
        "grand_total"
    ] == UNSUPPORTED_CONFIDENCE


def test_currency_marker_is_stripped_without_corrupting_words() -> None:
    """``rm`` inside a word is text, not a currency marker."""
    from app.pipeline.extractor import _normalize

    assert _normalize("RM 105.47") == "105.47"
    assert _normalize("storm") == "storm"
    assert _normalize("form") == "form"
    assert _normalize("kopirm") == "kopirm"
    assert _normalize("MYR 5.00") == "5.00"
    assert _normalize("$5.00") == "5.00"


def test_multi_token_merchant_name_is_matched_on_a_distinctive_word() -> None:
    """A full name spread across tokens is supported by any distinctive word.

    Only words of 4+ characters count as distinctive, so the short "SDN"/"BHD"
    tokens do not by themselves certify the name; the best token carrying a
    distinctive word ("HARDWARE") sets the confidence.
    """
    tokens = [
        _token("KIM", 0.90, 0.05, 0.10),
        _token("GUAN", 0.91, 0.20, 0.10),
        _token("HARDWARE", 0.92, 0.35, 0.10),
        _token("SDN", 0.93, 0.55, 0.10),
        _token("BHD", 0.94, 0.70, 0.10),
    ]
    data = ExtractedReceiptData(
        merchant_name="Kim Guan Hardware Sdn Bhd", grand_total=Decimal("10.00")
    )

    parsed = attach_provenance(data, tokens)

    assert {f.name: f.confidence for f in parsed.fields}["merchant_name"] == 0.92


def test_amount_on_a_single_row_token_is_evidence() -> None:
    """A row token carrying description, quantity and amount supports the line."""
    tokens = [_token("PVC Pipe 1 50.00 50.00", 0.91, 0.05, 0.25)]
    data = ExtractedReceiptData(
        grand_total=Decimal("50.00"),
        line_items=[
            LineItemSchema(
                line_index=0,
                description="PVC Pipe",
                quantity=Decimal("1.00"),
                unit_price=Decimal("50.00"),
                line_total=Decimal("50.00"),
            )
        ],
    )

    parsed = attach_provenance(data, tokens)

    assert parsed.line_items[0].confidence == 0.91


@pytest.mark.parametrize(
    "ocr_text",
    [
        "75 .75",  # EasyOCR split the decimal from the integer (real 1568x875 scan)
        "75. 75",
        "75 , 75",
    ],
)
def test_a_spaced_decimal_still_supports_the_total(ocr_text: str) -> None:
    """OCR spaces inside a decimal must not cost the field its evidence.

    Observed on a real scan where the printed ``75.75`` came back as ``75 .75``:
    the digits parsed as two unrelated numbers, so a *correct* total matched no
    token and the whole record was floored to 0% confidence by the critical-field
    rule. A spacing artefact is not a reason to distrust a value.
    """
    tokens = [
        _token("TOTAL :", 0.63, 0.05, 0.70),
        _token(ocr_text, 0.98, 0.70, 0.70),
    ]
    data = ExtractedReceiptData(grand_total=Decimal("75.75"))

    parsed = attach_provenance(data, tokens)

    field = next(f for f in parsed.fields if f.name == "grand_total")
    assert field.confidence == 0.98
    assert field.bbox is not None


def test_a_comma_decimal_still_supports_the_total() -> None:
    """``24,00`` is 24.00 on a Malaysian receipt, not twenty-four thousand."""
    tokens = [
        _token("ROLLER BRUSH 7\"", 0.87, 0.05, 0.40),
        _token("24,00", 0.83, 0.70, 0.40),
    ]
    data = ExtractedReceiptData(
        line_items=[
            LineItemSchema(
                line_index=0,
                description="ROLLER BRUSH 7\"",
                quantity=Decimal("2.00"),
                unit_price=Decimal("12.00"),
                line_total=Decimal("24.00"),
            )
        ],
    )

    parsed = attach_provenance(data, tokens)

    assert parsed.line_items[0].confidence == 0.83


def test_a_thousands_separator_is_not_mistaken_for_a_decimal() -> None:
    """``1,234.56`` must stay one thousand two hundred thirty-four, not 1.234."""
    tokens = [_token("RM 1,234.56", 0.95, 0.70, 0.70)]
    data = ExtractedReceiptData(grand_total=Decimal("1234.56"))

    parsed = attach_provenance(data, tokens)

    field = next(f for f in parsed.fields if f.name == "grand_total")
    assert field.confidence == 0.95


# --------------------------------------------------------------------------- #
# Description / price separation (REQ-109)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("description", "line_total", "expected"),
    [
        # The price leaked to the end of the name: strip it.
        ("PAKU 2 INCI 4.50", "4.50", "PAKU 2 INCI"),
        ("CAT JOTUN (KECIL) 38.00", "38.00", "CAT JOTUN (KECIL)"),
        ("AMPELAS 5.00", "5.00", "AMPELAS"),
        ('ROLLER BRUSH 7" 24.00', "24.00", 'ROLLER BRUSH 7"'),
        ("Minyak Hitam RM 85.00", "85.00", "Minyak Hitam"),
    ],
)
def test_trailing_price_is_removed_from_a_description(
    description: str, line_total: str, expected: str
) -> None:
    assert (
        _strip_price_from_description(
            description, Decimal(line_total), Decimal(line_total)
        )
        == expected
    )


@pytest.mark.parametrize(
    "description",
    [
        # A number that is part of the product name, not a price.
        "PAKU 2 INCI",
        "SHELL TELLUS 4L",
        "BATERI 12V",
        "PVC PIPE 2\"",
    ],
)
def test_a_product_number_is_not_stripped(description: str) -> None:
    """Only digits that reproduce the line's own money may be removed.

    Stripping a trailing number unconditionally would turn "PAKU 2 INCI" into
    "PAKU 2" or delete the name of a 4-litre bottle.
    """
    assert (
        _strip_price_from_description(description, Decimal("4.50"), Decimal("4.50"))
        == description
    )


def test_a_description_that_is_only_a_price_is_kept() -> None:
    """Blank the field and the auditor loses the row entirely; keep the text."""
    assert _strip_price_from_description("4.50", Decimal("4.50"), Decimal("4.50")) == "4.50"


def test_cleaning_applies_to_every_line_item() -> None:
    data = ExtractedReceiptData(
        grand_total=Decimal("75.75"),
        line_items=[
            LineItemSchema(
                line_index=0,
                description="PAKU 2 INCI 4.50",
                quantity=Decimal("1"),
                unit_price=Decimal("4.50"),
                line_total=Decimal("4.50"),
            ),
            LineItemSchema(
                line_index=1,
                description="CAT JOTUN 38.00",
                quantity=Decimal("1"),
                unit_price=Decimal("38.00"),
                line_total=Decimal("38.00"),
            ),
        ],
    )

    _clean_line_item_descriptions(data)

    assert [item.description for item in data.line_items] == [
        "PAKU 2 INCI",
        "CAT JOTUN",
    ]
