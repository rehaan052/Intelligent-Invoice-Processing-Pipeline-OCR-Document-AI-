# Small, CPU-only image. Tesseract + OpenCV(headless) keep it well under 500 MB.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first so Docker caches this layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src ./src
ENV PYTHONPATH=/app/src

# Run as a non-root user.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

# One worker keeps RAM low on small machines; scale with more containers instead.
CMD ["uvicorn", "invoice_ocr.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
