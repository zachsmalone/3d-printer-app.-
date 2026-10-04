"""Cheap numpy thumbnails of the *result* (no GPU / matplotlib needed)."""
from __future__ import annotations

import numpy as np
from PIL import Image


def _to_img(rgb: np.ndarray, max_w=260) -> np.ndarray:
    im = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    if im.width > max_w:
        im = im.resize((max_w, max(1, round(im.height * max_w / im.width))), Image.LANCZOS)
    return np.asarray(im)


def hillshade(h: np.ndarray, pitch: float, az=315, alt=45) -> np.ndarray:
    gy, gx = np.gradient(h, pitch)
    gy = -gy  # rows grow downward
    slope = np.pi / 2 - np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    azr, altr = np.deg2rad(360 - az + 90), np.deg2rad(alt)
    sh = np.sin(altr) * np.sin(slope) + np.cos(altr) * np.cos(slope) * np.cos(azr - aspect)
    return np.clip(sh, 0, 1)


def lithophane_backlit(thick: np.ndarray, tmin: float, tmax: float) -> np.ndarray:
    k = 0.9
    t = np.exp(-k * thick)
    lo, hi = np.exp(-k * tmax), np.exp(-k * tmin)
    i = np.clip((t - lo) / (hi - lo + 1e-9), 0, 1) ** 0.9
    warm = np.array([255, 238, 205.0])
    return _to_img(12 + i[..., None] * (warm - 12))


def relief_shaded(h: np.ndarray, pitch: float) -> np.ndarray:
    s = hillshade(h, pitch)
    hn = (h - h.min()) / (np.ptp(h) + 1e-9)
    base = np.array([120, 150, 190.0]) * (0.55 + 0.45 * hn[..., None])
    return _to_img(base * (0.35 + 0.8 * s[..., None]))


def popart_shaded(lab: np.ndarray, pal: np.ndarray, layer_mm: float, pitch: float) -> np.ndarray:
    rgb = pal[lab]
    s = hillshade(lab * layer_mm, pitch)
    return _to_img(rgb * (0.65 + 0.5 * (s[..., None] - 0.5) + 0.2))
