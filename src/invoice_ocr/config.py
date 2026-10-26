"""Central configuration, overridable through environment variables."""

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Tesseract: --oem 1 = LSTM engine, --psm 6 = assume a uniform block of text.
    tesseract_lang: str = os.getenv("OCR_LANG", "eng")
    tesseract_oem: int = _env_int("OCR_OEM", 1)
    tesseract_psm: int = _env_int("OCR_PSM", 6)
    tesseract_timeout_s: int = _env_int("OCR_TIMEOUT_S", 60)

    # Images are downscaled to this long edge to keep RAM/CPU low on weak machines.
    max_image_side: int = _env_int("MAX_IMAGE_SIDE", 2200)
    # Images smaller than this are upscaled (Tesseract works best at ~300 DPI).
    min_image_side: int = _env_int("MIN_IMAGE_SIDE", 1200)

    max_upload_mb: int = _env_int("MAX_UPLOAD_MB", 10)
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
