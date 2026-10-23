"""CAD Text & Emboss (original ZEIM code). Raised or cut-in text on a tapped surface point, or a standalone
text plate. Glyph outlines: matplotlib TextPath with the DejaVu fonts matplotlib ships (Bitstream Vera /
DejaVu licence, permissive). Booleans: manifold3d (Apache-2.0). The result is one closed manifold mesh.
Print warnings are advisory only (returned in the report, never raised)."""
from __future__ import annotations

import math

import numpy as np
import trimesh

from .meshedit import OpError, text_polygon
from . import cadops as C

FONTS = ("sans", "sans-bold", "serif", "mono")
KEYS = {"text", "font", "size", "depth", "style", "target", "point", "normal", "rotation",
        "nozzle", "plate_thickness", "margin", "replace"}


def _frame(n):
    n = n / np.linalg.norm(n)
    up = np.array([0.0, 0, 1])
    u = np.cross(up, n) if abs(n @ up) < 0.9 else np.array([1.0, 0, 0])
    u = u - n * (u @ n); u /= np.linalg.norm(u)
    return u, np.cross(n, u), n


def _solid(poly, z0, z1, origin, u, v, n, rot):
    a = math.radians(rot); c, s = math.cos(a), math.sin(a)
    parts = [g for g in (poly.geoms if hasattr(poly, "geoms") else [poly]) if g.area > 1e-6]
    m = trimesh.util.concatenate([trimesh.creation.extrude_polygon(g, z1 - z0) for g in parts])
    P = m.vertices; x, y, z = P[:, 0], P[:, 1], P[:, 2] + z0
    xr, yr = x * c - y * s, x * s + y * c
    w = origin + np.outer(xr, u) + np.outer(yr, v) + np.outer(z, n)
    return C._new(w, m.faces)   # u,v,n right-handed -> winding kept


def warnings_for(poly, depth, nozzle):
    out = []
    lost = 1 - poly.buffer(-nozzle * 0.5).area / max(poly.area, 1e-9)
    if lost > 0.5:
        out.append(f"Some letter strokes are thinner than about one {nozzle:g} mm nozzle width and may not print. "
                   "Try a bigger size or a bold font.")
    if depth < 2 * 0.2:
        out.append(f"Depth {depth:g} mm is only a layer or two; the text may barely show. 0.6 mm or more reads better.")
    return out


def op_cad_text(m, p):
    txt = str(p.get("text", "")).strip()
    if not txt or len(txt) > 60:
        raise OpError("Text must be 1–60 characters.")
    if any(ord(ch) < 32 for ch in txt):
        raise OpError("Text contains control characters.")
    font = p.get("font", "sans")
    if font not in FONTS:
        raise OpError("font must be one of " + ", ".join(FONTS))
    size = C._num(p, "size", 8, 1, 300); depth = C._num(p, "depth", 1, 0.1, 50)
    rot = C._num(p, "rotation", 0, -360, 360); nozzle = C._num(p, "nozzle", 0.4, 0.1, 2)
    style, target = p.get("style", "raised"), p.get("target", "surface")
    if style not in ("raised", "cut") or target not in ("surface", "plate"):
        raise OpError("style must be raised|cut and target surface|plate.")
    poly = text_polygon(txt, font, size)
    warns = warnings_for(poly, depth, nozzle)
    if p.get("replace"):          # first step of a new CAD project (replayed on an empty start)
        m = trimesh.Trimesh()
    has = len(m.faces) > 0
    if target == "plate":
        th = C._num(p, "plate_thickness", 2, 0.4, 50); mg = C._num(p, "margin", 3, 0, 100)
        if style == "cut" and depth >= th:
            raise OpError("Cut depth must be less than the plate thickness.")
        x0, y0, x1, y1 = poly.buffer(mg, join_style=1).bounds   # text bounds before rotation (plate turns with it)
        from shapely.geometry import box
        plate = box(x0, y0, x1, y1)
        o = np.zeros(3); u, v, n = np.eye(3)
        if has:   # beside the model, on the bed
            lo, hi = m.bounds
            o = np.array([hi[0] + 5 + (x1 - x0) / 2, (lo[1] + hi[1]) / 2, lo[2]])
        base = C._to_manifold(_solid(plate, 0, th, o, u, v, n, rot))
        top = o + n * th
        tool = C._to_manifold(_solid(poly, -0.3, depth, top, u, v, n, rot) if style == "raised"
                              else _solid(poly, -depth, 0.3, top, u, v, n, rot))
        res = C._from_manifold(base + tool if style == "raised" else base - tool)
        out = C._join_sep(m, res, "Move the model away from the plate.") if has else res
        what = f"Text plate '{txt}' ({'raised' if style == 'raised' else 'cut'} {depth:g} mm)"
    else:
        if not has:
            raise OpError("Tap a spot on a model first, or choose Text plate.")
        pt, nrm = C._vec(p, "point"), C._vec(p, "normal", (0, 0, 1), 10)
        if np.linalg.norm(nrm) < 1e-9:
            raise OpError("normal can't be zero.")
        u, v, n = _frame(nrm)
        sink = 0.3 + 0.15 * size          # bites into gently curved surfaces so raised text doesn't float
        tool = _solid(poly, -sink, depth, pt, u, v, n, rot) if style == "raised" else _solid(poly, -depth, sink, pt, u, v, n, rot)
        a, b = C._to_manifold(m), C._to_manifold(tool)
        r = a + b if style == "raised" else a - b
        if r.is_empty():
            raise OpError("The result is empty.")
        out = C._from_manifold(r)
        dv = out.volume - m.volume
        if style == "cut" and abs(dv) < 1e-3 * poly.area * depth:
            raise OpError("Nothing was cut: tap a spot on the model's surface.")
        if style == "raised" and len(C.bodies(out)) > len(C.bodies(m)):
            warns.append("Part of the text doesn't touch the model (floating). Move it onto a flatter spot or lower the size.")
        what = f"{'Raised' if style == 'raised' else 'Cut-in'} text '{txt}' {depth:g} mm"
    mm = out.copy(); mm.merge_vertices()
    if not mm.is_watertight:
        raise OpError("The text didn't make a clean closed solid here. Try another spot, size or font.")
    return out, {"message": what + ". It's a step in History (Undo works).", "warnings": warns}


def label(p):
    t = str(p.get("text", ""))[:20]
    return f"Text '{t}' ({p.get('style', 'raised')}{', plate' if p.get('target') == 'plate' else ''})"
