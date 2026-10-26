import random
import sys
from io import BytesIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import generate_samples  # noqa: E402


@pytest.fixture(scope="session")
def invoice():
    """One clean synthetic invoice: (PIL image, expected fields, reference lines)."""
    return generate_samples.make_invoice(random.Random(11))


@pytest.fixture(scope="session")
def invoice_png_bytes(invoice):
    buf = BytesIO()
    invoice[0].save(buf, format="PNG")
    return buf.getvalue()
