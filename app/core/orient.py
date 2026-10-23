"""Smart orient ('Lay flat', 'Best position') and multi-part plate arrangement."""
from __future__ import annotations

import math

import numpy as np
import trimesh

OVERHANG_DEG = 45.0          # faces tilted more than this past vertical need support (the usual FDM rule of thumb)
BED_EPS = 0.2                # mm: faces this close to the bed rest on it and need no support


def _rot_to_down(normal) -> np.ndarray:
    return trimesh.geometry.align_vectors(np.asarray(normal, float), np.array([0.0, 0.0, -1.0]))


def _apply(m: trimesh.Trimesh, T) -> trimesh.Trimesh:
    out = m.copy()
    out.apply_transform(T)
    lo, hi = out.bounds
    out.apply_translation([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])      # centred on the bed, resting on it
    return out


def overhang(m: trimesh.Trimesh) -> dict:
    """Overhang area (mm^2) of downward faces steeper than 45 deg that are not on the bed, and a support-volume proxy
    (area x height above the bed, mm^3)."""
    n = m.face_normals
    a = m.area_faces
    zmin = m.bounds[0][2]
    cz = m.triangles_center[:, 2] - zmin
    lim = -math.cos(math.radians(90 - OVERHANG_DEG))           # nz below -0.707
    down = (n[:, 2] < lim) & (cz > BED_EPS)
    proj = a * np.clip(-n[:, 2], 0, 1)
    on_bed = (n[:, 2] < -0.999) & (cz <= BED_EPS)
    return {"overhang_mm2": float(a[down].sum()), "support_mm3": float((proj[down] * cz[down]).sum()),
            "bed_contact_mm2": float(a[on_bed].sum()), "height_mm": float(m.extents[2])}


def _candidates(m: trimesh.Trimesh, k: int = 24) -> list[np.ndarray]:
    hull = m.convex_hull
    out = []
    try:
        fa = hull.facets_area
        order = np.argsort(fa)[::-1][:k]
        out = [hull.facets_normal[i] for i in order]
    except Exception:
        pass
    if len(out) < k:                                            # hull faces too (meshes without coplanar facets)
        order = np.argsort(hull.area_faces)[::-1][: k - len(out)]
        out += [hull.face_normals[i] for i in order]
    out += [np.array(v, float) for v in ((0, 0, -1), (0, 0, 1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0))]
    uniq = []
    for v in out:
        v = v / (np.linalg.norm(v) or 1)
        if not any(np.dot(v, u) > 0.999 for u in uniq):
            uniq.append(v)
    return uniq


def lay_flat(m: trimesh.Trimesh) -> tuple[trimesh.Trimesh, dict]:
    """Put the largest flat face (largest coplanar facet of the convex hull) down on the bed."""
    hull = m.convex_hull
    try:
        if len(hull.facets):
            i = int(np.argmax(hull.facets_area))
            normal, area = hull.facets_normal[i], float(hull.facets_area[i])
        else:
            raise ValueError
    except Exception:
        i = int(np.argmax(hull.area_faces))
        normal, area = hull.face_normals[i], float(hull.area_faces[i])
    out = _apply(m, _rot_to_down(normal))
    return out, {"message": f"Laid flat on its largest flat face ({area:.0f} mm²)", "face_mm2": round(area, 1), **_r(overhang(out))}


def score(o: dict, size: float) -> float:
    return o["overhang_mm2"] + o["support_mm3"] / max(size, 1.0) * 0.5 - 0.05 * o["bed_contact_mm2"]


def best_position(m: trimesh.Trimesh) -> tuple[trimesh.Trimesh, dict]:
    """Try resting on each big hull facet (plus the six axis directions); keep the one with the least overhang area and support."""
    size = float(max(m.extents))
    before = overhang(_apply(m, np.eye(4)))
    best = None
    for nrm in _candidates(m):
        cand = _apply(m, _rot_to_down(nrm))
        o = overhang(cand)
        s = score(o, size)
        if best is None or s < best[0] - 1e-6:
            best = (s, cand, o)
    if score(before, size) <= best[0] + 1e-6:                  # already as good as it gets: just drop / centre it
        out, o = _apply(m, np.eye(4)), before
    else:
        _, out, o = best
    return out, {"message": f"Best position: overhang {before['overhang_mm2']:.0f} → {o['overhang_mm2']:.0f} mm²",
                 "before": _r(before), **_r(o)}


def _r(o: dict) -> dict:
    return {k: round(v, 1) for k, v in o.items()}


# ---------------- multi-part plate ----------------
def arrange(meshes: list[trimesh.Trimesh], bed=(220.0, 220.0), gap: float = 5.0, height: float | None = None):
    """Shelf-pack parts on one plate (each dropped to the bed, `gap` mm apart), centre the layout on the bed origin.
    -> (combined mesh, report with fits / footprint / per-part positions)."""
    bx, by = float(bed[0]), float(bed[1])
    parts = []
    for m in meshes:
        p = m.copy()
        lo, hi = p.bounds
        p.apply_translation([-lo[0], -lo[1], -lo[2]])
        parts.append(p)
    order = sorted(range(len(parts)), key=lambda i: -parts[i].extents[1])     # tallest-in-Y first: tidy rows
    x = y = row_h = 0.0
    width = 0.0
    placed = [None] * len(parts)
    for i in order:
        ex, ey = parts[i].extents[0], parts[i].extents[1]
        if x > 0 and x + ex > bx:                                # next row
            y += row_h + gap
            x, row_h = 0.0, 0.0
        placed[i] = (x, y)
        parts[i].apply_translation([x, y, 0])
        x += ex + gap
        width = max(width, x - gap)
        row_h = max(row_h, ey)
    depth = y + row_h
    combined = trimesh.util.concatenate(parts)
    combined.apply_translation([-width / 2, -depth / 2, 0])
    tall = float(combined.extents[2])
    fits = width <= bx + 1e-6 and depth <= by + 1e-6 and (height is None or tall <= height + 1e-6)
    too_big = [i for i, p in enumerate(parts) if p.extents[0] > bx or p.extents[1] > by]
    return combined, {"fits": bool(fits), "footprint_mm": [round(width, 1), round(depth, 1), round(tall, 1)], "bed_mm": [bx, by] + ([height] if height else []),
                      "gap_mm": gap, "parts": len(parts), "too_big_parts": too_big,
                      "positions": [[round(a - width / 2, 1), round(b - depth / 2, 1)] for a, b in placed],
                      "_exact": [[a - width / 2, b - depth / 2] for a, b in placed]}
