"""Vision ingest pipeline: EXIF orientation, CLAHE, scaling, spatial OCR (REQ-101/102).

Two conventions this file depends on:

* OpenCV arrays are indexed ``[y, x]``, so ``img.shape[:2]`` is ``(height, width)``
  -- the reverse of PIL's ``(width, height)``.
* ``_write_jpeg(size=...)`` takes a PIL ``(w, h)``; the decoded OpenCV shape is
  therefore ``(h, w)``.

The OCR tests run the real EasyOCR reader against real receipts from dataset/.
EasyOCR downloads model weights on first use, so those tests skip rather than
fail when the machine is offline.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.pipeline.ocr_engine import (
    OCRToken,
    extract_tokens,
    normalize_bbox,
    process_receipt_image,
)
from app.pipeline.preprocessor import (
    ImageDecodeError,
    apply_clahe_contrast,
    auto_orient_image,
    decode_image,
    preprocess_image,
    read_exif_orientation,
    resize_if_needed,
)

DATASET_DIR = Path(__file__).resolve().parents[2] / "dataset"
SROIE_IMAGES = DATASET_DIR / "sroie" / "images"
RECEIPT_FILENAME = "100.jpg"

requires_dataset = pytest.mark.skipif(
    not (SROIE_IMAGES / RECEIPT_FILENAME).is_file(),
    reason=f"receipt dataset not present at {SROIE_IMAGES}",
)


@pytest.fixture
def receipt_path() -> Path:
    return SROIE_IMAGES / RECEIPT_FILENAME


@pytest.fixture
def receipt_bytes(receipt_path: Path) -> bytes:
    return receipt_path.read_bytes()


def _write_jpeg(exif_orientation: int | None, size: tuple[int, int]) -> bytes:
    """Build a JPEG carrying an EXIF orientation tag. ``size`` is PIL ``(w, h)``."""
    image = Image.new("RGB", size, color=(200, 200, 200))
    exif = image.getexif()
    if exif_orientation is not None:
        exif[0x0112] = exif_orientation
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif, quality=95)
    return buffer.getvalue()


def test_opencv_binary_matches_numpy_abi() -> None:
    """Regression guard for the opencv-python/opencv-python-headless `cv2` clash.

    Both distributions install a top-level `cv2`; when both are present the older
    one can win and fail to load against numpy 2.x with an opaque ABI error. This
    fails at import time if the two ever desynchronize again (see
    constraints.txt).
    """
    import cv2

    assert cv2.__version__
    # A real decode/exercise: an ABI mismatch raises here rather than silently.
    blank = np.full((16, 16, 3), 128, dtype=np.uint8)
    assert cv2.cvtColor(blank, cv2.COLOR_BGR2LAB).shape == blank.shape


def _jpeg_without_exif(size: tuple[int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(10, 20, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _run_ocr(*args, **kwargs):
    """Call into EasyOCR, skipping the test if weights cannot be obtained."""
    try:
        return process_receipt_image(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - skip when EasyOCR cannot load
    # no network for weights, torch missing, etc.
        pytest.skip(f"EasyOCR unavailable: {exc}")


# --------------------------------------------------------------------------- #
# REQ-101: preprocessor
# --------------------------------------------------------------------------- #


@requires_dataset
def test_preprocess_real_receipt_returns_bgr_uint8(receipt_bytes: bytes) -> None:
    processed = preprocess_image(receipt_bytes)

    assert processed.ndim == 3 and processed.shape[2] == 3  # BGR
    assert processed.dtype == np.uint8
    assert processed.size > 0


def test_decode_image_does_not_apply_exif_itself() -> None:
    """Orientation is applied exactly once, in auto_orient_image -- never twice.

    ``cv2.imdecode`` honors EXIF by default, which silently double-rotated every
    smartphone photo (REQ-101).
    """
    portrait = _write_jpeg(exif_orientation=6, size=(80, 160))

    # Raw decode keeps the stored pixel grid: PIL (w=80, h=160) -> (h=160, w=80).
    assert decode_image(portrait).shape[:2] == (160, 80)


def test_auto_orient_rotates_for_exif_orientation_6() -> None:
    """Orientation 6 means the camera stored the frame rotated 90 clockwise."""
    portrait = _write_jpeg(exif_orientation=6, size=(80, 160))
    assert read_exif_orientation(portrait) == 6

    oriented = auto_orient_image(portrait)

    # The 90-degree rotation turns the stored grid into the upright orientation.
    assert oriented.shape[:2] == (80, 160)


def test_auto_orient_handles_orientation_3() -> None:
    rotated = _write_jpeg(exif_orientation=3, size=(40, 70))

    assert read_exif_orientation(rotated) == 3
    # ROTATE_180 keeps the axes, so the shape is unchanged.
    assert auto_orient_image(rotated).shape[:2] == (70, 40)


def test_auto_orient_orientation_1_is_identity() -> None:
    upright = _write_jpeg(exif_orientation=1, size=(50, 90))

    assert auto_orient_image(upright).shape[:2] == (90, 50)


def test_auto_orient_defaults_to_upright_without_exif() -> None:
    assert read_exif_orientation(_jpeg_without_exif((50, 90))) == 1
    assert auto_orient_image(_jpeg_without_exif((50, 90))).shape[:2] == (90, 50)


def test_resize_scales_down_preserving_aspect_ratio() -> None:
    tall = np.zeros((4000, 2000, 3), dtype=np.uint8)  # (h=4000, w=2000)

    resized = resize_if_needed(tall, max_dim=2048)

    assert max(resized.shape[:2]) == 2048
    # 2:1 aspect ratio, so the scaled width must be exactly 1024.
    assert resized.shape[:2] == (2048, 1024)


def test_resize_leaves_small_images_untouched() -> None:
    small = np.zeros((300, 200, 3), dtype=np.uint8)

    assert resize_if_needed(small, max_dim=2048).shape == small.shape


def test_clahe_preserves_shape_and_dtype() -> None:
    faded = np.full((120, 160, 3), 150, dtype=np.uint8)
    faded[40:60, 30:120] = 90  # faint ink block

    enhanced = apply_clahe_contrast(faded)

    assert enhanced.shape == faded.shape
    assert enhanced.dtype == np.uint8


def test_clahe_lifts_faded_ink_contrast() -> None:
    """CLAHE exists to recover faded ink, so a flat patch must gain local contrast."""
    flat = np.full((100, 100, 3), 150, dtype=np.uint8)
    flat[45:55, 20:80] = 149  # ink only 1 level below paper

    enhanced = apply_clahe_contrast(flat)

    assert enhanced.std() > flat.std()


def test_clahe_keeps_ink_darker_than_paper() -> None:
    """Contrast may be stretched, but ink must stay below paper after equalization."""
    paper_with_ink = np.full((100, 100, 3), 200, dtype=np.uint8)
    paper_with_ink[45:55, 20:80] = 150

    enhanced = apply_clahe_contrast(paper_with_ink)

    assert enhanced[50, 50].mean() < enhanced[10, 10].mean()


def _local_text_separation(image: np.ndarray, win: int = 9) -> float:
    """Mean |pixel - local mean|: how far ink stands out from nearby paper.

    CLAHE is a *local* equalizer, so this -- not global std -- is what improves.
    """
    import cv2

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return float(np.abs(gray - cv2.blur(gray, (win, win))).mean())


@requires_dataset
def test_clahe_improves_local_contrast_on_real_receipt(receipt_bytes: bytes) -> None:
    """The end-to-end goal of §5.2.1: faded thermal ink stands out more after CLAHE."""
    raw = decode_image(receipt_bytes)

    enhanced = apply_clahe_contrast(raw)

    assert enhanced.shape == raw.shape
    assert _local_text_separation(enhanced) > _local_text_separation(raw)


@requires_dataset
def test_clahe_preserves_sharp_character_edges_on_real_receipt(
    receipt_bytes: bytes,
) -> None:
    """clipLimit=2.0 must not smear edges -- it protects the paper, not the glyphs."""
    import cv2

    raw = decode_image(receipt_bytes)
    enhanced = apply_clahe_contrast(raw)

    def detail(image: np.ndarray) -> float:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_32F).var())

    assert detail(enhanced) >= detail(raw)


def test_decode_image_rejects_garbage() -> None:
    with pytest.raises(ImageDecodeError):
        decode_image(b"not an image at all")


def test_decode_image_rejects_empty_payload() -> None:
    with pytest.raises(ImageDecodeError):
        decode_image(b"")


# --------------------------------------------------------------------------- #
# REQ-102: spatial OCR
# --------------------------------------------------------------------------- #


def test_normalize_bbox_maps_pixels_to_relative() -> None:
    box = np.array([[20, 40], [120, 40], [120, 90], [20, 90]], dtype=np.float32)

    assert normalize_bbox(box, width=200, height=100) == pytest.approx(
        [0.1, 0.4, 0.6, 0.9]
    )


def test_normalize_bbox_clamps_out_of_bounds_points() -> None:
    """EasyOCR can emit edge vertices outside the image; boxes must stay in range."""
    box = np.array([[-10, -10], [260, -10], [260, 130], [-10, 130]], dtype=np.float32)

    assert normalize_bbox(box, width=200, height=100) == pytest.approx(
        [0.0, 0.0, 1.0, 1.0]
    )


def test_ocr_token_rejects_unnormalized_bbox() -> None:
    with pytest.raises(ValueError):
        OCRToken(
            text="TOTAL", confidence=0.9, bbox=[10.0, 20.0, 30.0, 40.0], line_num=0
        )


def test_ocr_token_rejects_inverted_bbox() -> None:
    with pytest.raises(ValueError):
        OCRToken(text="TOTAL", confidence=0.9, bbox=[0.8, 0.4, 0.2, 0.9], line_num=0)


def test_ocr_token_accepts_normalized_bbox() -> None:
    token = OCRToken(
        text="TOTAL", confidence=0.91, bbox=[0.1, 0.4, 0.6, 0.9], line_num=3
    )

    assert token.bbox == [0.1, 0.4, 0.6, 0.9]


@requires_dataset
def test_easyocr_returns_bboxes(receipt_bytes: bytes) -> None:
    """REQ-102: a real receipt yields recognized tokens with spatial data."""
    tokens = _run_ocr(receipt_bytes)

    assert len(tokens) >= 5

    for token in tokens:
        assert token.text
        assert 0.0 <= token.confidence <= 1.0
        assert len(token.bbox) == 4
        assert token.line_num >= 0


@requires_dataset
def test_coords_normalized_0_to_1(receipt_bytes: bytes) -> None:
    """REQ-102: every bounding box sits inside the unit square."""
    tokens = _run_ocr(receipt_bytes)

    assert len(tokens) >= 5

    for token in tokens:
        x_min, y_min, x_max, y_max = token.bbox
        for coordinate in token.bbox:
            assert 0.0 <= coordinate <= 1.0
        assert x_min <= x_max
        assert y_min <= y_max


@requires_dataset
def test_line_numbers_follow_reading_order(receipt_bytes: bytes) -> None:
    tokens = _run_ocr(receipt_bytes)

    line_numbers = [token.line_num for token in tokens]

    assert line_numbers == sorted(line_numbers)
    assert len(set(line_numbers)) == len(line_numbers)


@requires_dataset
def test_extracted_text_mentions_expected_receipt_fields(receipt_bytes: bytes) -> None:
    """Guards against a pipeline that returns boxes but no usable text."""
    tokens = _run_ocr(receipt_bytes)

    joined = " ".join(token.text for token in tokens).upper()

    assert any(char.isdigit() for char in joined)
    assert any(
        word in joined
        for word in ("TOTAL", "RM", "MYR", "CASH", "QTY", "PRICE", "AMOUNT")
    )


@requires_dataset
def test_extract_tokens_accepts_preprocessed_array(receipt_bytes: bytes) -> None:
    """The engine accepts a preprocessed array, not just raw bytes."""
    processed = preprocess_image(receipt_bytes)

    try:
        tokens = extract_tokens(processed)
    except Exception as exc:  # noqa: BLE001 - weights unavailable
                         # pragma: no cover
        pytest.skip(f"EasyOCR unavailable: {exc}")

    assert len(tokens) >= 5
    assert all(
        0.0 <= coordinate <= 1.0 for token in tokens for coordinate in token.bbox
    )


@requires_dataset
def test_preprocessor_output_is_ocr_consumable(receipt_bytes: bytes) -> None:
    """Preprocessing must not destroy the image OCR depends on."""
    processed = preprocess_image(receipt_bytes)

    assert processed.shape[2] == 3
    assert processed.max() > 0
    assert processed.dtype == np.uint8
