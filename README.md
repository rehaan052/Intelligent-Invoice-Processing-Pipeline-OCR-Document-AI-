# Invoice OCR: Intelligent Document Processing Pipeline

A lightweight, **CPU-only** pipeline that turns invoice images into structured JSON
(vendor, invoice number, dates, subtotal, tax, total). It runs on a low-end laptop
with no GPU, uses about 115 MB of RAM and takes about 0.3 s per invoice.

```
image -> decode -> resize -> denoise -> illumination fix -> deskew -> Otsu -> ROI crop
      -> Tesseract OCR -> regex/keyword key-value extraction -> validation -> JSON
```

## Features

| Area | What it does |
|---|---|
| Preprocessing (OpenCV) | Median + Gaussian denoise, shadow/illumination normalisation, projection-profile deskew, Otsu binarisation, ROI cropping, size normalisation |
| OCR | Tesseract 5 (LSTM engine), per-word confidences |
| Extraction | Vendor, invoice no., invoice/due date (ISO format), subtotal, tax, total, currency, GSTIN, email, phone |
| OCR-error tolerance | Fixes common slips: `3.549.00` -> 3549.00, `tnvoice`, `(NV-...` -> `INV-...`, `Que Date` |
| Validation | `subtotal + tax == total` check flags digit errors that field presence alone would miss |
| Evaluation | CER, WER and per-field accuracy on labelled data, split by difficulty |
| Service | FastAPI: `/extract`, `/health`, `/metrics`, upload validation, request IDs, structured logs |
| Delivery | Docker (non-root, healthcheck), GitHub Actions CI, optional AWS ECR push |

## Quick start

**1. Install Tesseract** (the only system dependency)

| OS | Command |
|---|---|
| Ubuntu/Debian | `sudo apt install tesseract-ocr` |
| macOS | `brew install tesseract` |
| Windows | Install from the [UB Mannheim builds](https://github.com/UB-Mannheim/tesseract/wiki) and add it to `PATH` |

**2. Install Python packages**

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

**3. Try it**

```bash
python scripts/generate_samples.py --out samples --count 12     # synthetic labelled invoices
PYTHONPATH=src python -m invoice_ocr.cli samples/invoice_003_hard.png
```

On Windows PowerShell use `$env:PYTHONPATH="src"` before the command, or run
`pip install -e .` once and then call `invoice-ocr samples/invoice_003_hard.png`.

**4. Run the API**

```bash
PYTHONPATH=src uvicorn invoice_ocr.api:app --port 8000
# open http://localhost:8000/docs
curl -F "file=@samples/invoice_003_hard.png;type=image/png" http://localhost:8000/extract
```

**5. Docker**

```bash
docker build -t invoice-ocr .
docker run -p 8000:8000 invoice-ocr
```

## Results

Measured on 30 synthetic invoices (10 clean, 10 medium, 10 hard: rotation up to 8 degrees,
noise, blur, uneven lighting) on a 2-core CPU. Reproduce with
`python scripts/evaluate.py`.

| Slice | CER | WER | Field accuracy | Avg latency |
|---|---|---|---|---|
| Overall | 1.09% | 5.63% | 100% | 276 ms |
| Clean | 1.62% | 9.25% | 100% | 273 ms |
| Medium | 0.71% | 3.83% | 100% | 285 ms |
| Hard | 0.94% | 3.82% | 100% | 271 ms |

CER/WER are computed line by line (best-matching substring), so the two-column layout does
not distort the score. Peak memory for a single run is about 115 MB.

**Read this honestly:** the data is synthetic, rendered with one clean font, and the
extraction rules were tuned on the same generator. Real scans (stamps, handwriting, odd
layouts, low-resolution photos) will score lower. Before relying on this for real documents,
evaluate on your own labelled invoices. `scripts/evaluate.py` accepts any folder with the
same `ground_truth.json` format.

## API

`POST /extract` (multipart `file`, optional `include_text=false`) returns:

```json
{
  "filename": "invoice_006_hard.png",
  "fields": {
    "vendor_name": "Greenfield Traders",
    "invoice_number": "INV-2025-8353",
    "invoice_date": "2025-10-10",
    "due_date": "2025-10-20",
    "subtotal": 23118.0, "tax": 4161.24, "total": 27279.24,
    "currency": "INR",
    "missing_fields": [], "arithmetic_ok": true
  },
  "quality": {"mean_confidence": 93.52, "word_count": 60, "skew_corrected_deg": -4.25, "low_confidence": false},
  "timings_ms": {"preprocess": 56.6, "ocr": 247.1, "extraction": 1.1, "total": 304.8}
}
```

| Status | Meaning |
|---|---|
| 415 | Not an image type |
| 413 | File larger than `MAX_UPLOAD_MB` |
| 422 | File is not a decodable image |
| 503 | Tesseract missing or timed out |

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `OCR_LANG` | `eng` | Tesseract language pack |
| `OCR_PSM` / `OCR_OEM` | `6` / `1` | Page segmentation mode / LSTM engine |
| `OCR_TIMEOUT_S` | `60` | Per-image timeout |
| `MAX_IMAGE_SIDE` / `MIN_IMAGE_SIDE` | `2200` / `1200` | Resize bounds (lower the first to save CPU/RAM) |
| `MAX_UPLOAD_MB` | `10` | Upload limit |
| `LOG_LEVEL` | `INFO` | Logging level |

## Project layout

```
src/invoice_ocr/   preprocessing.py  ocr_engine.py  extraction.py  evaluation.py
                   pipeline.py  api.py  cli.py  config.py
scripts/           generate_samples.py  evaluate.py
tests/             37 tests: extraction, metrics, preprocessing, pipeline, API
docs/              AWS_DEPLOYMENT.md
.github/workflows/ ci.yml  (tests -> benchmark -> docker build -> optional ECR push)
```

## Limitations and next steps

- Extraction is rule-based: fast and explainable, but new layouts need new rules.
  A natural upgrade is a layout-aware model (for example LayoutLM or a small VLM) behind the same interface.
- Tesseract is weak on handwriting and very low-resolution photos. PaddleOCR or TrOCR can
  be plugged in by replacing `ocr_engine.run_ocr`.
- Line-item tables are not parsed yet (only the header fields and totals).
- PDFs are not supported directly. Convert pages to images first (for example with `pdf2image`).
- Metrics are in-process counters. In production, export them to CloudWatch or Prometheus.
