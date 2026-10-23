"""LLM structured entity extraction (docs/05_trd.md §5.3, REQ-103/109).

The LLM turns raw spatial OCR tokens into the flat ``ExtractedReceiptData``
accounting model. Two things happen after the model returns, both deterministic:

1. ``attach_provenance`` maps every populated header field back to the OCR token
   that carries it, so per-field confidence is *measured* from the OCR engine
   rather than self-reported by the model. A value with no supporting token gets
   confidence 0.0 and is routed to human review by the reconciler.
2. Line items keep the confidence/bbox the model cited, defaulting to 1.0.

Nothing here touches the database or the filesystem.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterable
from datetime import date
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Final

import httpx
import instructor
import openai

from app.pipeline.ocr_engine import OCRToken
from app.schemas.receipt import (
    ExtractedField,
    ExtractedReceiptData,
    ParsedReceiptSchema,
)

logger = logging.getLogger(__name__)

# Verbatim from docs/05_trd.md §5.3.1 -- do not paraphrase: the local lexicon is
# the product feature (REQ-109), and the "no hallucinated items" rule is what
# keeps faded receipts out of the math audit's failure path.
SYSTEM_PROMPT: Final = """\
You are the core extraction engine for Kenyalang Ledger, an expert Malaysian accounting parser.
Your task is to extract structured invoice/receipt data from raw OCR tokens.

CRITICAL LOCAL KNOWLEDGE:
1. Malaysian Business Reg:
   - BRN: 9-12 digits, or old format (e.g., 123456-X or 202001012345).
   - SST Number: Often formatted as [Letter][Digits]-[Digits]-[Digits] (e.g., W10-1808-32000018).
2. Currencies:
   - All amounts are in Malaysian Ringgit (MYR). Remove 'RM', 'MYR', '$' prefixes.
3. Dialect & Terminology (Sarawak/Manglish):
   - F&B: "kopi c peng", "teh o", "mee kolok", "laksa", "nasi goreng".
   - Hardware/Workshop: "minyak hitam", "upah pasang", "pvc pipe", "bateri", "tayar".
   - Labels: "Jumlah" = Total, "Cukai" = Tax, "Tarikh" = Date, "Resit Rasmi" = Official Receipt.
4. Line Item Extraction:
   - Identify line items strictly: description, quantity (default 1 if absent), unit_price, line_total.
   - description is the item NAME ONLY. Strip the price, quantity and per-unit arithmetic from it:
     "PAKU 2 INCI 4.50" -> description "PAKU 2 INCI", line_total 4.50.
     "2 ROLLER BRUSH 7\" 24.00" -> description "ROLLER BRUSH 7\"", quantity 2, unit_price 12.00.
     A description ending in a number is almost always a price that leaked in.
   - Do not hallucinate items. If line items are unreadable due to fading, extract grand_total and set line_items to empty array.
5. Rounding (rounding) -- SIGNED, usually the last line before the total:
   - Malaysian tills round the payable amount to the nearest 5 sen and print the adjustment on its own
     line: "ROUNDING -0.04", "PEMBUNDARAN 0.03", "ROUND ADJ -0.02".
   - Report that signed number as rounding. It is neither tax nor a discount, and it is NOT part of any
     line item. Include it only when the receipt actually prints such a line; otherwise omit the field.
   - The audit expects: sum(line_total) + tax + rounding == grand_total.
6. Tax Basis (amount_basis) -- REQUIRED, this drives the arithmetic audit:
   - Report whether the printed line amounts ALREADY INCLUDE the tax, or whether tax is added on top.
   - Set amount_basis to "INCLUSIVE" when sum(line_total) equals the final total, or when the receipt says
     "Total (Inclusive of GST)", "Harga termasuk GST", "Termasuk Cukai". Malaysian retail till receipts are
     usually INCLUSIVE: line 7.00 with GST 0.42 and Total 7.42 means the line is 7.00 exclusive OR 7.42
     inclusive -- read the printed arithmetic to decide.
   - Set amount_basis to "EXCLUSIVE" when sum(line_total) + tax_amount equals the final total, or when the
     receipt says "Total (Excluding GST)", "Sebelum Cukai".
   - When the receipt shows no tax, use "EXCLUSIVE".
   - Never adjust the printed line totals to force one basis: report the numbers as printed and set the basis.

Return ONLY a validated JSON payload adhering to the requested schema.
"""

# Appended to the user turn: MD_JSON is prompt-based, so the model only sees the
# schema if we spell it out. Computed once -- it is a pure function of the model.
_SCHEMA_HINT: Final = (
    "\n\nRespond with minified JSON only, no prose and no markdown fences, "
    "conforming to this JSON Schema:\n"
    + json.dumps(
        ExtractedReceiptData.model_json_schema(), separators=(",", ":"), ensure_ascii=False
    )
)

MODEL_ENV: Final = "KENYALANG_LLM_MODEL"
BASE_URL_ENV: Final = "OPENAI_BASE_URL"
API_KEY_ENV: Final = "OPENAI_API_KEY"
DEFAULT_MODEL: Final = "gpt-4o-mini"
# docs/03_appflow.md: the whole pipeline must finish in 15s or the receipt is
# marked ERR_TIMEOUT, so the LLM call may never own more than that budget.
LLM_TIMEOUT_SECONDS: Final = 15.0

# Confidence assigned to an extracted value no OCR token can back. Below the
# §5.4 review threshold by construction: unsupported means a human looks.
UNSUPPORTED_CONFIDENCE: Final = 0.0

# Values that mean "the receipt does not state this", not "the receipt says zero".
_ABSENT: Final = (None, "", 0, Decimal(0), Decimal("0.00"))

_NUMBER_RE: Final = re.compile(r"\d[\d,]*(?:\.\d+)?")
# EasyOCR routinely splits a decimal from its integer part ("75 .75", "38 .00").
# Left alone the digits parse as two unrelated numbers, so a correct total matches
# no evidence at all and floors the whole record to 0% confidence.
_SPACED_DECIMAL_RE: Final = re.compile(
    r"(?<=\d)\s*\.\s*(?=\d)"  # "75 .75" / "75. 75"
    r"|(?<=\d)\s+,\s*(?=\d)"  # "75 ,75"
    r"|(?<=\d)\s*,\s+(?=\d)"  # "75, 75"
)
# A comma between digits is a thousands separator in "1,234.56" but a decimal
# point in "24,00" — Malaysian receipts print both, sometimes in one image.
_DECIMAL_COMMA_RE: Final = re.compile(r"^\d+,\d{2}$")
# Currency markers are stripped only as standalone tokens: an unanchored "rm"
# would eat the middle of "storm" and "form".
_CURRENCY_RE: Final = re.compile(r"(?<![A-Za-z])(?:myr|rm|\$)(?![A-Za-z])")
# Two tokens belong to the same visual row when their top edges are this close
# in normalized coordinates. Large enough to absorb OCR jitter on one printed
# line, small enough to keep distinct printed lines apart.
_ROW_TOLERANCE: Final = 0.01
_DATE_FORMATS: Final = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%d/%m/%y",
    "%d-%m-%y",
)


class ExtractionError(RuntimeError):
    """The LLM stage could not produce a validated payload."""


class ExtractionTimeout(ExtractionError):
    """The LLM call itself timed out (genuine SDK timeout, not a slow result).

    Raised only when the exception chain contains an SDK-level timeout
    (``openai.APITimeoutError`` or ``httpx.TimeoutException``). Every other
    failure -- validation, connection, auth, config -- stays a plain
    :class:`ExtractionError` so a slow-but-successful call is never discarded
    and a config error is never retried as a timeout.
    """


# --------------------------------------------------------------------------- #
# Token pruning (§5.3.2)
# --------------------------------------------------------------------------- #


def _find_best_slope(tokens: list[OCRToken]) -> float:
    """Estimate document slant slope (dy/dx) from token positions.

    Tests candidate slopes in [-0.20, +0.20] (approx ±11 degrees) and selects
    the slope minimizing within-line vertical variance. Upright documents return 0.0.
    """
    if len(tokens) < 3:
        return 0.0

    best_slope = 0.0
    best_cost = float("inf")
    for i in range(-20, 21):
        s = i * 0.01
        projs = []
        for t in tokens:
            x_c = (t.bbox[0] + t.bbox[2]) / 2.0
            y_c = (t.bbox[1] + t.bbox[3]) / 2.0
            projs.append(y_c - s * x_c)
        projs.sort()
        diffs = [projs[j + 1] - projs[j] for j in range(len(projs) - 1)]
        within = [d for d in diffs if d < 0.025]
        if not within:
            continue
        cost = (sum(d * d for d in within) / (len(within) ** 2)) + 1e-6 * (s * s)
        if cost < best_cost:
            best_cost = cost
            best_slope = s

    return best_slope


def group_tokens_into_rows(
    tokens: Iterable[OCRToken], slope: float | None = None
) -> list[list[OCRToken]]:
    """Group tokens into visual reading-order rows taking slant into account.

    Within each row, tokens are ordered strictly left-to-right (x_min).
    Rows are ordered top-to-bottom.
    """
    token_list = list(tokens)
    if not token_list:
        return []

    if slope is None:
        slope = _find_best_slope(token_list)

    def get_y_proj(t: OCRToken) -> float:
        x_c = (t.bbox[0] + t.bbox[2]) / 2.0
        y_c = (t.bbox[1] + t.bbox[3]) / 2.0
        return y_c - slope * x_c

    sorted_tokens = sorted(token_list, key=lambda t: (get_y_proj(t), t.bbox[0]))
    rows: list[list[OCRToken]] = []

    for token in sorted_tokens:
        y_p = get_y_proj(token)
        if rows and abs(y_p - get_y_proj(rows[-1][0])) <= 0.022:
            rows[-1].append(token)
        else:
            rows.append([token])

    for row in rows:
        row.sort(key=lambda t: t.bbox[0])

    rows.sort(key=lambda r: min(t.bbox[1] for t in r))
    return rows


def sort_tokens(tokens: Iterable[OCRToken]) -> list[OCRToken]:
    """Reading order: top-to-bottom, then left-to-right (§5.3.2)."""
    rows = group_tokens_into_rows(tokens)
    return [token for row in rows for token in row]


def render_tokens(tokens: Iterable[OCRToken]) -> str:
    """Format tokens as a compact line-per-row text block for the LLM.

    Tokens are grouped into visual rows by their slant-corrected geometry and
    emitted top-to-bottom with the row's normalized ``y`` as a spatial hint;
    within a row, tokens are joined left-to-right by ``x_min``.
    """
    rows = group_tokens_into_rows(tokens)
    return "\n".join(
        f"[{min(t.bbox[1] for t in row):.3f}] " + " ".join(t.text for t in row)
        for row in rows
    )


# --------------------------------------------------------------------------- #
# LLM call
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=1)
def get_llm_client() -> instructor.Instructor:
    """Build the process-wide instructor-wrapped OpenAI client."""
    api_key = os.getenv(API_KEY_ENV, "").strip()
    if not api_key:
        raise ExtractionError(f"{API_KEY_ENV} is not set; cannot run LLM extraction")

    raw_base_url = (os.getenv(BASE_URL_ENV) or "").strip()
    base_url = None
    if raw_base_url:
        base_url = raw_base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

    client = openai.OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=LLM_TIMEOUT_SECONDS,
        # The SDK's own retry loop is bounded here so it cannot stack on top of
        # instructor's validation retries and blow the §5.3.2 time budget.
        max_retries=0,
    )
    # MD_JSON, not TOOLS: OpenAI-compatible relays frequently reject the object
    # form of ``tool_choice`` that instructor sends for TOOLS mode
    # ("cannot unmarshal object into Go struct field ... of type string"), which
    # would make extraction fail against a perfectly good provider. The schema is
    # carried in the user turn instead -- see ``_SCHEMA_HINT``.
    return instructor.from_openai(client, mode=instructor.Mode.MD_JSON)


def _is_timeout_error(exc: BaseException) -> bool:
    """True when the exception chain is a genuine SDK-level timeout.

    Walks ``__cause__``/``__context__`` so a timeout wrapped by instructor's
    retry machinery is still recognised, while an unrelated error that merely
    mentions "timeout" in its message is not.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(
            current, (openai.APITimeoutError, httpx.TimeoutException, TimeoutError)
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


# A price that leaked into the item name: "PAKU 2 INCI 4.50", "CAT JOTUN 38.00".
# Only a *trailing* amount that equals the line's own total or unit price is
# removed -- a bare number at the end of a name can be part of the product
# ("PAKU 2 INCI", "SHELL TELLUS 4L"), so the value has to corroborate the match.
_TRAILING_AMOUNT_RE: Final = re.compile(
    r"[\s@x×*()\-]*(?:RM|MYR)?[\s]*(\d[\d,]*(?:\.\d{1,2})?)[\s.)]*$",
    re.IGNORECASE,
)


def _strip_price_from_description(
    description: str, line_total: Decimal | None, unit_price: Decimal | None
) -> str:
    """Drop a trailing printed price the model folded into the item name.

    The prompt already forbids it, but a description and a price sit on one OCR
    line and models conflate them often enough to matter (REQ-109). This only
    removes digits that reproduce the line's own money, which keeps genuine
    alphanumerics such as "PAKU 2 INCI" or "CAT 5L" intact.
    """
    text = description.strip()
    if not text:
        return text
    match = _TRAILING_AMOUNT_RE.search(text)
    if match is None:
        return text
    try:
        value = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return text
    if value not in {line_total, unit_price}:
        return text
    # Trim separators only, then rebalance: the separator run can swallow the
    # closing paren of a name such as "CAT JOTUN (KECIL) 38.00".
    trimmed = text[: match.start()].rstrip(" \t-@x×*")
    if trimmed.count("(") > trimmed.count(")"):
        trimmed = f"{trimmed})"
    # Never let the strip empty the field: a description made only of the price
    # is still a line item, and blanking it would hide the row from the auditor.
    return trimmed or text


def _clean_line_item_descriptions(data: ExtractedReceiptData) -> None:
    """Apply the trailing-price strip to every extracted line, in place."""
    for item in data.line_items:
        item.description = _strip_price_from_description(
            item.description, item.line_total, item.unit_price
        )


def extract_receipt_data(
    tokens: list[OCRToken],
    *,
    client: instructor.Instructor | None = None,
    model: str | None = None,
) -> ExtractedReceiptData:
    """Run one structured-extraction completion over the token block (§5.3)."""
    if not tokens:
        raise ExtractionError("no OCR tokens to extract from")

    llm = client or get_llm_client()
    try:
        parsed = llm.chat.completions.create(
            model=model or os.getenv(MODEL_ENV) or DEFAULT_MODEL,
            response_model=ExtractedReceiptData,
            max_retries=2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": render_tokens(tokens) + _SCHEMA_HINT},
            ],
        )
        _clean_line_item_descriptions(parsed)
        return parsed
    except Exception as exc:  # instructor retries already exhausted
        if _is_timeout_error(exc):
            raise ExtractionTimeout(f"LLM extraction timed out: {exc}") from exc
        raise ExtractionError(f"LLM extraction failed: {exc}") from exc


# --------------------------------------------------------------------------- #
# Provenance: measure per-field confidence from the OCR tokens
# --------------------------------------------------------------------------- #


def _normalize(text: str) -> str:
    """Lowercase, drop currency markers and all whitespace."""
    lowered = _CURRENCY_RE.sub("", text.lower())
    return "".join(lowered.split())


def _decimal_or_none(text: str) -> Decimal | None:
    match = _NUMBER_RE.search(text)
    if match is None:
        return None
    try:
        return Decimal(match.group().replace(",", ""))
    except InvalidOperation:  # pragma: no cover - regex guarantees a parseable number
        return None


def _token_numbers(token: OCRToken) -> list[Decimal]:
    """The numeric values a token states, after undoing common OCR spacing damage."""
    text = _SPACED_DECIMAL_RE.sub(".", token.text)
    if _DECIMAL_COMMA_RE.match(text.strip()):
        # "24,00" is 24.00 in this dialect, not twenty-four thousand.
        text = text.strip().replace(",", ".")
    numbers = (_decimal_or_none(match.group()) for match in _NUMBER_RE.finditer(text))
    return [number for number in numbers if number is not None]


def _pick(candidates: list[OCRToken]) -> OCRToken | None:
    """The token that best supports a value: most trusted of the matches."""
    return max(candidates, key=lambda token: token.confidence, default=None)


def _match_numeric(target: Decimal, tokens: list[OCRToken]) -> OCRToken | None:
    """A token carrying ``target`` as one of its numbers.

    A number only counts as evidence when it is the token's whole value (or one
    of its whitespace-separated parts): the same digits appearing inside a date,
    a BRN, or an unrelated amount must not certify a total.
    """
    return _pick([token for token in tokens if target in _token_numbers(token)])


def _word_in_token(word: str, token: OCRToken) -> bool:
    haystack = _normalize(token.text)
    if not haystack:
        return False
    if word in haystack:
        return True
    if len(haystack) >= 3 and SequenceMatcher(None, word, haystack).ratio() >= 0.70:
        return True
    w_len = len(word)
    if len(haystack) > w_len:
        for i in range(len(haystack) - w_len + 1):
            if SequenceMatcher(None, word, haystack[i : i + w_len]).ratio() >= 0.70:
                return True
    return False


def _match_text(target: str, tokens: list[OCRToken]) -> OCRToken | None:
    needle = _normalize(target)
    if len(needle) < 3:  # too short to be evidence; refuse to guess
        return None
    hits = []
    for token in tokens:
        haystack = _normalize(token.text)
        if haystack and needle in haystack:
            hits.append(token)
    if hits:
        return _pick(hits)
    # Multi-token values (e.g. "KIM GUAN HARDWARE SDN BHD") are only supported
    # when the OCR actually carries the whole value: every distinctive word must
    # appear in some token. A lone substring ("KIM GUAN" for the full name) is
    # not evidence for the words the receipt never showed.
    words = [word for word in re.split(r"\W+", target.lower()) if len(word) >= 4]
    if not words:
        return None
    all_covered = all(any(_word_in_token(word, t) for t in tokens) for word in words)
    if not all_covered:
        return None
    partial = [
        token
        for token in tokens
        if any(_word_in_token(word, token) for word in words)
    ]
    return _pick(partial)


def _match_date(value, tokens: list[OCRToken]) -> OCRToken | None:
    renderings = {value.strftime(fmt) for fmt in _DATE_FORMATS}
    renderings.add(value.isoformat())
    for token in sorted(tokens, key=lambda t: t.confidence, reverse=True):
        if any(rendering in token.text for rendering in renderings):
            return token
    return None


def _provenance(name: str, value, tokens: list[OCRToken]) -> ExtractedField:
    if isinstance(value, date):
        token = _match_date(value, tokens)
    elif isinstance(value, Decimal):
        token = _match_numeric(value, tokens)
    else:
        token = _match_text(str(value), tokens)

    if token is None:
        return ExtractedField(name=name, confidence=UNSUPPORTED_CONFIDENCE, bbox=None)
    return ExtractedField(name=name, confidence=token.confidence, bbox=list(token.bbox))


HEADER_FIELDS: Final = (
    "merchant_name",
    "merchant_brn",
    "merchant_sst",
    "invoice_date",
    "invoice_number",
    "subtotal",
    "tax_amount",
    "grand_total",
)


def attach_provenance(
    data: ExtractedReceiptData, tokens: list[OCRToken]
) -> ParsedReceiptSchema:
    """Pair an extraction result with per-field OCR provenance (§5.4 input)."""
    fields = []
    for name in HEADER_FIELDS:
        value = getattr(data, name)
        if value in _ABSENT:
            continue  # absent fields are the mandatory-field check's business
        fields.append(_provenance(name, value, tokens))

    line_items = [
        item.model_copy(
            update={
                "confidence": _line_item_confidence(item, tokens),
                "bbox": item.bbox or _line_item_bbox(item, tokens),
            }
        )
        for item in data.line_items
    ]
    return ParsedReceiptSchema(
        **data.model_dump(exclude={"line_items"}), line_items=line_items, fields=fields
    )


def _line_item_confidence(item, tokens: list[OCRToken]) -> float:
    """A line is only as trustworthy as the weakest token backing it.

    Both the description and the amount must be present in the OCR: a line with
    a readable total but no readable description (or vice versa) is not evidence
    of a real line, so it is conservatively scored 0.0 rather than trusting the
    half that happened to survive.
    """
    if item.confidence < 1.0:
        return item.confidence  # model already reported its own doubt
    description = _match_text(item.description, tokens)
    amount = _match_numeric(item.line_total, tokens)
    if description is None or amount is None:
        return UNSUPPORTED_CONFIDENCE
    return min(description.confidence, amount.confidence)

def _line_item_bbox(item, tokens: list[OCRToken]) -> list[float] | None:
    description = _match_text(item.description, tokens)
    amount = _match_numeric(item.line_total, tokens)
    matched = [t for t in (description, amount) if t is not None]
    if not matched:
        return None
    x_min = min(t.bbox[0] for t in matched)
    y_min = min(t.bbox[1] for t in matched)
    x_max = max(t.bbox[2] for t in matched)
    y_max = max(t.bbox[3] for t in matched)
    return [round(x_min, 4), round(y_min, 4), round(x_max, 4), round(y_max, 4)]


def extract_receipt(
    tokens: list[OCRToken],
    *,
    client: instructor.Instructor | None = None,
    model: str | None = None,
) -> ParsedReceiptSchema:
    """Full §5.3 stage: tokens -> validated extraction -> provenance-tagged parse."""
    data = extract_receipt_data(tokens, client=client, model=model)
    return attach_provenance(data, tokens)


__all__ = [
    "SYSTEM_PROMPT",
    "ExtractionError",
    "ExtractionTimeout",
    "attach_provenance",
    "extract_receipt",
    "extract_receipt_data",
    "get_llm_client",
    "render_tokens",
    "sort_tokens",
]
