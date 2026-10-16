"""Image variants fed to the engines: raw, and enhanced (white balance, CLAHE, board warp)."""

import cv2
import numpy as np

MIN_BOARD_AREA = 0.20
# A "board" covering nearly the whole frame is the frame itself; warping it changes nothing.
MAX_BOARD_AREA = 0.95


def _gray_world(img: np.ndarray) -> np.ndarray:
    means = img.reshape(-1, 3).mean(axis=0)
    scale = means.mean() / np.maximum(means, 1e-6)
    return np.clip(img * scale, 0, 255).astype(np.uint8)


def _clahe(img: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def _order_corners(pts: np.ndarray) -> np.ndarray:
    s, d = pts.sum(axis=1), np.diff(pts, axis=1).ravel()
    return np.array([pts[s.argmin()], pts[d.argmin()], pts[s.argmax()], pts[d.argmax()]], np.float32)


def _find_board(img: np.ndarray) -> np.ndarray | None:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    quad = cv2.approxPolyDP(largest, 0.02 * cv2.arcLength(largest, True), True)
    share = cv2.contourArea(quad) / (img.shape[0] * img.shape[1])
    if len(quad) != 4 or not MIN_BOARD_AREA <= share <= MAX_BOARD_AREA:
        return None
    return _order_corners(quad.reshape(4, 2).astype(np.float32))


def _warp(img: np.ndarray, corners: np.ndarray) -> np.ndarray:
    tl, tr, br, bl = corners
    width = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    height = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], np.float32)
    return cv2.warpPerspective(img, cv2.getPerspectiveTransform(corners, target), (width, height))


def enhance(image: bytes) -> tuple[bytes, bool]:
    img = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
    img = _clahe(_gray_world(img))
    corners = _find_board(img)
    if corners is not None:
        img = _warp(img, corners)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise ValueError("JPEG encode failed")
    return buf.tobytes(), corners is not None


def prepare(image: bytes, variant: str) -> tuple[bytes, dict]:
    if variant == "raw":
        return image, {}
    if variant == "enhanced":
        out, warped = enhance(image)
        return out, {"warped": warped}
    raise ValueError(f"unknown variant: {variant}")
