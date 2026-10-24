"""Lithophane image tools: grey methods, brightness / contrast / sharpen, and seamless tiling.

Defaults leave the existing map byte-identical (rec601 luma, no tone extras, no tile). thickness_map and the
flat rect path both call prepare_grey() so Expert tone knobs apply to every lithophane shape.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage

GREY_METHODS = ("rec601", "rec709", "average", "lightness", "max")
# brightness / contrast: -1..1 (0 = unchanged). sharpen: 0..2 (0 = off).
BRIGHT_RANGE = (-1.0, 1.0)
CONTRAST_RANGE = (-1.0, 1.0)
SHARPEN_RANGE = (0.0, 2.0)
MM_PER_REPEAT_RANGE = (5.0, 200.0)
DEFAULT_MM_PER_REPEAT = 40.0

# Night-light sleeve: inside diameter the cover slips over (mm). LED / battery only — not for hot mains bulbs.
# Values are starting fits from data/litho/litho-specs.json + common LED tea-light / puck sizes; measure yours.
LIGHT_FITS = {
    "tealight": {"diameter_mm": 38.0, "label": "LED tea-light (~38 mm)",
                 "help": "Common battery LED tea-light. Measure yours; flame candles are not safe in printed sleeves."},
    "puck50": {"diameter_mm": 50.0, "label": "LED puck (~50 mm)",
               "help": "Small USB / battery LED puck. Size the sleeve to the measured puck, not a guess."},
    "puck70": {"diameter_mm": 70.0, "label": "LED puck (~70 mm)",
               "help": "Larger desk LED puck. Prefer low-heat LEDs; leave vents if the puck runs warm."},
    "e12": {"diameter_mm": 16.0, "label": "E12 LED candelabra (~16 mm)",
            "help": "Fits over a small E12 LED bulb/socket assembly (~12.6 mm opening + clearance). Use a certified socket for mains; print is not an electrical part."},
}

# Standard photo-plate widths (mm, long side). UI only sets width_mm; height follows the photo.
FRAME_SIZES = {
    "4x6": {"width_mm": 152.4, "label": "4 × 6 in"},
    "5x7": {"width_mm": 177.8, "label": "5 × 7 in"},
    "8x10": {"width_mm": 254.0, "label": "8 × 10 in"},
    "a6": {"width_mm": 148.0, "label": "A6 postcard"},
    "a5": {"width_mm": 210.0, "label": "A5"},
}


def luma(rgb: np.ndarray, method: str = "rec601") -> np.ndarray:
    """rgb float array (…,3) 0..255 → grey 0..1."""
    method = (method or "rec601").strip().lower()
    if method not in GREY_METHODS:
        raise ValueError("grey_method must be one of " + " | ".join(GREY_METHODS))
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    if method == "rec601":
        y = 0.299 * r + 0.587 * g + 0.114 * b
    elif method == "rec709":
        y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    elif method == "average":
        y = (r + g + b) / 3.0
    elif method == "lightness":
        y = (np.maximum(np.maximum(r, g), b) + np.minimum(np.minimum(r, g), b)) / 2.0
    else:  # max
        y = np.maximum(np.maximum(r, g), b)
    return y / 255.0


def check_tone(grey_method="rec601", brightness=0.0, contrast=0.0, sharpen=0.0):
    """Validate Expert tone knobs. Returns a clean dict; identity values are kept (caller decides what to store)."""
    method = (grey_method or "rec601").strip().lower()
    if method not in GREY_METHODS:
        raise ValueError("grey_method must be one of " + " | ".join(GREY_METHODS))
    try:
        br, co, sh = float(brightness), float(contrast), float(sharpen)
    except (TypeError, ValueError):
        raise ValueError("brightness, contrast and sharpen must be numbers")
    for name, v, (lo, hi) in (("brightness", br, BRIGHT_RANGE), ("contrast", co, CONTRAST_RANGE),
                              ("sharpen", sh, SHARPEN_RANGE)):
        if not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f"{name} must be {lo:g}..{hi:g}")
    return {"grey_method": method, "brightness": br, "contrast": co, "sharpen": sh}


def check_tile(tile, mm_per_repeat=DEFAULT_MM_PER_REPEAT):
    """tile on → (True, mm_per_repeat); off → (False, None)."""
    on = bool(tile) if not isinstance(tile, str) else tile.strip().lower() in ("1", "true", "yes", "on")
    if not on:
        return False, None
    try:
        mm = float(mm_per_repeat)
    except (TypeError, ValueError):
        raise ValueError("mm_per_repeat must be a number")
    lo, hi = MM_PER_REPEAT_RANGE
    if not math.isfinite(mm) or not lo <= mm <= hi:
        raise ValueError(f"mm_per_repeat must be {lo:g}..{hi:g}")
    return True, mm


def adjust(g: np.ndarray, brightness=0.0, contrast=0.0, sharpen=0.0) -> np.ndarray:
    """Manual tone after auto-contrast / gamma. All-zero is a no-op."""
    g = np.asarray(g, float)
    if sharpen:
        blur = ndimage.gaussian_filter(g, 1.0)
        g = g + float(sharpen) * (g - blur)
    if contrast:
        g = (g - 0.5) * (1.0 + float(contrast)) + 0.5
    if brightness:
        g = g + float(brightness)
    return np.clip(g, 0, 1)


def prepare_grey(rgb: np.ndarray, grey_method="rec601", auto_contrast=True, gamma=1.0, smooth=0.8,
                 brightness=0.0, contrast=0.0, sharpen=0.0) -> np.ndarray:
    """Full grey pipeline used by every lithophane thickness map."""
    from .geometry import _tone
    g = _tone(luma(rgb, grey_method), auto_contrast, gamma, smooth)
    return adjust(g, brightness, contrast, sharpen)


def place_tiled(im: Image.Image, nx: int, ny: int, mm_per_repeat: float, span_mm: float,
                place=None, wrap=False) -> Image.Image:
    """Tile the photo across an nx×ny map. mm_per_repeat is the physical width of one repeat; span_mm is the
    map's physical width (plate width, circumference, or panel arc). wrap=True: tile only around (X); Y fills
    the height once (cylinder / globe). Flat: tile both axes, aspect kept. Empty = white (thinnest)."""
    nx, ny = int(nx), int(ny)
    span = max(float(span_mm), 1e-6)
    tw = max(4, int(round(nx * float(mm_per_repeat) / span)))
    im = im.convert("RGB")
    if wrap:
        # one tile height = map height; width = tw; then repeat around
        th = ny
        small = ImageOps.fit(im, (tw, th), Image.LANCZOS)
        arr = np.asarray(small)
        reps = int(math.ceil(nx / tw)) + 1
        row = np.tile(arr, (1, reps, 1))[:, :nx]
    else:
        th = max(4, int(round(tw * im.height / max(1, im.width))))
        small = im.resize((tw, th), Image.LANCZOS)
        arr = np.asarray(small)
        rx = int(math.ceil(nx / tw)) + 1
        ry = int(math.ceil(ny / th)) + 1
        row = np.tile(arr, (ry, rx, 1))[:ny, :nx]
    if place:
        if place.get("rotation"):
            # rotate the source tile only (re-tile) would be heavy; roll/offset is enough for seam align
            pass
        if place.get("x"):
            row = np.roll(row, int(round(float(place["x"]) * nx)), axis=1)
        if place.get("y") and not wrap:
            row = np.roll(row, int(round(float(place["y"]) * ny)), axis=0)
    return Image.fromarray(row)


def light_fit(fit_id: str) -> dict:
    """Return a LIGHT_FITS entry or raise ValueError."""
    key = (fit_id or "").strip().lower()
    if key not in LIGHT_FITS:
        raise ValueError("light_fit must be one of " + " | ".join(LIGHT_FITS) + " (or empty for custom)")
    return dict(LIGHT_FITS[key], id=key)


def frame_size(size_id: str) -> dict:
    key = (size_id or "").strip().lower()
    if key not in FRAME_SIZES:
        raise ValueError("frame_size must be one of " + " | ".join(FRAME_SIZES))
    return dict(FRAME_SIZES[key], id=key)
