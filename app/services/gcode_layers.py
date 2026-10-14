"""Layer-by-layer preview data from G-code (the file ZEIM's slicer wrote, or any Marlin/Klipper-style G-code).

Reads moves only (never runs anything): G0/G1 (G2/G3 arcs are drawn as a straight line to their end point), G90/G91,
M82/M83, G92. A move that pushes filament out (E goes up) is an extrusion line; travels and retractions are skipped.
Layers come from PrusaSlicer's ;LAYER_CHANGE / ;Z: comments, or (other slicers) from the Z height of the extrusions.
Line kinds come from ;TYPE: comments when present. Big prints are thinned to a point budget so a phone can draw them.
"""
from __future__ import annotations

import re

MAX_POINTS = 200_000          # total x,y points sent to the browser (thinned evenly across all layers above this)
MAX_LAYERS = 5000

# ;TYPE: names (PrusaSlicer / SuperSlicer / Orca / Cura) -> short kinds the preview colours and names in its legend
KINDS = {
    "external perimeter": "outer", "outer wall": "outer", "wall-outer": "outer", "overhang perimeter": "outer", "overhang wall": "outer",
    "perimeter": "inner", "inner wall": "inner", "wall-inner": "inner",
    "internal infill": "infill", "sparse infill": "infill", "fill": "infill", "infill": "infill",
    "solid infill": "solid", "internal solid infill": "solid", "top solid infill": "solid", "top surface": "solid",
    "bottom surface": "solid", "bridge infill": "solid", "skin": "solid", "ironing": "solid", "gap fill": "solid",
    "support material": "support", "support material interface": "support", "support": "support", "support interface": "support",
    "support-interface": "support", "support transition": "support",
    "skirt/brim": "skirt", "skirt": "skirt", "brim": "skirt", "wipe tower": "skirt", "prime tower": "skirt",
}
KIND_LABELS = {"outer": "Outer wall", "inner": "Inner wall", "infill": "Infill", "solid": "Top / bottom",
               "support": "Supports", "skirt": "Skirt / brim", "other": "Other"}

_WORD = re.compile(r"([XYZEIJF])\s*(-?\d*\.?\d+(?:[eE][-+]?\d+)?)")


class GcodeError(ValueError):
    pass


def _kind(name: str) -> str:
    n = name.strip().lower()
    return KINDS.get(n) or ("support" if "support" in n else "infill" if "infill" in n else
                            "outer" if ("external" in n or "outer" in n) else
                            "inner" if ("perimeter" in n or "wall" in n) else "other")


def parse(text: str, max_points: int = MAX_POINTS) -> dict:
    """-> {"layers": [{"z": mm, "paths": [{"k": kind, "p": [x0, y0, x1, y1, ...]}, ...]}, ...],
           "bounds": [min_x, min_y, max_x, max_y], "kinds": {kind: label}, "points": n, "thinned": bool}"""
    x = y = z = 0.0
    e = 0.0
    abs_xy, abs_e = True, True
    kind = "other"
    layers: list[dict] = []
    cur: dict | None = None              # current layer
    path: dict | None = None             # current polyline in that layer
    pending_z = None                     # ;Z: from a ;LAYER_CHANGE block, applied to the next layer
    layer_marked = False                 # the file uses ;LAYER_CHANGE markers (then Z hops never start a layer)
    mnx = mny = float("inf"); mxx = mxy = float("-inf")
    points = 0

    def new_layer(zv):
        nonlocal cur, path
        cur = {"z": round(zv, 3), "paths": []}
        layers.append(cur); path = None
        if len(layers) > MAX_LAYERS:
            raise GcodeError("This G-code has more layers than the preview can show.")

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line[0] == ";":
            u = line[1:].strip()
            if u.startswith("LAYER_CHANGE"):
                layer_marked = True; pending_z = None
                cur = None; path = None
            elif u.startswith("Z:") and layer_marked:
                try: pending_z = float(u[2:])
                except ValueError: pass
            elif u.startswith("TYPE:"):
                kind = _kind(u[5:]); path = None
            continue
        code = line.split(";", 1)[0].strip().upper()
        if not code:
            continue
        head = code.split(None, 1)[0]
        if head == "G90": abs_xy = True; continue           # Klipper / Marlin: E follows G91, otherwise M82 / M83
        if head == "G91": abs_xy = False; continue
        if head == "M82": abs_e = True; continue
        if head == "M83": abs_e = False; continue
        if head == "G92":
            w = dict(_WORD.findall(code))
            if "E" in w: e = float(w["E"])
            if "X" in w: x = float(w["X"])
            if "Y" in w: y = float(w["Y"])
            if "Z" in w: z = float(w["Z"])
            continue
        if head not in ("G0", "G1", "G00", "G01", "G2", "G3", "G02", "G03"):
            continue
        w = dict(_WORD.findall(code))
        nx = (float(w["X"]) if abs_xy else x + float(w["X"])) if "X" in w else x
        ny = (float(w["Y"]) if abs_xy else y + float(w["Y"])) if "Y" in w else y
        nz = (float(w["Z"]) if abs_xy else z + float(w["Z"])) if "Z" in w else z
        de = 0.0
        if "E" in w:
            ev = float(w["E"])
            ae = abs_e and abs_xy
            de = ev - e if ae else ev
            e = ev if ae else e + ev
        moved = (nx != x or ny != y)
        if de > 1e-6 and moved:
            if cur is None or (not layer_marked and abs(nz - cur["z"]) > 1e-4):
                new_layer(pending_z if (layer_marked and pending_z is not None) else nz)
            if path is None or path["k"] != kind:
                path = {"k": kind, "p": [round(x, 1), round(y, 1)]}; cur["paths"].append(path); points += 1
                mnx = min(mnx, x); mxx = max(mxx, x); mny = min(mny, y); mxy = max(mxy, y)
            path["p"] += [round(nx, 1), round(ny, 1)]; points += 1
            mnx = min(mnx, nx); mxx = max(mxx, nx); mny = min(mny, ny); mxy = max(mxy, ny)
        elif moved or nz != z:
            path = None                   # travel (or Z hop): the next extrusion starts a new line
        x, y, z = nx, ny, nz

    layers = [l for l in layers if l["paths"]]
    if not layers:
        raise GcodeError("This G-code has no printed lines to preview.")
    thinned = points > max_points
    if thinned:
        step = points / max_points
        points = 0
        for l in layers:
            for p in l["paths"]:
                pts = p["p"]; n = len(pts) // 2
                if n > 2:
                    keep = max(2, int(n / step))
                    idx = sorted({round(i * (n - 1) / (keep - 1)) for i in range(keep)})
                    p["p"] = [v for i in idx for v in (pts[2 * i], pts[2 * i + 1])]
                points += len(p["p"]) // 2
    return {"layers": layers, "bounds": [round(mnx, 2), round(mny, 2), round(mxx, 2), round(mxy, 2)],
            "kinds": KIND_LABELS, "points": points, "thinned": thinned}

