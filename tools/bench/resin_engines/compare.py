"""Pixel checks for sliced layers.

DragonFruit maps plate millimetres with the origin at the plate centre onto
pixel coordinates ``0 .. resolution-1``, and flips Y so world +Y is image row 0.
Coverage is the half-open span used by both engines' scan conversion:
``first = ceil(edge - 0.5)``, ``last = ceil(other - 0.5) - 1``.

mslicer's ``--placed`` path scales corner-origin millimetres by
``resolution / plate_mm`` (so the far edge lands on ``resolution``, one past
the last pixel) and writes the low-Y scanline first. UVtools' PNG keeps that
order, so world +Y is the high row, the opposite of DragonFruit.
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np

Rect = tuple[float, float, float, float]


def _span(lo: float, hi: float) -> tuple[int, int]:
    if lo > hi:
        lo, hi = hi, lo
    first = math.ceil(lo - 0.5)
    last = math.ceil(hi - 0.5) - 1
    return int(first), int(last)


def dragonfruit_x(x_mm: float, build_mm: float, pixels: int) -> float:
    return (x_mm + build_mm * 0.5) / build_mm * (pixels - 1)


def dragonfruit_y(y_mm: float, build_mm: float, pixels: int) -> float:
    """Image row. World +Y moves toward row 0."""
    max_px = pixels - 1
    return y_mm * (-max_px / build_mm) + max_px * 0.5


def mslicer_x(x_mm: float, build_mm: float, pixels: int) -> float:
    return (x_mm + build_mm * 0.5) / build_mm * pixels


def mslicer_y(y_mm: float, build_mm: float, pixels: int) -> float:
    """Image row. World +Y moves toward the last row."""
    return (y_mm + build_mm * 0.5) / build_mm * pixels


def rects_for(mesh: str, z_mm: float) -> list[Rect] | None:
    """World-space rectangles that should be solid at this height. None: no analytic."""
    if mesh == "box":
        if 0.0 < z_mm < 12.0:
            return [(-10.0, -8.0, 10.0, 8.0)]
        return []
    if mesh == "asymmetric":
        if 0.0 < z_mm < 4.0:
            return [(-15.0, -10.0, 15.0, 10.0)]
        if 4.0 < z_mm < 12.0:
            return [(5.0, 2.0, 15.0, 10.0)]
        return []
    return None


def _paint(shape: tuple[int, int], spans: Iterable[tuple[int, int, int, int]]) -> np.ndarray:
    mask = np.zeros(shape, dtype=bool)
    height, width = shape
    for x0, x1, y0, y1 in spans:
        if x1 < x0 or y1 < y0:
            continue
        xa, xb = max(0, x0), min(width - 1, x1)
        ya, yb = max(0, y0), min(height - 1, y1)
        if xb >= xa and yb >= ya:
            mask[ya : yb + 1, xa : xb + 1] = True
    return mask


def expected_mask(engine: str, mesh: str, z_mm: float, build_w: float, build_d: float, width: int, height: int) -> np.ndarray | None:
    rects = rects_for(mesh, z_mm)
    if rects is None:
        return None
    spans = []
    for x0, y0, x1, y1 in rects:
        if engine == "dragonfruit":
            px0, px1 = _span(dragonfruit_x(x0, build_w, width), dragonfruit_x(x1, build_w, width))
            py0, py1 = _span(dragonfruit_y(y0, build_d, height), dragonfruit_y(y1, build_d, height))
        elif engine == "mslicer":
            px0, px1 = _span(mslicer_x(x0, build_w, width), mslicer_x(x1, build_w, width))
            py0, py1 = _span(mslicer_y(y0, build_d, height), mslicer_y(y1, build_d, height))
        else:
            raise ValueError(engine)
        spans.append((px0, px1, py0, py1))
    return _paint((height, width), spans)


def solid_mask(image: np.ndarray, threshold: int = 128) -> tuple[np.ndarray, dict]:
    gray = np.asarray(image)
    if gray.ndim == 3:
        gray = gray[..., 0]
    unique = np.unique(gray)
    mask = gray >= threshold
    return mask, {
        "unique_levels": int(unique.size),
        "min": int(gray.min()) if gray.size else 0,
        "max": int(gray.max()) if gray.size else 0,
        "not_binary": bool(np.any((gray != 0) & (gray != 255))),
        "solid_pixels": int(mask.sum()),
    }


def against_expected(actual: np.ndarray, expected: np.ndarray) -> dict:
    xor = np.logical_xor(actual, expected)
    inter = int(np.logical_and(actual, expected).sum())
    union = int(np.logical_or(actual, expected).sum())
    missing = int(np.logical_and(expected, np.logical_not(actual)).sum())
    extra = int(np.logical_and(actual, np.logical_not(expected)).sum())
    return {
        "expected_pixels": int(expected.sum()),
        "actual_pixels": int(actual.sum()),
        "missing": missing,
        "extra": extra,
        "xor": int(xor.sum()),
        "iou": (inter / union) if union else 1.0,
    }


def layer_delta(a: np.ndarray, b: np.ndarray) -> dict:
    """Difference of two masks. Also after flipping B on Y, which is the orientation gap."""
    def one(left: np.ndarray, right: np.ndarray) -> dict:
        inter = int(np.logical_and(left, right).sum())
        union = int(np.logical_or(left, right).sum())
        xor = int(np.logical_xor(left, right).sum())
        return {
            "xor": xor,
            "iou": (inter / union) if union else 1.0,
            "a_pixels": int(left.sum()),
            "b_pixels": int(right.sum()),
        }

    direct = one(a, b)
    flipped = one(a, np.flipud(b))
    return {"stored_order": direct, "b_flipped_in_y": flipped}
