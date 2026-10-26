"""End-to-end pipeline: bytes in -> structured invoice JSON out."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from . import extraction, ocr_engine, preprocessing

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    text: str
    fields: extraction.InvoiceFields
    mean_confidence: float
    word_count: int
    skew_angle: float
    preprocessing_steps: list[str]
    timings_ms: dict[str, float] = field(default_factory=dict)

    def to_dict(self, include_text: bool = True) -> dict:
        out = {
            "fields": self.fields.to_dict(),
            "quality": {
                "mean_confidence": self.mean_confidence,
                "word_count": self.word_count,
                "skew_corrected_deg": self.skew_angle,
                "low_confidence": self.mean_confidence < 60,
            },
            "preprocessing_steps": self.preprocessing_steps,
            "timings_ms": self.timings_ms,
        }
        if include_text:
            out["raw_text"] = self.text
        return out


class InvoicePipeline:
    """Stateless, thread-safe pipeline."""

    def __init__(self, deskew: bool = True, crop: bool = True) -> None:
        self.deskew = deskew
        self.crop = crop

    def run_image(self, image_bgr) -> PipelineResult:
        timings: dict[str, float] = {}

        t0 = time.perf_counter()
        pre = preprocessing.preprocess(image_bgr, deskew=self.deskew, crop=self.crop)
        timings["preprocess"] = round((time.perf_counter() - t0) * 1000, 1)

        t1 = time.perf_counter()
        ocr = ocr_engine.run_ocr(pre.image)
        timings["ocr"] = round((time.perf_counter() - t1) * 1000, 1)

        t2 = time.perf_counter()
        fields = extraction.extract_invoice_fields(ocr.text)
        timings["extraction"] = round((time.perf_counter() - t2) * 1000, 1)
        timings["total"] = round((time.perf_counter() - t0) * 1000, 1)

        logger.info(
            "Processed invoice: conf=%.1f words=%d missing=%s total_ms=%.0f",
            ocr.mean_confidence, len(ocr.words), fields.missing_fields, timings["total"],
        )
        return PipelineResult(
            text=ocr.text,
            fields=fields,
            mean_confidence=ocr.mean_confidence,
            word_count=len(ocr.words),
            skew_angle=pre.skew_angle,
            preprocessing_steps=pre.steps,
            timings_ms=timings,
        )

    def run_bytes(self, data: bytes) -> PipelineResult:
        return self.run_image(preprocessing.decode_image(data))

    def run_path(self, path: str) -> PipelineResult:
        with open(path, "rb") as fh:
            return self.run_bytes(fh.read())
