"""Image normalization for faded, curled thermal receipts (docs/05_trd.md §5.2.1).

Order matters: orientation is corrected *before* scaling so the longest edge is
measured on the upright image, and denoising runs last so CLAHE's output is not
re-smoothed away.

Three containers are supported: JPEG/PNG (OpenCV), HEIC (``pillow-heif``) and
PDF (PyMuPDF, page 1 at 200 DPI). Every decoder enforces ``MAX_IMAGE_PIXELS``
before allocating a full-resolution buffer, so a decompression bomb is a bounded
``ERR_FILE_CORRUPT`` rather than an out-of-memory crash.
"""

from __future__ import annotations

import io
import struct

import cv2
import numpy as np
import piexif
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError

EXIF_ORIENTATION_TAG = 0x0112  # Orientation

MAX_DIMENSION = 2048
# 40 MP is above any phone camera this demo targets and below the point where a
# decode can exhaust the container's memory budget.
MAX_IMAGE_PIXELS = 40_000_000
PDF_DPI = 200

CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_GRID_SIZE = (8, 8)

BILATERAL_D = 9
BILATERAL_SIGMA_COLOR = 75
BILATERAL_SIGMA_SPACE = 75


class ImageDecodeError(ValueError):
    """Raised when the payload is not a decodable image."""


# cv2.imdecode applies EXIF rotation by default. We disable it here so the
# orientation transform is applied exactly once, explicitly, in auto_orient_image.
_RAW_DECODE_FLAGS = cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION


def _check_pixels(width: int, height: int) -> None:
    """Reject non-positive or oversized raster dimensions before decoding."""
    if width <= 0 or height <= 0:
        raise ImageDecodeError("image has no pixels")
    if width * height > MAX_IMAGE_PIXELS:
        megapixels = width * height / 1_000_000
        raise ImageDecodeError(
            f"image is {megapixels:.1f} MP, above the {MAX_IMAGE_PIXELS // 1_000_000} MP limit"
        )


def _probe_size(image_bytes: bytes) -> tuple[int, int]:
    """Read raster dimensions from the header without decoding pixel data."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as probe:
            return probe.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageDecodeError("Payload is not a decodable image") from exc


def decode_image(image_bytes: bytes) -> NDArray[np.uint8]:
    """Decode bytes to a BGR array, raising ImageDecodeError on garbage input."""
    if not image_bytes:
        raise ImageDecodeError("Empty image payload")
    _check_pixels(*_probe_size(image_bytes))

    array = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), _RAW_DECODE_FLAGS)
    if array is None:
        raise ImageDecodeError("Payload is not a decodable image")
    _check_pixels(array.shape[1], array.shape[0])
    return array


def read_exif_orientation(image_bytes: bytes) -> int:
    """Return EXIF orientation tag 0x0112, defaulting to 1 (upright) when absent."""
    try:
        exif_dict = piexif.load(image_bytes)
    except (piexif.InvalidImageDataError, ValueError, KeyError, OSError, struct.error):
        # Absent or unreadable EXIF is normal for PNG, screenshots and downloads.
        # piexif has no ``exceptions`` submodule (a nonexistent attribute in the
        # except clause would itself raise AttributeError); its error class is
        # exported at the top level and subclasses ValueError. Images without an
        # EXIF header can also fail inside piexif with struct.error.
        return 1

    try:
        orientation = exif_dict["0th"].get(EXIF_ORIENTATION_TAG, 1)
    except (KeyError, TypeError):
        return 1
    return int(orientation) if isinstance(orientation, int) else 1


def auto_orient_image(image_bytes: bytes) -> NDArray[np.uint8]:
    """Decode and rotate per EXIF orientation so the receipt reads upright.

    Mirrors a camera/decoder for orientations 2-8 (mirrored cases included).
    """
    image = decode_image(image_bytes)
    orientation = read_exif_orientation(image_bytes)

    if orientation == 1:
        return image
    if orientation == 2:
        return cv2.flip(image, cv2.FLIP_LEFT_RIGHT)
    if orientation == 3:
        return cv2.rotate(image, cv2.ROTATE_180)
    if orientation == 4:
        return cv2.flip(image, cv2.FLIP_TOP_BOTTOM)
    if orientation == 5:
        return cv2.rotate(cv2.flip(image, cv2.FLIP_LEFT_RIGHT), cv2.ROTATE_90_CLOCKWISE)
    if orientation == 6:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)  # real 90
    if orientation == 7:
        return cv2.rotate(
            cv2.flip(image, cv2.FLIP_LEFT_RIGHT), cv2.ROTATE_90_COUNTERCLOCKWISE
        )
    if orientation == 8:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)  # real 270
    return image


def decode_heic(image_bytes: bytes) -> NDArray[np.uint8]:
    """Decode a HEIC/HEIF payload, honouring the EXIF orientation, as BGR."""
    if not image_bytes:
        raise ImageDecodeError("Empty image payload")
    try:
        import pillow_heif
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise ImageDecodeError("HEIC decoder is not installed") from exc

    pillow_heif.register_heif_opener()
    try:
        with Image.open(io.BytesIO(image_bytes)) as probe:
            _check_pixels(*probe.size)
        with Image.open(io.BytesIO(image_bytes)) as image:
            rgb = ImageOps.exif_transpose(image).convert("RGB")
            pixels = np.asarray(rgb)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageDecodeError("HEIC payload could not be decoded") from exc

    _check_pixels(pixels.shape[1], pixels.shape[0])
    return cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)


def decode_pdf(image_bytes: bytes) -> NDArray[np.uint8]:
    """Rasterize page 1 of a PDF at 200 DPI, as BGR.

    Only the first page is read: a receipt is a single document, and rendering
    every page would multiply the cost of a hostile upload.
    """
    if not image_bytes:
        raise ImageDecodeError("Empty PDF payload")
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise ImageDecodeError("PDF decoder is not installed") from exc

    try:
        document = pymupdf.open(stream=image_bytes, filetype="pdf")
    except Exception as exc:
        raise ImageDecodeError("PDF payload could not be opened") from exc

    try:
        if document.needs_pass or document.is_encrypted:
            raise ImageDecodeError("encrypted PDFs are not supported")
        if document.page_count < 1:
            raise ImageDecodeError("PDF has no pages")

        page = document.load_page(0)
        rect = page.rect
        scale = PDF_DPI / 72.0
        _check_pixels(
            int(round(rect.width * scale)), int(round(rect.height * scale))
        )

        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(scale, scale), alpha=False, colorspace=pymupdf.csRGB
        )
        _check_pixels(pixmap.width, pixmap.height)
        pixels = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
            pixmap.height, pixmap.width, 3
        )
        return cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR).copy()
    except ImageDecodeError:
        raise
    except Exception as exc:
        raise ImageDecodeError("PDF page could not be rasterized") from exc
    finally:
        document.close()


def apply_clahe_contrast(cv_image: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """Apply CLAHE to the LAB L-channel to recover faded thermal ink.

    Equalizing the L-channel only: the A/B channels carry paper tint and yellowing
    that must stay intact, and clipping at 2.0 keeps the paper background from
    blowing out to pure white (which would erase faint text).
    """
    lab = cv2.cvtColor(cv_image, cv2.COLOR_BGR2LAB)
    lightness, a_channel, b_channel = cv2.split(lab)

    clahe = cv2.createCLAHE(
        clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_GRID_SIZE
    )
    enhanced_lightness = clahe.apply(lightness)

    merged = cv2.merge((enhanced_lightness, a_channel, b_channel))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def resize_if_needed(
    cv_image: NDArray[np.uint8], max_dim: int = MAX_DIMENSION
) -> NDArray[np.uint8]:
    """Downscale so max(height, width) <= max_dim, preserving aspect ratio.

    Upscaling is deliberately not performed: a small crop stays small rather than
    being blown up into blurry artefacts for the OCR model.
    """
    height, width = cv_image.shape[:2]
    longest_edge = max(height, width)
    if longest_edge <= max_dim:
        return cv_image

    scale = max_dim / float(longest_edge)
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))

    # INTER_AREA is the correct kernel for downscaling (averages, avoids aliasing).
    return cv2.resize(cv_image, (new_width, new_height), interpolation=cv2.INTER_AREA)


def denoise(cv_image: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """Smooth paper texture while preserving character edge gradients."""
    return cv2.bilateralFilter(
        cv_image,
        d=BILATERAL_D,
        sigmaColor=BILATERAL_SIGMA_COLOR,
        sigmaSpace=BILATERAL_SIGMA_SPACE,
    )


def preprocess_image(
    image_bytes: bytes, max_dim: int = MAX_DIMENSION
) -> NDArray[np.uint8]:
    """Run the full §5.2.1 chain: orient -> scale -> CLAHE -> denoise."""
    image = auto_orient_image(image_bytes)
    image = resize_if_needed(image, max_dim=max_dim)
    image = apply_clahe_contrast(image)
    return denoise(image)


def preprocess_receipt(
    payload: bytes, mime_type: str | None = None, max_dim: int = MAX_DIMENSION
) -> NDArray[np.uint8]:
    """Normalize any supported container (JPEG/PNG/HEIC/PDF) for OCR."""
    if mime_type == "application/pdf":
        image = decode_pdf(payload)
    elif mime_type == "image/heic":
        image = decode_heic(payload)
    else:
        return preprocess_image(payload, max_dim=max_dim)

    image = resize_if_needed(image, max_dim=max_dim)
    image = apply_clahe_contrast(image)
    return denoise(image)


__all__ = [
    "ImageDecodeError",
    "MAX_DIMENSION",
    "MAX_IMAGE_PIXELS",
    "PDF_DPI",
    "apply_clahe_contrast",
    "auto_orient_image",
    "decode_heic",
    "decode_image",
    "decode_pdf",
    "denoise",
    "preprocess_image",
    "preprocess_receipt",
    "read_exif_orientation",
    "resize_if_needed",
]
