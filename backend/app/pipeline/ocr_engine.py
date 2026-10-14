"""EasyOCR spatial token extraction (docs/05_trd.md §5.2.2, REQ-102).

EasyOCR returns four-point pixel polygons per detected text segment. This module
flattens each polygon to an axis-aligned box and divides by the image dimensions,
producing the normalized ``[x_min, y_min, x_max, y_max]`` coordinates (0.0-1.0) the
review console needs to highlight source regions in the browser.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Final

import easyocr
import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field, field_validator

from app.pipeline.preprocessor import preprocess_image

logger = logging.getLogger(__name__)

OCR_LANGUAGES: Final = ["en", "ms"]
# Below this, EasyOCR reports noise and half-characters that mislead the LLM stage.
MIN_CONFIDENCE: Final = 0.30
# Reader construction loads ~100MB of detection/recognition weights, so it is
# cached process-wide: the ingest worker is long-lived and reuses one reader.
_READER_GPU_FLAG_ENV: Final = "EASYOCR_USE_GPU"


class OCRToken(BaseModel):
    """A recognized text run with its position in the source image."""

    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    # [x_min, y_min, x_max, y_max], each normalized to 0.0-1.0.
    bbox: list[float] = Field(min_length=4, max_length=4)
    line_num: int = Field(ge=0)

    @field_validator("bbox")
    @classmethod
    def _validate_bbox(cls, bbox: list[float]) -> list[float]:
        if not all(0.0 <= coordinate <= 1.0 for coordinate in bbox):
            raise ValueError(f"bbox must be normalized to 0.0-1.0, got {bbox}")
        x_min, y_min, x_max, y_max = bbox
        if x_max < x_min or y_max < y_min:
            raise ValueError(f"bbox corners are inverted: {bbox}")
        return bbox


@lru_cache(maxsize=1)
def get_reader(gpu: bool | None = None) -> "easyocr.Reader":
    """Return the process-wide EasyOCR reader for English + Malay."""
    if gpu is None:
        gpu = os.getenv(_READER_GPU_FLAG_ENV, "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
    reader = easyocr.Reader(OCR_LANGUAGES, gpu=gpu, verbose=False)
    logger.info("EasyOCR reader ready (languages=%s, gpu=%s)", OCR_LANGUAGES, gpu)
    return reader


def normalize_bbox(box: NDArray[np.float32], width: int, height: int) -> list[float]:
    """Flatten an EasyOCR 4-point pixel polygon to a normalized axis-aligned box.

    Implements the min/max normalization of §5.2.2. Coordinates are clamped to
    0.0-1.0 because EasyOCR can emit vertices a pixel outside the image edge,
    which would otherwise produce an out-of-range box.
    """
    points = np.asarray(box, dtype=np.float64).reshape(-1, 2)
    x_min, y_min = points.min(axis=0)
    x_max, y_max = points.max(axis=0)

    normalized = [
        float(np.clip(x_min / width, 0.0, 1.0)),
        float(np.clip(y_min / height, 0.0, 1.0)),
        float(np.clip(x_max / width, 0.0, 1.0)),
        float(np.clip(y_max / height, 0.0, 1.0)),
    ]
    return normalized


def extract_tokens(
    cv_image: NDArray[np.uint8], reader: "easyocr.Reader" | None = None
) -> list[OCRToken]:
    """Run EasyOCR over a BGR image and return normalized OCRTokens.

    Tokens arrive in reading order, so the enumerate index doubles as ``line_num``
    for the downstream LLM stage (REQ-103).
    """
    if reader is None:
        reader = get_reader()

    height, width = cv_image.shape[:2]
    if width == 0 or height == 0:
        raise ValueError("Cannot OCR an image with a zero dimension")

    results = reader.readtext(cv_image, detail=1, paragraph=False)
    tokens: list[OCRToken] = []

    for line_num, (box, text, raw_confidence) in enumerate(results):
        confidence = float(raw_confidence)
        if confidence < MIN_CONFIDENCE:
            continue
        cleaned = str(text).strip()
        if not cleaned:
            continue

        tokens.append(
            OCRToken(
                text=cleaned,
                confidence=round(confidence, 4),
                bbox=normalize_bbox(box, width, height),
                line_num=line_num,
            )
        )
    return tokens


def process_receipt_image(file_bytes: bytes) -> list[OCRToken]:
    """Full ingest entrypoint: bytes -> normalized image -> spatial OCR tokens.

    This is the internal runner wired to ``receipts.ocr_raw_tokens`` (JSONB).
    """
    processed = preprocess_image(file_bytes)
    return extract_tokens(processed)


def tokens_to_dicts(tokens: list[OCRToken]) -> list[dict[str, Any]]:
    """Serialize tokens for JSONB persistence in ``receipts.ocr_raw_tokens``."""
    return [token.model_dump() for token in tokens]


__all__ = [
    "OCRToken",
    "extract_tokens",
    "get_reader",
    "normalize_bbox",
    "process_receipt_image",
    "tokens_to_dicts",
]
