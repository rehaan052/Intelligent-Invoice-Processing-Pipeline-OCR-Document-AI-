import pytest
from fastapi.testclient import TestClient

from invoice_ocr.api import app
from invoice_ocr.ocr_engine import OCRUnavailableError, check_tesseract
from invoice_ocr.pipeline import InvoicePipeline

try:
    check_tesseract()
    HAS_TESSERACT = True
except OCRUnavailableError:
    HAS_TESSERACT = False

needs_tesseract = pytest.mark.skipif(not HAS_TESSERACT, reason="Tesseract not installed")
client = TestClient(app)


@needs_tesseract
def test_pipeline_extracts_expected_fields(invoice_png_bytes, invoice):
    expected = invoice[1]
    result = InvoicePipeline().run_bytes(invoice_png_bytes)
    f = result.fields
    assert f.invoice_number == expected["invoice_number"]
    assert f.invoice_date == expected["invoice_date"]
    assert f.total == pytest.approx(expected["total"])
    assert f.arithmetic_ok is True
    assert result.mean_confidence > 70
    assert set(result.timings_ms) == {"preprocess", "ocr", "extraction", "total"}


@needs_tesseract
def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


@needs_tesseract
def test_extract_endpoint_happy_path(invoice_png_bytes, invoice):
    r = client.post("/extract", files={"file": ("inv.png", invoice_png_bytes, "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["fields"]["invoice_number"] == invoice[1]["invoice_number"]
    assert "raw_text" in body and "x-request-id" in r.headers


@needs_tesseract
def test_extract_can_omit_raw_text(invoice_png_bytes):
    r = client.post("/extract?include_text=false", files={"file": ("inv.png", invoice_png_bytes, "image/png")})
    assert r.status_code == 200 and "raw_text" not in r.json()


def test_rejects_wrong_content_type():
    r = client.post("/extract", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 415


def test_rejects_corrupt_image():
    r = client.post("/extract", files={"file": ("a.png", b"not really a png", "image/png")})
    assert r.status_code == 422


def test_rejects_oversized_upload(monkeypatch):
    from invoice_ocr import api
    from invoice_ocr.config import Settings
    monkeypatch.setattr(api, "settings", Settings(max_upload_mb=0))  # auto-restored after the test
    r = client.post("/extract", files={"file": ("a.png", b"x" * 10, "image/png")})
    assert r.status_code == 413


def test_metrics_endpoint():
    r = client.get("/metrics")
    assert r.status_code == 200 and {"requests", "failures", "avg_latency_ms"} <= set(r.json())
