"""Image normalization for faded, curled thermal receipts (docs/05_trd.md §5.2.1).

Order matters: orientation is corrected *before* scaling so the longest edge is
measured on the upright image, and denoising runs last so CLAHE's output is not
re-smoothed away.
"""

from __future__ import annotations

import cv2
import numpy as np
import piexif
from numpy.typing import NDArray

EXIF_ORIENTATION_TAG = 0x0112  # Orientation

MAX_DIMENSION = 2048
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


def decode_image(image_bytes: bytes) -> NDArray[np.uint8]:
    """Decode bytes to a BGR array, raising ImageDecodeError on garbage input."""
    if not image_bytes:
        raise ImageDecodeError("Empty image payload")
    array = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), _RAW_DECODE_FLAGS)
    if array is None:
        raise ImageDecodeError("Payload is not a decodable image")
    return array


def read_exif_orientation(image_bytes: bytes) -> int:
    """Return EXIF orientation tag 0x0112, defaulting to 1 (upright) when absent."""
    try:
        exif_dict = piexif.load(image_bytes)
    except (piexif.exceptions.InvalidImageDataError, ValueError, KeyError, OSError):
        # Corrupt/absent EXIF is normal for downloads and screenshots.
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
