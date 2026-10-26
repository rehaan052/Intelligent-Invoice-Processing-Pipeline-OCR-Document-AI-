"""Image preprocessing: the step that makes or breaks OCR accuracy.

Pipeline:  decode -> resize -> grayscale -> denoise -> illumination fix -> deskew -> Otsu binarise -> ROI crop
Every stage is pure OpenCV/NumPy, so it runs fast on a CPU with no GPU.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

from .config import settings

logger = logging.getLogger(__name__)


class ImageDecodeError(ValueError):
    """Raised when the uploaded bytes are not a decodable image."""


@dataclass
class PreprocessResult:
    image: np.ndarray                      # final binarised image fed to OCR
    skew_angle: float = 0.0                # degrees corrected
    scale: float = 1.0                     # resize factor applied
    steps: list[str] = field(default_factory=list)


def decode_image(data: bytes) -> np.ndarray:
    """Decode raw bytes into a BGR image."""
    if not data:
        raise ImageDecodeError("Empty file.")
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ImageDecodeError("File is not a valid image (PNG/JPG/BMP/TIFF/WEBP).")
    return img


def resize_for_ocr(img: np.ndarray) -> tuple[np.ndarray, float]:
    """Keep the long edge within [min_image_side, max_image_side]."""
    h, w = img.shape[:2]
    long_edge = max(h, w)
    scale = 1.0
    if long_edge > settings.max_image_side:
        scale = settings.max_image_side / long_edge
    elif long_edge < settings.min_image_side:
        scale = settings.min_image_side / long_edge
    if abs(scale - 1.0) < 1e-3:
        return img, 1.0
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    resized = cv2.resize(img, None, fx=scale, fy=scale, interpolation=interp)
    return resized, scale


def to_gray(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def denoise(gray: np.ndarray) -> np.ndarray:
    """Median (salt-and-pepper) then a light Gaussian (sensor/film grain).

    Far cheaper than non-local-means, which matters on low-end CPUs.
    """
    return cv2.GaussianBlur(cv2.medianBlur(gray, 3), (3, 3), 0)


def normalise_illumination(gray: np.ndarray) -> np.ndarray:
    """Remove shadows and uneven lighting (phone photos, scanner edges).

    Estimate the page background with a max-filter + big median, then divide it
    out so paper becomes uniformly white while ink stays dark.
    """
    background = cv2.medianBlur(cv2.dilate(gray, np.ones((7, 7), np.uint8)), 21)
    return cv2.divide(gray, background, scale=255)


def binarise(gray: np.ndarray) -> np.ndarray:
    """Otsu threshold. After illumination normalisation a global threshold is
    both sharper and less noisy than an adaptive one."""
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    return bw


def _projection_score(binary_inv: np.ndarray, angle: float) -> float:
    """Variance of row sums: text lines aligned with the rows give sharp peaks."""
    h, w = binary_inv.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(binary_inv, matrix, (w, h), flags=cv2.INTER_LINEAR)
    return float(np.var(rotated.sum(axis=1, dtype=np.float64)))


def estimate_skew_angle(gray: np.ndarray, max_angle: float = 12.0) -> float:
    """Estimate skew with a projection-profile search (coarse then fine).

    Returns degrees to rotate (positive = counter-clockwise, same convention as
    `rotate`) to straighten the page. Runs on a ~700px thumbnail, so it costs
    only a few milliseconds. Returns 0 when there is too little ink to decide.
    """
    h, w = gray.shape[:2]
    scale = 700 / max(h, w)
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
    _, inv = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    inv = cv2.medianBlur(inv, 3)  # drop isolated speckles
    if cv2.countNonZero(inv) < 300:
        return 0.0

    coarse = np.arange(-max_angle, max_angle + 0.01, 1.0)
    best = max(coarse, key=lambda a: _projection_score(inv, a))
    fine = np.arange(best - 1.0, best + 1.01, 0.25)
    best = max(fine, key=lambda a: _projection_score(inv, a))
    return 0.0 if abs(best) < 0.3 else float(round(best, 2))


def rotate(img: np.ndarray, angle: float, border_value: int | tuple = 255) -> np.ndarray:
    if abs(angle) < 0.1:
        return img
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        img, matrix, (w, h), flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT, borderValue=border_value,
    )


def crop_to_content(binary: np.ndarray, margin: int = 20) -> np.ndarray:
    """Crop away empty page margins (simple ROI extraction)."""
    inverted = cv2.bitwise_not(binary)
    coords = cv2.findNonZero(inverted)
    if coords is None:
        return binary
    x, y, w, h = cv2.boundingRect(coords)
    # Ignore if the crop would remove most of the page (likely noise).
    if w * h < 0.1 * binary.shape[0] * binary.shape[1]:
        return binary
    H, W = binary.shape[:2]
    x0, y0 = max(x - margin, 0), max(y - margin, 0)
    x1, y1 = min(x + w + margin, W), min(y + h + margin, H)
    return binary[y0:y1, x0:x1]


def preprocess(img: np.ndarray, *, deskew: bool = True, crop: bool = True) -> PreprocessResult:
    """Run the full preprocessing chain and report what was done."""
    steps: list[str] = []

    img, scale = resize_for_ocr(img)
    steps.append(f"resize(x{scale:.2f})")

    gray = to_gray(img)
    gray = denoise(gray)
    steps.append("denoise")
    gray = normalise_illumination(gray)
    steps.append("illumination_normalise")

    angle = 0.0
    if deskew:
        angle = estimate_skew_angle(gray)
        if abs(angle) >= 0.1:
            gray = rotate(gray, angle)
            steps.append(f"deskew({angle:.1f}deg)")

    binary = binarise(gray)
    steps.append("otsu_threshold")

    if crop:
        binary = crop_to_content(binary)
        steps.append("crop_roi")

    logger.debug("Preprocessing steps: %s", steps)
    return PreprocessResult(image=binary, skew_angle=angle, scale=scale, steps=steps)
