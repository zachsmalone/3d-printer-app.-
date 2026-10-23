"""2D footprint bin-packing for the plate editor (ZEIM's own code, no third-party packer).

Each item is the axis-aligned box of its convex-hull footprint (XY), optionally turned 90 deg. Items are packed with a
"max-rects" free-space list (best short-side fit), largest first, with `gap` mm between parts and from the bed edge
kept by inflating every rectangle by `gap`. Anything that doesn't fit spills onto plate 2, 3... (never refused);
the caller warns and can offer to split those onto another plate.
"""
from __future__ import annotations

import numpy as np

EPS = 1e-6


def footprint(points_xy) -> tuple[float, float, float, float]:
    """(min_x, min_y, width, depth) of the convex hull of the XY points (== their box for axis-aligned packing)."""
    p = np.asarray(points_xy, float).reshape(-1, 2)
    try:
        from scipy.spatial import ConvexHull
        if len(p) >= 3:
            p = p[ConvexHull(p).vertices]
    except Exception:
        pass
    lo, hi = p.min(axis=0), p.max(axis=0)
    return float(lo[0]), float(lo[1]), float(hi[0] - lo[0]), float(hi[1] - lo[1])


class _Bin:
    def __init__(self, w, h):
        self.free = [(0.0, 0.0, w, h)]

    def find(self, w, h):
        best = None
        for fx, fy, fw, fh in self.free:
            if w <= fw + EPS and h <= fh + EPS:
                score = (min(fw - w, fh - h), max(fw - w, fh - h), fy, fx)
                if best is None or score < best[0]:
                    best = (score, fx, fy)
        return best

    def place(self, x, y, w, h):
        out = []
        for f in self.free:
            fx, fy, fw, fh = f
            if x >= fx + fw - EPS or x + w <= fx + EPS or y >= fy + fh - EPS or y + h <= fy + EPS:
                out.append(f); continue
            if x > fx + EPS: out.append((fx, fy, x - fx, fh))
            if x + w < fx + fw - EPS: out.append((x + w, fy, fx + fw - x - w, fh))
            if y > fy + EPS: out.append((fx, fy, fw, y - fy))
            if y + h < fy + fh - EPS: out.append((fx, y + h, fw, fy + fh - y - h))
        # drop rectangles contained in another
        keep = []
        for i, a in enumerate(out):
            if not any(j != i and a[0] >= b[0] - EPS and a[1] >= b[1] - EPS and a[0] + a[2] <= b[0] + b[2] + EPS
                       and a[1] + a[3] <= b[1] + b[3] + EPS and (b != a or j < i) for j, b in enumerate(out)):
                keep.append(a)
        self.free = keep


def pack(sizes, bed, gap=5.0, rotate=True, max_plates=20) -> dict:
    """sizes: [(w, d)] footprints in mm. bed: (bx, by). Returns
    {"items": [{"plate", "x", "y", "rot"}]  (x, y = min corner, bed centred on (0, 0); rot = 0 or 90),
     "plates": n, "fits": all on plate 0, "overflow": [indices not on plate 0], "too_big": [indices bigger than the bed]}"""
    bx, by = float(bed[0]), float(bed[1])
    g = max(0.0, float(gap))
    W, H = bx + g, by + g                      # every rect inflated by gap on its +x/+y side; bed by gap too
    order = sorted(range(len(sizes)), key=lambda i: (-(sizes[i][0] * sizes[i][1]), -max(sizes[i]), i))
    bins: list[_Bin] = []
    items: list = [None] * len(sizes)
    too_big = []
    for i in order:
        w, d = float(sizes[i][0]), float(sizes[i][1])
        opts = [(w, d, 0)] + ([(d, w, 90)] if rotate and abs(w - d) > EPS else [])
        if not any(a <= bx + EPS and b <= by + EPS for a, b, _ in opts):
            too_big.append(i)
        def fit_in(b):
            best = None
            for a, c, r in opts:
                f = b.find(a + g, c + g)
                if f and (best is None or f[0] < best[0]):
                    best = (f[0], f[1], f[2], a, c, r)
            return best
        placed = False
        for k, b in enumerate(bins):
            best = fit_in(b)
            if best:
                _, x, y, a, c, r = best
                b.place(x, y, a + g, c + g)
                items[i] = {"plate": k, "x": x, "y": y, "w": a, "d": c, "rot": r}
                placed = True
                break
        if not placed:
            b = _Bin(W, H); bins.append(b)
            best = fit_in(b) if len(bins) <= max_plates else None
            if best:
                _, x, y, a, c, r = best
                b.place(x, y, a + g, c + g)
                items[i] = {"plate": len(bins) - 1, "x": x, "y": y, "w": a, "d": c, "rot": r}
            else:                              # bigger than the bed (or too many plates): its own plate; the bed check warns
                items[i] = {"plate": len(bins) - 1, "x": 0.0, "y": 0.0, "w": w, "d": d, "rot": 0}
                b.free = []
    # centre each plate's used area on the bed (keeps the gap from the edges balanced)
    for k in range(len(bins)):
        on = [it for it in items if it["plate"] == k]
        if not on:
            continue
        ux = max(it["x"] + it["w"] for it in on); uy = max(it["y"] + it["d"] for it in on)
        ox = max(-bx / 2, -ux / 2) if ux <= bx else -bx / 2
        oy = max(-by / 2, -uy / 2) if uy <= by else -by / 2
        for it in on:
            it["x"] = round(it["x"] + ox, 3); it["y"] = round(it["y"] + oy, 3)
    overflow = sorted(i for i, it in enumerate(items) if it["plate"] > 0 or i in too_big)
    return {"items": items, "plates": max([it["plate"] for it in items], default=0) + 1,
            "fits": not overflow, "overflow": overflow, "too_big": sorted(too_big), "gap_mm": g, "bed_mm": [bx, by]}
