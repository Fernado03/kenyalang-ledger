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

import logging
import os
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Final, Iterable, Optional

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
   - Do not hallucinate items. If line items are unreadable due to fading, extract grand_total and set line_items to empty array.

Return ONLY a validated JSON payload adhering to the requested schema.
"""

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
_ABSENT: Final = (None, "", 0, Decimal("0"), Decimal("0.00"))

_NUMBER_RE: Final = re.compile(r"\d[\d,]*(?:\.\d+)?")
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


def sort_tokens(tokens: Iterable[OCRToken]) -> list[OCRToken]:
    """Reading order: top-to-bottom, then left-to-right (§5.3.2)."""
    return sorted(tokens, key=lambda token: (token.bbox[1], token.bbox[0]))


def render_tokens(tokens: Iterable[OCRToken]) -> str:
    """Format tokens as a compact line-per-row text block for the LLM.

    Tokens are grouped into visual rows by their ``y_min`` and emitted
    top-to-bottom with the row's normalized ``y`` as a spatial hint; within a
    row, tokens are joined left-to-right by ``x_min``. Sending rows instead of
    one token per line is what keeps the prompt small enough to stay inside the
    §5.3.2 token budget.

    Grouping is geometric, not ``line_num``-based: a scrambled or interleaved
    ``line_num`` must never split tokens that share a visual row, so the row a
    token lands in is decided by where it actually is.
    """
    ordered = sort_tokens(tokens)
    rows: list[list[OCRToken]] = []
    for token in ordered:
        if rows and abs(token.bbox[1] - rows[-1][0].bbox[1]) <= _ROW_TOLERANCE:
            rows[-1].append(token)
        else:
            rows.append([token])

    return "\n".join(
        f"[{row[0].bbox[1]:.3f}] " + " ".join(t.text for t in row) for row in rows
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

    client = openai.OpenAI(
        api_key=api_key,
        base_url=os.getenv(BASE_URL_ENV) or None,
        timeout=LLM_TIMEOUT_SECONDS,
        # The SDK's own retry loop is bounded here so it cannot stack on top of
        # instructor's validation retries and blow the §5.3.2 time budget.
        max_retries=0,
    )
    # TOOLS (function calling) rather than JSON mode: it is the only mode that
    # accepts the full Pydantic surface we need (Decimal, date, Optional).
    return instructor.from_openai(client, mode=instructor.Mode.TOOLS)


def _is_timeout_error(exc: BaseException) -> bool:
    """True when the exception chain is a genuine SDK-level timeout.

    Walks ``__cause__``/``__context__`` so a timeout wrapped by instructor's
    retry machinery is still recognised, while an unrelated error that merely
    mentions "timeout" in its message is not.
    """
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(
            current, (openai.APITimeoutError, httpx.TimeoutException, TimeoutError)
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


def extract_receipt_data(
    tokens: list[OCRToken],
    *,
    client: Optional[instructor.Instructor] = None,
    model: Optional[str] = None,
) -> ExtractedReceiptData:
    """Run one structured-extraction completion over the token block (§5.3)."""
    if not tokens:
        raise ExtractionError("no OCR tokens to extract from")

    llm = client or get_llm_client()
    try:
        return llm.chat.completions.create(
            model=model or os.getenv(MODEL_ENV) or DEFAULT_MODEL,
            response_model=ExtractedReceiptData,
            max_retries=2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": render_tokens(tokens)},
            ],
        )
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


def _decimal_or_none(text: str) -> Optional[Decimal]:
    match = _NUMBER_RE.search(text)
    if match is None:
        return None
    try:
        return Decimal(match.group().replace(",", ""))
    except InvalidOperation:  # pragma: no cover - regex guarantees a parseable number
        return None


def _token_numbers(token: OCRToken) -> list[Decimal]:
    numbers = (
        _decimal_or_none(match.group()) for match in _NUMBER_RE.finditer(token.text)
    )
    return [number for number in numbers if number is not None]


def _pick(candidates: list[OCRToken]) -> Optional[OCRToken]:
    """The token that best supports a value: most trusted of the matches."""
    return max(candidates, key=lambda token: token.confidence, default=None)


def _match_numeric(target: Decimal, tokens: list[OCRToken]) -> Optional[OCRToken]:
    """A token carrying ``target`` as one of its numbers.

    A number only counts as evidence when it is the token's whole value (or one
    of its whitespace-separated parts): the same digits appearing inside a date,
    a BRN, or an unrelated amount must not certify a total.
    """
    return _pick([token for token in tokens if target in _token_numbers(token)])


def _match_text(target: str, tokens: list[OCRToken]) -> Optional[OCRToken]:
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
    covered = [
        any(word in _normalize(token.text) for token in tokens) for word in words
    ]
    if not all(covered):
        return None
    partial = [
        token
        for token in tokens
        if any(word in _normalize(token.text) for word in words)
    ]
    return _pick(partial)


def _match_date(value, tokens: list[OCRToken]) -> Optional[OCRToken]:
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
        item.model_copy(update={"confidence": _line_item_confidence(item, tokens)})
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


def extract_receipt(
    tokens: list[OCRToken],
    *,
    client: Optional[instructor.Instructor] = None,
    model: Optional[str] = None,
) -> ParsedReceiptSchema:
    """Full §5.3 stage: tokens -> validated extraction -> provenance-tagged parse."""
    data = extract_receipt_data(tokens, client=client, model=model)
    return attach_provenance(data, tokens)


__all__ = [
    "ExtractionError",
    "ExtractionTimeout",
    "SYSTEM_PROMPT",
    "attach_provenance",
    "extract_receipt",
    "extract_receipt_data",
    "get_llm_client",
    "render_tokens",
    "sort_tokens",
]
