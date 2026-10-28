"""Auto head-and-shoulders mask for Bust mode (starting selection the user can edit).

Uses a frontal-face cascade when it fires, otherwise skin-tone + portrait-shape
heuristics (numpy / scipy / scikit-image only — no OpenCV dependency). The result
is a Select-mode payload: a mask PNG plus an outline path. Always a starting guess,
never a finished cut — the tip text says so.
"""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.measure import find_contours

from . import selectmask

WORK = 384
TIP = (
    "Auto head and shoulders is a starting mask — edit it with Trace, Add, or Subtract, "
    "then press Make it from my selection."
)
TIPS = {
    "face": TIP,
    "skin": TIP + " This follows colour and the portrait shape, not a found face. Edit the outline if the cut is wrong.",
    "prior": TIP + " No face was found, so this is a centred head-and-shoulders shape. Edit it before you build.",
}


def _resize_work(im: Image.Image):
    W, H = im.size
    s = WORK / max(W, H)
    w, h = max(4, int(round(W * min(1, s)))), max(4, int(round(H * min(1, s))))
    small = im.convert("RGB").resize((w, h), Image.BILINEAR)
    return small, np.asarray(small, np.uint8), w, h


def _try_face(gray: np.ndarray):
    """Return (r, c, width, height) in gray coords, or None. Cascade is best-effort."""
    try:
        from skimage.data import lbp_frontal_face_cascade_filename
        from skimage.feature import Cascade
        det = Cascade(lbp_frontal_face_cascade_filename())
        side = max(gray.shape)
        mn = max(24, side // 12)
        mx = max(mn + 8, int(side * 0.85))
        hits = det.detect_multi_scale(
            img=gray, scale_factor=1.2, step_ratio=1.0, min_size=(mn, mn), max_size=(mx, mx)
        )
    except Exception:
        return None
    if not hits:
        return None
    # Prefer a detection in the upper half (portrait faces); otherwise largest.
    scored = []
    for h in hits:
        r, c, ww, hh = int(h["r"]), int(h["c"]), int(h["width"]), int(h["height"])
        cy = r + hh / 2
        upper = 1.0 if cy < gray.shape[0] * 0.55 else 0.4
        scored.append((upper * ww * hh, r, c, ww, hh))
    scored.sort(reverse=True)
    return scored[0][1:]


def _skin_mask(rgb: np.ndarray) -> np.ndarray:
    """Loose YCbCr skin band — good enough to seed a portrait blob."""
    r = rgb[..., 0].astype(np.float32)
    g = rgb[..., 1].astype(np.float32)
    b = rgb[..., 2].astype(np.float32)
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
    skin = (y > 40) & (y < 240) & (cb > 77) & (cb < 135) & (cr > 125) & (cr < 180)
    # Drop near-white / near-black backgrounds that sneak in
    skin &= (r + g + b) > 80
    skin &= (r + g + b) < 720
    skin = ndimage.binary_opening(skin, iterations=1)
    skin = ndimage.binary_closing(skin, iterations=2)
    return skin


def _largest_blob(mask: np.ndarray) -> np.ndarray:
    lbl, n = ndimage.label(mask)
    if n == 0:
        return mask
    sizes = ndimage.sum(mask, lbl, range(1, n + 1))
    keep = int(np.argmax(sizes)) + 1
    return lbl == keep


def _ellipse(h, w, cy, cx, ry, rx) -> np.ndarray:
    yy, xx = np.ogrid[:h, :w]
    return ((yy - cy) / max(ry, 1)) ** 2 + ((xx - cx) / max(rx, 1)) ** 2 <= 1.0


def _shoulders(h, w, chin_y, cx, half_w, bottom_y) -> np.ndarray:
    """Trapezoid flare from the chin down to the bust cut line."""
    yy, xx = np.ogrid[:h, :w]
    t = np.clip((yy - chin_y) / max(1.0, bottom_y - chin_y), 0, 1)
    half = half_w * (1.0 + 0.85 * t)          # widen toward the base
    band = (yy >= chin_y) & (yy <= bottom_y) & (np.abs(xx - cx) <= half)
    return band


def _from_face(h, w, face) -> np.ndarray:
    r, c, fw, fh = face
    cx = c + fw / 2
    cy = r + fh / 2
    # Slightly taller than the detector box so hair/forehead stay in
    rx, ry = fw * 0.62, fh * 0.72
    head = _ellipse(h, w, cy, cx, ry, rx)
    chin = cy + ry * 0.85
    bottom = min(h - 1, chin + max(fh * 1.55, h * 0.38))
    shoulders = _shoulders(h, w, chin, cx, fw * 0.95, bottom)
    # Soft neck bridge
    neck = _ellipse(h, w, chin + fh * 0.15, cx, fh * 0.35, fw * 0.45)
    m = head | shoulders | neck
    m = ndimage.binary_closing(m, iterations=3)
    m = ndimage.binary_dilation(m, iterations=1)
    return _largest_blob(m)


def _from_skin(rgb: np.ndarray) -> np.ndarray | None:
    h, w = rgb.shape[:2]
    skin = _skin_mask(rgb)
    # Bias: keep upper-body region (drop lower 15%)
    skin[int(h * 0.88):, :] = False
    if skin.mean() < 0.01:
        return None
    blob = _largest_blob(skin)
    if blob.mean() < 0.01:
        return None
    ys, xs = np.nonzero(blob)
    cy, cx = ys.mean(), xs.mean()
    # If the blob is mostly lower half, treat as failed (shirt-only / background)
    if cy > h * 0.65:
        return None
    # Grow a classical bust silhouette around the blob centroid
    face_h = max(h * 0.22, (ys.max() - ys.min()) * 0.55)
    face_w = max(w * 0.18, (xs.max() - xs.min()) * 0.55)
    head = _ellipse(h, w, min(cy, h * 0.35), cx, face_h * 0.7, face_w * 0.65)
    chin = min(cy, h * 0.35) + face_h * 0.55
    bottom = min(h - 1, chin + max(face_h * 1.6, h * 0.4))
    shoulders = _shoulders(h, w, chin, cx, face_w * 1.05, bottom)
    # Union of cleaned blob with the portrait prior around it
    m = blob | head | shoulders
    m = ndimage.binary_closing(m, iterations=3)
    m = ndimage.binary_dilation(m, iterations=2)
    # Trim below the bust cut
    m[int(bottom) + 1:, :] = False
    return _largest_blob(m)


def _portrait_prior(h, w) -> np.ndarray:
    """Last-resort classical bust silhouette centred in the frame."""
    cx, cy = w * 0.5, h * 0.32
    rx, ry = w * 0.22, h * 0.22
    head = _ellipse(h, w, cy, cx, ry, rx)
    chin = cy + ry * 0.9
    bottom = min(h - 1, h * 0.78)
    shoulders = _shoulders(h, w, chin, cx, w * 0.28, bottom)
    neck = _ellipse(h, w, chin + ry * 0.2, cx, ry * 0.35, rx * 0.5)
    m = head | shoulders | neck
    return ndimage.binary_closing(m, iterations=2)


def head_shoulders_mask(im: Image.Image) -> tuple[np.ndarray, str]:
    """Bool mask at working resolution + method tag: face | skin | prior."""
    small, rgb, w, h = _resize_work(im)
    gray = np.asarray(small.convert("L"), np.uint8)
    face = _try_face(gray)
    if face is not None:
        return _from_face(h, w, face), "face"
    skin = _from_skin(rgb)
    if skin is not None and 0.04 <= skin.mean() <= 0.75:
        return skin, "skin"
    return _portrait_prior(h, w), "prior"


def _outline_path(mask: np.ndarray, max_pts: int = 96) -> list[list[float]]:
    h, w = mask.shape
    padded = np.pad(mask.astype(np.float64), 1, mode="constant")
    contours = find_contours(padded, 0.5)
    if not contours:
        # Degenerate: rectangle covering the mask bbox
        ys, xs = np.nonzero(mask)
        if len(ys) == 0:
            return [[0.2, 0.1], [0.8, 0.1], [0.8, 0.85], [0.2, 0.85]]
        return [
            [xs.min() / max(w - 1, 1), ys.min() / max(h - 1, 1)],
            [xs.max() / max(w - 1, 1), ys.min() / max(h - 1, 1)],
            [xs.max() / max(w - 1, 1), ys.max() / max(h - 1, 1)],
            [xs.min() / max(w - 1, 1), ys.max() / max(h - 1, 1)],
        ]
    # Largest contour; find_contours coords are (row, col) in padded space
    c = max(contours, key=len)
    c = c - 1.0  # undo pad
    step = max(1, len(c) // max_pts)
    pts = c[::step]
    out = []
    for row, col in pts:
        out.append([
            round(float(np.clip(col / max(w - 1, 1), 0, 1)), 4),
            round(float(np.clip(row / max(h - 1, 1), 0, 1)), 4),
        ])
    if len(out) >= 3 and out[0] != out[-1]:
        out.append(out[0])
    return out[: max_pts + 1]


def auto_select(im: Image.Image, soft: float = 2.0) -> dict:
    """Select-mode payload for Bust: editable starting mask + outline path + tip."""
    mask, method = head_shoulders_mask(im)
    # Upscale mask to a stable send size (same WORK as selectmode client)
    path = _outline_path(mask)
    # Soften tiny holes
    mask = ndimage.binary_fill_holes(mask)
    b64 = selectmask.encode_mask(mask.astype(np.float32))
    return {
        "v": 1,
        "mask": b64,
        "soft": float(np.clip(soft, 0, 20)),
        "outside": "plain",
        "invert": False,
        "snap": True,
        "paths": [{"op": "new", "pts": path}],
        "auto": True,
        "method": method,
        "tip": TIPS.get(method, TIP),
    }
