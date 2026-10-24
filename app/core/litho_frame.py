"""Frame / border styles for flat lithophanes (beyond plate-size presets).

plain  — today's solid rim at max_thickness (default; byte-identical when chosen).
double — outer solid rim, a thin bright channel, then an inner solid rim.
ledge  — stepped outer ledge at ~60% max thickness, then full-thickness inner rim
         (a simple picture-frame look; still one solid mesh).

These change the rim thickness pattern only. They are not multi-colour prints.
"""
from __future__ import annotations

import numpy as np

STYLES = ("plain", "double", "ledge")


def check(style: str) -> str:
    key = (style or "plain").strip().lower() or "plain"
    if key not in STYLES:
        raise ValueError("frame_style must be one of " + " | ".join(STYLES))
    return key


def apply_rect(thick: np.ndarray, pad: int, max_thickness: float, style: str) -> np.ndarray:
    """Rewrite the padded rim of a rect heightfield. `thick` already includes `pad` cells."""
    style = check(style)
    if style == "plain" or pad <= 0:
        return thick
    out = thick.copy()
    H, W = out.shape
    yy, xx = np.mgrid[0:H, 0:W]
    dist = np.minimum(np.minimum(yy, H - 1 - yy), np.minimum(xx, W - 1 - xx))
    rim = dist < pad
    if style == "double":
        outer = dist < max(1, pad // 3)
        channel = (dist >= max(1, pad // 3)) & (dist < max(2, (2 * pad) // 3))
        out[rim & outer] = max_thickness
        out[rim & channel] = max(0.6, max_thickness * 0.45)
        out[rim & ~outer & ~channel] = max_thickness
    else:  # ledge
        outer = dist < max(1, pad // 2)
        out[rim & outer] = max(0.6, max_thickness * 0.6)
        out[rim & ~outer] = max_thickness
    return out


def apply_polar(z: np.ndarray, s: np.ndarray, border_mm: float, half: float,
                max_thickness: float, style: str) -> np.ndarray:
    """Adjust rim thicknesses on a polar flat-shape ring mesh."""
    style = check(style)
    if style == "plain" or border_mm <= 0 or len(s) == 0:
        return z
    out = np.asarray(z, float).copy()
    A = (len(out) - 1) // len(s)
    if A < 3:
        return out
    rim_start = max(0.0, 1.0 - border_mm / max(half, 1e-6))
    for i, si in enumerate(s):
        if si < rim_start:
            continue
        t = (si - rim_start) / max(1e-6, 1.0 - rim_start)
        sl = slice(1 + i * A, 1 + (i + 1) * A)
        if style == "double":
            if t < 1 / 3:
                out[sl] = max_thickness
            elif t < 2 / 3:
                out[sl] = max(0.6, max_thickness * 0.45)
            else:
                out[sl] = max_thickness
        else:  # ledge
            out[sl] = max(0.6, max_thickness * 0.6) if t < 0.5 else max_thickness
    return out
