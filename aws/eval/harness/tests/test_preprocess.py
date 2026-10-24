import cv2
import numpy as np
import pytest

from harness.preprocess import enhance, prepare


def _board(tilted: bool) -> bytes:
    img = np.full((600, 800, 3), 40, np.uint8)
    pts = np.array([[120, 90], [690, 60], [720, 520], [90, 540]] if tilted
                   else [[100, 100], [700, 100], [700, 500], [100, 500]], np.int32)
    cv2.fillPoly(img, [pts], (235, 235, 235))
    cv2.putText(img, "RAG revision", (200, 300), cv2.FONT_HERSHEY_SIMPLEX, 2, (20, 20, 20), 4)
    return cv2.imencode(".jpg", img)[1].tobytes()


def _decode(b):
    return cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)


def test_enhance_warps_board():
    out, warped = enhance(_board(tilted=True))
    img = _decode(out)
    assert warped and img is not None and img.std() > 5
    assert img.shape[1] < 800 and img.shape[0] < 600


def test_enhance_without_board_keeps_size():
    flat = cv2.imencode(".jpg", np.full((600, 800, 3), 128, np.uint8))[1].tobytes()
    out, warped = enhance(flat)
    assert not warped and _decode(out).shape == (600, 800, 3)


def test_prepare_raw_is_identity():
    b = _board(False)
    assert prepare(b, "raw") == (b, {})


def test_prepare_unknown_variant():
    with pytest.raises(ValueError):
        prepare(b"", "sharpen")
