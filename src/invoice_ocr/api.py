"""FastAPI inference service.

Run:  uvicorn invoice_ocr.api:app --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from . import __version__, ocr_engine
from .config import settings
from .pipeline import InvoicePipeline
from .preprocessing import ImageDecodeError

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger("invoice_ocr.api")

pipeline = InvoicePipeline()
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/bmp", "image/tiff", "image/webp"}

# Lightweight in-process metrics (swap for Prometheus/CloudWatch in production).
metrics = {"requests": 0, "failures": 0, "total_latency_ms": 0.0, "low_confidence": 0}


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        logger.info("Tesseract version: %s", ocr_engine.check_tesseract())
    except ocr_engine.OCRUnavailableError as exc:
        logger.error("%s", exc)
    yield


app = FastAPI(
    title="Invoice OCR API",
    version=__version__,
    description="CPU-only invoice OCR: preprocessing, Tesseract, key-value extraction.",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    logger.info(
        "%s %s -> %s in %.0fms [%s]",
        request.method, request.url.path, response.status_code,
        (time.perf_counter() - start) * 1000, request_id,
    )
    return response


@app.get("/health")
def health() -> dict:
    """Liveness + readiness: verifies Tesseract is reachable."""
    try:
        version = ocr_engine.check_tesseract()
    except ocr_engine.OCRUnavailableError as exc:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "detail": str(exc)})
    return {"status": "ok", "tesseract": version, "version": __version__}


@app.get("/metrics")
def get_metrics() -> dict:
    n = metrics["requests"] or 1
    return {**metrics, "avg_latency_ms": round(metrics["total_latency_ms"] / n, 1)}


@app.post("/extract")
async def extract(file: UploadFile = File(...), include_text: bool = True) -> dict:
    """Upload an invoice image and receive structured JSON."""
    metrics["requests"] += 1

    if file.content_type not in ALLOWED_TYPES:
        metrics["failures"] += 1
        raise HTTPException(415, f"Unsupported file type '{file.content_type}'. Upload PNG/JPG/BMP/TIFF/WEBP.")

    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        metrics["failures"] += 1
        raise HTTPException(413, f"File too large (max {settings.max_upload_mb} MB).")

    try:
        # OCR is CPU-bound and blocking, so keep it off the event loop.
        result = await run_in_threadpool(pipeline.run_bytes, data)
    except ImageDecodeError as exc:
        metrics["failures"] += 1
        raise HTTPException(422, str(exc)) from exc
    except ocr_engine.OCRUnavailableError as exc:
        metrics["failures"] += 1
        raise HTTPException(503, str(exc)) from exc

    metrics["total_latency_ms"] += result.timings_ms.get("total", 0.0)
    if result.mean_confidence < 60:
        metrics["low_confidence"] += 1
    return {"filename": file.filename, **result.to_dict(include_text=include_text)}
