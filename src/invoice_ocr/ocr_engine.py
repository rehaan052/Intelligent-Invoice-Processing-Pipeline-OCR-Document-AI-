"""Thin wrapper around Tesseract (CPU only, ~100 MB RAM, no GPU needed)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pytesseract
from pytesseract import Output

from .config import settings

logger = logging.getLogger(__name__)


class OCRUnavailableError(RuntimeError):
    """Tesseract binary is missing or failed."""


@dataclass
class OCRWord:
    text: str
    conf: float
    left: int
    top: int
    width: int
    height: int


@dataclass
class OCRResult:
    text: str
    words: list[OCRWord]
    mean_confidence: float


def _config() -> str:
    return f"--oem {settings.tesseract_oem} --psm {settings.tesseract_psm}"


def check_tesseract() -> str:
    """Return the Tesseract version or raise OCRUnavailableError."""
    try:
        return str(pytesseract.get_tesseract_version())
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRUnavailableError(
            "Tesseract is not installed. Install it (e.g. `sudo apt install tesseract-ocr`, "
            "`brew install tesseract`, or the Windows installer) and make sure it is on PATH."
        ) from exc


def run_ocr(image: np.ndarray) -> OCRResult:
    """Run Tesseract and return text plus per-word confidences."""
    try:
        data = pytesseract.image_to_data(
            image,
            lang=settings.tesseract_lang,
            config=_config(),
            output_type=Output.DICT,
            timeout=settings.tesseract_timeout_s,
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRUnavailableError("Tesseract is not installed or not on PATH.") from exc
    except RuntimeError as exc:  # pytesseract raises RuntimeError on timeout
        raise OCRUnavailableError(f"Tesseract failed or timed out: {exc}") from exc

    words: list[OCRWord] = []
    lines: dict[tuple[int, int, int], list[str]] = {}
    for i, raw in enumerate(data["text"]):
        text = raw.strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if not text or conf < 0:
            continue
        words.append(
            OCRWord(
                text=text, conf=conf,
                left=int(data["left"][i]), top=int(data["top"][i]),
                width=int(data["width"][i]), height=int(data["height"][i]),
            )
        )
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(text)

    full_text = "\n".join(" ".join(ws) for ws in lines.values())
    mean_conf = float(np.mean([w.conf for w in words])) if words else 0.0
    return OCRResult(text=full_text, words=words, mean_confidence=round(mean_conf, 2))
