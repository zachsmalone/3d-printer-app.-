"""Backlit lithophane preview ("Light on"): a PREVIEW ESTIMATE of how bright each spot glows with a light behind it.

Beer-Lambert style: I = exp(-k * t), t = wall thickness in mm. Thin = bright, thick = dark.
k ~ 0.9 /mm is a rough figure for white PLA (real filament varies a lot). static/lithlight.js is the browser twin
of these functions and must stay in step (tests/test_litho_light.py checks both).

Thickness per vertex:
* flat shapes (rect / heart / circle / star / square): height above the back face, t = z - z_min.
* nightlight / cup: radial wall, t = r - r_inner (r measured from the upright Z axis).
* globe: spherical wall, t = |p - c| - r_inner (c = sphere centre).
"""
from __future__ import annotations

import numpy as np

K_PER_MM = 0.9
LIGHTS = {"warm": (1.0, 0.72, 0.42), "cool": (0.74, 0.85, 1.0), "white": (1.0, 1.0, 1.0)}


def brightness(t, k: float = K_PER_MM):
    t = np.clip(np.asarray(t, float), 0.0, None)
    return np.exp(-k * t)


def display(t, k: float = K_PER_MM, gamma: float = 0.6):
    """0..1 shade for the screen: relative to the thinnest wall in the model, gamma-lifted so mid-tones read."""
    i = brightness(t, k)
    top = float(i.max()) if i.size else 1.0
    return np.clip(i / (top or 1.0), 0, 1) ** gamma


def wall_thickness(v, shape: str = "rect"):
    v = np.asarray(v, float)
    lo, hi = v.min(0), v.max(0)
    if shape in ("nightlight", "cup"):
        c = (lo + hi) / 2
        r = np.hypot(v[:, 0] - c[0], v[:, 1] - c[1])
        mid = (v[:, 2] > lo[2] + 0.2 * (hi[2] - lo[2])) & (v[:, 2] < lo[2] + 0.8 * (hi[2] - lo[2]))
        r_in = r[mid].min() if mid.any() else r.min()
        return np.clip(r - r_in, 0, None)
    if shape == "globe":
        R = (hi[0] - lo[0]) / 2
        c = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, hi[2] - R])
        d = np.linalg.norm(v - c, axis=1)
        up = v[:, 2] > c[2]
        r_in = d[up].min() if up.any() else d.min()
        return np.clip(d - r_in, 0, None)
    return v[:, 2] - lo[2]
