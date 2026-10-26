import pytest

from invoice_ocr.extraction import extract_invoice_fields, parse_amount

SAMPLE = """Nova Tech Solutions INVOICE
12 Market Road, Patna, Bihar
billing@nova.com
Invoice No: INV-2024-7468 Bill To:
Invoice Date: 2025-01-21 Rehaan Traders Pvt Ltd
Due Date: 2025-01-28
Standing Desk Mat 1 1,299.00 1,299.00
Subtotal: Rs. 3,549.00
GST (18%): Rs. 638.82
Total Amount: Rs. 4,187.82"""


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1,234.50", 1234.50),
        ("1.234.50", 1234.50),   # OCR read the thousands comma as a dot
        ("3.549.00", 3549.00),
        ("638.82", 638.82),
        ("13,400.00", 13400.00),
        ("7100", 7100.0),
        ("1 299.00", 1299.0),
    ],
)
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == pytest.approx(expected)


def test_extracts_all_core_fields():
    f = extract_invoice_fields(SAMPLE)
    assert f.vendor_name == "Nova Tech Solutions"
    assert f.invoice_number == "INV-2024-7468"
    assert f.invoice_date == "2025-01-21"
    assert f.due_date == "2025-01-28"
    assert f.subtotal == pytest.approx(3549.0)
    assert f.tax == pytest.approx(638.82)
    assert f.total == pytest.approx(4187.82)
    assert f.currency == "INR"
    assert f.email == "billing@nova.com"
    assert f.missing_fields == []
    assert f.arithmetic_ok is True


def test_total_does_not_pick_up_subtotal():
    f = extract_invoice_fields("Subtotal: 500.00\nTax: 90.00\nTotal: 590.00")
    assert f.total == pytest.approx(590.0)
    assert f.subtotal == pytest.approx(500.0)


def test_arithmetic_check_flags_ocr_digit_error():
    bad = SAMPLE.replace("Rs. 4,187.82", "Rs. 4,787.82")
    assert extract_invoice_fields(bad).arithmetic_ok is False


def test_tolerates_common_ocr_slips():
    noisy = "Sharma Office Supplies INVOICE\ntnvoice No: (NV-2026-7499\nQue Date: 2025-04-26\nTotal Amount: Rs. 15,812.00"
    f = extract_invoice_fields(noisy)
    assert f.invoice_number == "INV-2026-7499"
    assert f.due_date == "2025-04-26"


@pytest.mark.parametrize(
    "line, iso",
    [
        ("Invoice Date: 21/01/2025", "2025-01-21"),
        ("Date: 21 Jan 2025", "2025-01-21"),
        ("Date: January 21, 2025", "2025-01-21"),
        ("Invoice Date: 2025-01-21", "2025-01-21"),
    ],
)
def test_date_formats(line, iso):
    assert extract_invoice_fields(line).invoice_date == iso


def test_missing_fields_reported_on_empty_text():
    f = extract_invoice_fields("")
    assert set(f.missing_fields) == {"vendor_name", "invoice_number", "invoice_date", "total"}
    assert f.arithmetic_ok is None
