"""Photo collage for a single flat lithophane (distinct from the memory box cube).

Combines 2–6 photos into one image with a simple layout, then the normal lithophane
pipeline builds one printable panel. This is not colour/CMYK stacking and not a
multi-sided box — just a multi-photo layout on one plate.
"""
from __future__ import annotations

import math

from PIL import Image, ImageOps

LAYOUTS = ("hstrip", "vstrip", "grid")
MIN_PHOTOS, MAX_PHOTOS = 2, 6
GAP_PX = 4                     # thin white gap between cells (prints as a thin bright line)
CELL_TARGET = 512              # per-cell long side before compose (keeps memory modest)


def check_layout(layout: str) -> str:
    key = (layout or "").strip().lower()
    if key not in LAYOUTS:
        raise ValueError("collage layout must be one of " + " | ".join(LAYOUTS))
    return key


def check_count(n: int) -> int:
    if not (MIN_PHOTOS <= int(n) <= MAX_PHOTOS):
        raise ValueError(f"collage needs {MIN_PHOTOS}..{MAX_PHOTOS} photos")
    return int(n)


def _fit_cell(im: Image.Image, w: int, h: int) -> Image.Image:
    """Centre-crop cover into a cell; empty = white (thinnest in the lithophane)."""
    return ImageOps.fit(im.convert("RGB"), (w, h), Image.LANCZOS)


def _grid_dims(n: int) -> tuple[int, int]:
    """Columns × rows for n photos (prefer wider than tall)."""
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return cols, rows


def compose(images: list[Image.Image], layout: str = "grid") -> Image.Image:
    """Build one RGB canvas from 2–6 photos. Raises ValueError on bad input."""
    layout = check_layout(layout)
    check_count(len(images))
    ims = [im.convert("RGB") for im in images]

    if layout == "hstrip":
        cols, rows = len(ims), 1
    elif layout == "vstrip":
        cols, rows = 1, len(ims)
    else:
        cols, rows = _grid_dims(len(ims))

    # cell size from the first photo's aspect, capped
    aw, ah = ims[0].size
    scale = CELL_TARGET / max(aw, ah)
    cw = max(32, int(round(aw * scale)))
    ch = max(32, int(round(ah * scale)))

    W = cols * cw + (cols - 1) * GAP_PX
    H = rows * ch + (rows - 1) * GAP_PX
    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    for i, im in enumerate(ims):
        r, c = divmod(i, cols) if layout != "vstrip" else (i, 0)
        if layout == "hstrip":
            r, c = 0, i
        if layout == "grid":
            r, c = divmod(i, cols)
        x = c * (cw + GAP_PX)
        y = r * (ch + GAP_PX)
        canvas.paste(_fit_cell(im, cw, ch), (x, y))
    return canvas


def info(n: int, layout: str) -> dict:
    layout = check_layout(layout)
    n = check_count(n)
    if layout == "hstrip":
        cols, rows = n, 1
    elif layout == "vstrip":
        cols, rows = 1, n
    else:
        cols, rows = _grid_dims(n)
    return dict(collage=True, layout=layout, photos=n, cols=cols, rows=rows,
                note="One flat lithophane from several photos — not a memory box, not colour layers.")
