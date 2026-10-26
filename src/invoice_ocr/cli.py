"""Command line interface:  python -m invoice_ocr.cli path/to/invoice.png"""

from __future__ import annotations

import argparse
import json
import sys

from .ocr_engine import OCRUnavailableError, check_tesseract
from .pipeline import InvoicePipeline
from .preprocessing import ImageDecodeError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract structured data from invoice images.")
    parser.add_argument("images", nargs="+", help="One or more invoice image paths")
    parser.add_argument("--no-deskew", action="store_true", help="Disable skew correction")
    parser.add_argument("--show-text", action="store_true", help="Include raw OCR text in output")
    args = parser.parse_args(argv)

    try:
        check_tesseract()
    except OCRUnavailableError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    pipeline = InvoicePipeline(deskew=not args.no_deskew)
    exit_code = 0
    for path in args.images:
        try:
            result = pipeline.run_path(path)
            print(json.dumps({"file": path, **result.to_dict(include_text=args.show_text)}, indent=2))
        except (ImageDecodeError, FileNotFoundError, OCRUnavailableError) as exc:
            print(f"Error processing {path}: {exc}", file=sys.stderr)
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
