import pytest

from invoice_ocr.evaluation import cer, edit_distance, field_accuracy, line_cer, wer


def test_edit_distance_basics():
    assert edit_distance("kitten", "sitting") == 3
    assert edit_distance("", "abc") == 3
    assert edit_distance("abc", "abc") == 0


def test_cer_wer():
    assert cer("hello world", "hello world") == 0.0
    assert cer("abcd", "abxd") == pytest.approx(0.25)
    assert wer("the quick brown fox", "the quick brown dog") == pytest.approx(0.25)
    assert cer("", "") == 0.0 and cer("", "x") == 1.0


def test_line_cer_is_order_independent_and_ignores_extra_text():
    page = "completely unrelated header Total: 590.00 more text Invoice No: INV-1"
    assert line_cer(["Invoice No: INV-1", "Total: 590.00"], page) == 0.0
    assert line_cer(["Total: 590.00"], page.replace("590", "599")) > 0.0


def test_field_accuracy():
    out = field_accuracy(
        {"total": 100.0, "vendor_name": "Acme", "invoice_number": "A1"},
        {"total": 100.004, "vendor_name": "acme", "invoice_number": None},
    )
    assert out["correct"] == 2 and out["total"] == 3
    assert out["per_field"]["invoice_number"] is False
    assert out["accuracy"] == pytest.approx(0.6667, abs=1e-3)
