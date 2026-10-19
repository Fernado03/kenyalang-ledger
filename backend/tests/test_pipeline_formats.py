"""Format-decoding tests for the OCR preprocessor (docs/05_trd.md §5.2.1).

Covers the decompression-bomb guard, multi-page PDF handling (page 1 only),
encrypted PDFs, HEIC decoding and EXIF orientation. Fixtures are synthesised in
memory so the cases run without the receipt dataset.
"""

from __future__ import annotations

import io

import numpy as np
import piexif
import pytest
from PIL import Image

from app.pipeline.preprocessor import (
    ImageDecodeError,
    _check_pixels,
    auto_orient_image,
    decode_heic,
    decode_image,
    decode_pdf,
    preprocess_image,
    preprocess_receipt,
)


# --------------------------------------------------------------------------- #
# Pixel-budget guard
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("width", "height"), [(0, 10), (10, 0), (-1, 10), (10, -1)])
def test_check_pixels_rejects_empty_dimensions(width: int, height: int) -> None:
    with pytest.raises(ImageDecodeError):
        _check_pixels(width, height)


def test_check_pixels_rejects_above_40_megapixels() -> None:
    with pytest.raises(ImageDecodeError) as excinfo:
        _check_pixels(8000, 6000)  # 48 MP

    message = str(excinfo.value)
    assert "40" in message
    assert "MP" in message


def test_check_pixels_accepts_exactly_40_megapixels() -> None:
    _check_pixels(8000, 5000)  # 40 MP: the limit is inclusive


# --------------------------------------------------------------------------- #
# PDF: page 1 only
# --------------------------------------------------------------------------- #


def _build_pdf() -> bytes:
    import fitz

    document = fitz.open()
    first = document.new_page(width=400, height=600)  # portrait: aspect 2/3
    first.insert_text((50, 60), "PAGE ONE ALPHA")
    second = document.new_page(width=600, height=300)  # landscape: aspect 2/1
    second.insert_text((50, 60), "PAGE TWO BETA")
    payload = document.tobytes()
    document.close()
    return payload


def test_decode_pdf_uses_page_one_aspect_ratio() -> None:
    decoded = decode_pdf(_build_pdf())

    assert decoded.dtype == np.uint8
    assert decoded.ndim == 3 and decoded.shape[2] == 3

    height, width = decoded.shape[:2]
    page_one_aspect = 400 / 600
    page_two_aspect = 600 / 300
    assert width / height == pytest.approx(page_one_aspect, rel=0.01)
    assert abs(width / height - page_one_aspect) < abs(width / height - page_two_aspect)


def test_preprocess_receipt_pdf_returns_bgr_uint8() -> None:
    processed = preprocess_receipt(_build_pdf(), "application/pdf")

    assert processed.dtype == np.uint8
    assert processed.ndim == 3
    assert processed.shape[2] == 3


def test_decode_pdf_rejects_encrypted_document() -> None:
    import fitz

    document = fitz.open()
    page = document.new_page(width=400, height=600)
    page.insert_text((50, 60), "TOP SECRET")
    payload = document.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner-secret",
        user_pw="user-secret",
    )
    document.close()

    with pytest.raises(ImageDecodeError):
        decode_pdf(payload)


# --------------------------------------------------------------------------- #
# HEIC
# --------------------------------------------------------------------------- #


def test_decode_heic_returns_expected_shape() -> None:
    pillow_heif = pytest.importorskip("pillow_heif")
    pillow_heif.register_heif_opener()

    width, height = 64, 48
    image = Image.new("RGB", (width, height), color=(120, 30, 200))
    buffer = io.BytesIO()
    try:
        image.save(buffer, format="HEIF")
    except Exception as exc:  # encoder plugin missing from the wheel
        pytest.skip(f"pillow-heif encoder unavailable: {exc}")

    decoded = decode_heic(buffer.getvalue())

    assert decoded.shape == (height, width, 3)


# --------------------------------------------------------------------------- #
# EXIF orientation
# --------------------------------------------------------------------------- #


def test_auto_orient_swaps_axes_for_orientation_6() -> None:
    # PIL takes (width, height); OpenCV decodes to (height, width).
    image = Image.new("RGB", (100, 50), color=(200, 200, 200))
    exif_bytes = piexif.dump({"0th": {piexif.ImageIFD.Orientation: 6}})
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif_bytes, quality=95)
    payload = buffer.getvalue()

    # Stored grid: width 100, height 50 -> decoded (50, 100).
    assert decode_image(payload).shape[:2] == (50, 100)

    oriented = auto_orient_image(payload)

    # Orientation 6 rotates 90 degrees clockwise, swapping the axes back.
    assert oriented.shape[:2] == (100, 50)
    assert oriented.shape[2] == 3


def test_preprocess_image_accepts_png_without_exif() -> None:
    """PNG carries no EXIF header; reading one must not fail the whole decode.

    Regression: the EXIF reader caught ``piexif.exceptions.InvalidImageDataError``,
    a submodule that does not exist in piexif 1.1.3, so evaluating the except
    clause raised AttributeError and every PNG upload ended as
    ``processing failed unexpectedly``.
    """
    image = Image.new("RGB", (64, 48), color=(250, 250, 250))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    decoded = preprocess_image(buffer.getvalue())

    assert decoded.shape[0] > 0
    assert decoded.shape[1] > 0


def test_preprocess_image_accepts_jpeg_without_exif() -> None:
    image = Image.new("RGB", (64, 48), color=(250, 250, 250))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)

    assert preprocess_image(buffer.getvalue()).shape[2] == 3
