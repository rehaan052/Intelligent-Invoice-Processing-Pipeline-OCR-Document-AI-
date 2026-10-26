"""Generate synthetic invoice images with known ground truth.

Why synthetic? It gives us labelled data for free, so we can measure real
CER/WER and field accuracy and run tests without any private documents.

Usage:  python scripts/generate_samples.py --out samples --count 12 --seed 7
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/Library/Fonts/Arial.ttf",
]
BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]

VENDORS = [
    "Sharma Office Supplies", "Bright Path Logistics", "Nova Tech Solutions",
    "Greenfield Traders", "Apex Cloud Services", "Urban Print House",
]
ITEMS = [
    ("A4 Paper Ream", 320.00), ("Laser Toner Cartridge", 4850.00), ("Wireless Mouse", 799.00),
    ("Cloud Hosting (monthly)", 2500.00), ("Ethernet Cable 10m", 450.00),
    ("Standing Desk Mat", 1299.00), ("Whiteboard Markers", 180.00), ("USB-C Hub", 2199.00),
]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


class RecordingDraw:
    """ImageDraw wrapper that remembers every string drawn (the OCR ground truth)."""

    def __init__(self, img: Image.Image) -> None:
        self._d = ImageDraw.Draw(img)
        self.lines: list[str] = []

    def text(self, xy, text, font=None, fill=None) -> None:
        self.lines.append(text)
        self._d.text(xy, text, font=font, fill=fill)

    def line(self, *args, **kwargs) -> None:
        self._d.line(*args, **kwargs)


def make_invoice(rng: random.Random) -> tuple[Image.Image, dict, list[str]]:
    vendor = rng.choice(VENDORS)
    inv_no = f"INV-{rng.randint(2024, 2026)}-{rng.randint(1000, 9999)}"
    day, month, year = rng.randint(1, 28), rng.randint(1, 12), rng.choice([2025, 2026])
    due_day = min(day + rng.randint(7, 30), 28)
    invoice_date = f"{year}-{month:02d}-{day:02d}"
    due_date = f"{year}-{month:02d}-{due_day:02d}"

    items = rng.sample(ITEMS, k=rng.randint(2, 4))
    rows, subtotal = [], 0.0
    for name, price in items:
        qty = rng.randint(1, 5)
        amount = round(price * qty, 2)
        subtotal += amount
        rows.append((name, qty, price, amount))
    subtotal = round(subtotal, 2)
    tax = round(subtotal * 0.18, 2)
    total = round(subtotal + tax, 2)

    W, H = 1240, 1000 + 60 * len(rows)
    img = Image.new("RGB", (W, H), "white")
    d = RecordingDraw(img)
    title, bold, body, small = (
        _font(BOLD_CANDIDATES, 44), _font(BOLD_CANDIDATES, 28),
        _font(FONT_CANDIDATES, 28), _font(FONT_CANDIDATES, 24),
    )

    d.text((70, 60), vendor, font=title, fill="black")
    d.text((70, 120), "12 Market Road, Patna, Bihar", font=small, fill="black")
    d.text((70, 155), f"billing@{vendor.split()[0].lower()}.com", font=small, fill="black")
    d.text((W - 330, 70), "INVOICE", font=title, fill="black")

    d.text((70, 240), f"Invoice No: {inv_no}", font=body, fill="black")
    d.text((70, 285), f"Invoice Date: {invoice_date}", font=body, fill="black")
    d.text((70, 330), f"Due Date: {due_date}", font=body, fill="black")
    d.text((700, 240), "Bill To:", font=bold, fill="black")
    d.text((700, 285), "Rehaan Traders Pvt Ltd", font=body, fill="black")

    y = 440
    d.line((70, y - 10, W - 70, y - 10), fill="black", width=2)
    for x, label in [(70, "Description"), (650, "Qty"), (800, "Rate"), (1000, "Amount")]:
        d.text((x, y), label, font=bold, fill="black")
    d.line((70, y + 45, W - 70, y + 45), fill="black", width=2)
    y += 65
    for name, qty, price, amount in rows:
        d.text((70, y), name, font=body, fill="black")
        d.text((650, y), str(qty), font=body, fill="black")
        d.text((800, y), f"{price:,.2f}", font=body, fill="black")
        d.text((1000, y), f"{amount:,.2f}", font=body, fill="black")
        y += 55

    y += 30
    d.line((700, y, W - 70, y), fill="black", width=2)
    y += 20
    d.text((700, y), f"Subtotal: Rs. {subtotal:,.2f}", font=body, fill="black")
    d.text((700, y + 50), f"GST (18%): Rs. {tax:,.2f}", font=body, fill="black")
    d.text((700, y + 105), f"Total Amount: Rs. {total:,.2f}", font=bold, fill="black")

    expected = {
        "vendor_name": vendor,
        "invoice_number": inv_no,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
    }
    return img, expected, d.lines


def degrade(img: Image.Image, rng: random.Random, level: str) -> Image.Image:
    """Simulate real-world scans: rotation, blur, noise, uneven lighting."""
    arr = np.array(img)
    if level == "clean":
        return img

    angle = rng.uniform(-4, 4) if level == "medium" else rng.uniform(-8, 8)
    h, w = arr.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    arr = cv2.warpAffine(arr, m, (w, h), borderValue=(255, 255, 255))

    if level == "hard":
        arr = cv2.GaussianBlur(arr, (3, 3), 0)
        gradient = np.tile(np.linspace(0.75, 1.0, w), (h, 1))[..., None]
        arr = (arr * gradient).astype(np.uint8)
    noise = np.random.default_rng(rng.randint(0, 10_000)).normal(0, 8 if level == "medium" else 14, arr.shape)
    arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="samples")
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    levels = ["clean", "medium", "hard"]
    manifest = []

    for i in range(args.count):
        level = levels[i % len(levels)]
        img, expected, reference_lines = make_invoice(rng)
        img = degrade(img, rng, level)
        name = f"invoice_{i + 1:03d}_{level}.png"
        img.save(out / name)
        manifest.append({"file": name, "difficulty": level, "expected": expected,
                         "reference_lines": reference_lines})

    (out / "ground_truth.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {len(manifest)} invoices + ground_truth.json to {out}/")


if __name__ == "__main__":
    main()
