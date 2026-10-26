import cv2
import numpy as np
import pytest

from invoice_ocr import preprocessing as pp


def _text_page(w=1000, h=800):
    img = np.full((h, w, 3), 255, np.uint8)
    for y in range(120, h - 100, 70):
        cv2.putText(img, "Invoice No INV-2025-1234 Total 5000.00", (80, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 3, cv2.LINE_AA)
    return img


def test_decode_rejects_garbage_and_empty():
    with pytest.raises(pp.ImageDecodeError):
        pp.decode_image(b"")
    with pytest.raises(pp.ImageDecodeError):
        pp.decode_image(b"this is not an image")


def test_resize_bounds():
    big = np.zeros((4000, 3000, 3), np.uint8)
    out, scale = pp.resize_for_ocr(big)
    assert max(out.shape[:2]) <= 2200 and scale < 1
    small = np.zeros((300, 200, 3), np.uint8)
    out, scale = pp.resize_for_ocr(small)
    assert max(out.shape[:2]) >= 1200 and scale > 1


@pytest.mark.parametrize("angle", [-7.0, -3.0, 4.0, 8.0])
def test_deskew_recovers_rotation(angle):
    gray = pp.to_gray(_text_page())
    skewed = pp.rotate(gray, angle)
    estimated = pp.estimate_skew_angle(skewed)
    # Rotating by the estimate must cancel the applied skew.
    assert abs(estimated + angle) <= 1.0


def test_straight_page_is_left_alone():
    assert abs(pp.estimate_skew_angle(pp.to_gray(_text_page()))) <= 0.5


def test_blank_page_does_not_crash():
    blank = np.full((600, 600), 255, np.uint8)
    assert pp.estimate_skew_angle(blank) == 0.0
    result = pp.preprocess(np.full((600, 600, 3), 255, np.uint8))
    assert result.image.ndim == 2


def test_preprocess_output_is_binary():
    result = pp.preprocess(_text_page())
    assert set(np.unique(result.image)).issubset({0, 255})
    assert "otsu_threshold" in result.steps
