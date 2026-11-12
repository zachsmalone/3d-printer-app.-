"""Mesh editing operations (trimesh / numpy / scipy / shapely; booleans via manifold3d when installed).

Every operation is a pure function  (mesh, params) -> (new_mesh, report)  working in MILLIMETRES, Z up.
Projects store the ORIGINAL upload untouched plus a list of {op, params}; the current mesh is the replay of
that list (see services/editproj.py), which is what makes undo / redo / jump-to-step non-destructive.
"""
from __future__ import annotations

import io
import logging
import math
import time
import zipfile
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree
from trimesh.transformations import scale_and_translate
from trimesh.voxel.base import VoxelGrid
from trimesh.voxel.encoding import SparseBinaryEncoding

try:
    import manifold3d
except Exception:
    manifold3d = None

try:
    import fast_simplification
except Exception:
    fast_simplification = None

try:
    from scipy import ndimage
    from skimage import measure as skimage_measure
except Exception:
    ndimage = None
    skimage_measure = None

log = logging.getLogger("zeim.hollow")

from . import memtrim

MAX_FACES = 3_000_000
UNIT_MM = {"mm": 1.0, "cm": 10.0, "in": 25.4, "m": 1000.0}


class OpError(ValueError):
    """User-facing problem (bad parameter / geometry unsuitable for this operation)."""


def have_boolean() -> bool:
    try:
        import manifold3d  # noqa: F401
        return True
    except Exception:
        return False


def have_simplify() -> bool:
    try:
        import fast_simplification  # noqa: F401
        return True
    except Exception:
        return False


def have_hollow() -> bool:
    return have_boolean() and ndimage is not None and skimage_measure is not None


# ------------------------------------------------------------------ helpers
def _num(p, key, default=None, lo=-1e6, hi=1e6):
    v = p.get(key, default)
    if v is None:
        raise OpError(f"'{key}' is required")
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise OpError(f"'{key}' must be a number")
    if not math.isfinite(v) or v < lo or v > hi:
        raise OpError(f"'{key}' must be between {lo:g} and {hi:g}")
    return v


def _vec(p, key, default=(0, 0, 0), lo=-1e5, hi=1e5):
    v = p.get(key, default)
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        raise OpError(f"'{key}' must be [x, y, z]")
    return np.array([_num({"v": x}, "v", lo=lo, hi=hi) for x in v], dtype=float)


def _new(vertices, faces) -> trimesh.Trimesh:
    return trimesh.Trimesh(np.asarray(vertices, float), np.asarray(faces, np.int64), process=False)


def _check(m: trimesh.Trimesh) -> trimesh.Trimesh:
    if len(m.faces) == 0:
        raise OpError("The operation left nothing (empty mesh).")
    if len(m.faces) > MAX_FACES:
        raise OpError(f"Result has {len(m.faces):,} triangles (limit {MAX_FACES:,}). Simplify first.")
    if not np.isfinite(m.vertices).all():
        raise OpError("Result contains invalid (NaN/inf) coordinates.")
    return m


def _bounds(m):
    return m.bounds[0], m.bounds[1]


def _transform(m, T):
    v = np.c_[m.vertices, np.ones(len(m.vertices))] @ np.asarray(T).T
    f = m.faces.copy()
    if np.linalg.det(np.asarray(T)[:3, :3]) < 0:   # mirrored -> keep outward-facing winding
        f = f[:, ::-1]
    return _new(v[:, :3], f)


def _mat_translate(t):
    T = np.eye(4); T[:3, 3] = t
    return T


def _drop(m):
    return _transform(m, _mat_translate([0, 0, -m.bounds[0][2]]))


def analyze(m: trimesh.Trimesh) -> dict:
    """Health + size report (shown in the UI as the 'Measure / Info' panel)."""
    n = len(m.faces)
    mg = m.copy() if n else m
    if n:
        mg.merge_vertices()                       # count edges as an exported STL will have them (coincident vertices joined)
    edges = np.sort(mg.edges, axis=1)
    _, cnt = np.unique(edges, axis=0, return_counts=True) if n else (None, np.array([]))
    boundary = int((cnt == 1).sum()); nonmanifold = int((cnt > 2).sum())
    lo, hi = m.bounds if n else (np.zeros(3), np.zeros(3))
    wt = bool(m.is_watertight) and bool(mg.is_watertight) and nonmanifold == 0 and boundary == 0     # trimesh alone can call an edge shared by 4 faces "watertight"
    vol = float(m.volume) if wt else float(abs(m.volume)) if n else 0.0
    try:
        com = m.center_mass.tolist() if wt and m.volume > 0 else m.centroid.tolist()
    except Exception:
        com = m.centroid.tolist()
    voids = None
    try:
        pieces = m.split(only_watertight=False) if n < 400_000 else None
        comps = len(pieces) if pieces is not None else None
        voids = sum(1 for c in pieces if c.is_watertight and c.volume < 0) if pieces is not None else None   # sealed inner cavities
    except Exception:
        comps = None
    return {"triangles": int(n), "vertices": int(len(m.vertices)), "watertight": wt,
            "winding_consistent": bool(m.is_winding_consistent), "boundary_edges": boundary,
            "nonmanifold_edges": nonmanifold, "inverted": bool(wt and m.volume < 0),
            "volume_mm3": round(vol, 2), "area_mm2": round(float(m.area), 2),
            "size_mm": (hi - lo).round(3).tolist(), "min_mm": lo.round(3).tolist(), "max_mm": hi.round(3).tolist(),
            "center_mm": ((lo + hi) / 2).round(3).tolist(), "center_of_mass_mm": np.round(com, 3).tolist(),
            "components": comps, "internal_voids": voids}


def _boundary_cycles(m: trimesh.Trimesh) -> list:
    """Directed open-boundary loops (vertex index lists, in the winding of the faces next to them)."""
    f = m.faces
    de = np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    key = np.sort(de, axis=1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    bnd = de[cnt[inv.reshape(-1)] == 1]
    if len(bnd) == 0:
        return []
    rem: dict = {}
    for a_, b_ in bnd:
        rem.setdefault(int(a_), []).append(int(b_))
    cycles = []
    while True:
        start = next((k for k, v in rem.items() if v), None)
        if start is None:
            break
        cur = rem[start].pop()
        path, pos = [start], {start: 0}
        while True:
            if cur in pos:                       # closed a simple cycle (handles bow-tie vertices)
                i = pos[cur]
                if len(path) - i >= 3:
                    cycles.append(path[i:])
                for v in path[i + 1:]:
                    del pos[v]
                path = path[:i + 1]
            else:
                pos[cur] = len(path)
                path.append(cur)
            outs = rem.get(cur)
            if not outs:
                break
            cur = outs.pop()
    return cycles


def fill_boundary_loops(m: trimesh.Trimesh, max_loop=20000) -> int:
    """Close open boundary loops with a centroid fan (trimesh.fill_holes only handles tiny holes).
    Returns the number of loops closed. Good for flat/gently curved holes; very concave holes may look rough."""
    new_faces, new_verts, loops = [], [], 0
    base = len(m.vertices)
    for loop in _boundary_cycles(m):
        if len(loop) > max_loop:
            continue
        c = m.vertices[loop].mean(0)
        ci = base + len(new_verts)
        new_verts.append(c)
        for i, a_ in enumerate(loop):
            new_faces.append([loop[(i + 1) % len(loop)], a_, ci])
        loops += 1
    if loops:
        m.vertices = np.vstack([m.vertices, np.array(new_verts)])
        m.faces = np.vstack([m.faces, np.array(new_faces, dtype=np.int64)])
    return loops


MAX_PATCH_LOOP = 150


def _min_area_patch(v, loop):
    """Triangulate one boundary loop with the smallest total area (dynamic programming over the loop, O(n³)).
    On a bent hole (e.g. across a cube edge) this follows the surface instead of cutting a corner off."""
    n = len(loop)
    P = v[loop]
    W = np.zeros((n, n)); K = np.zeros((n, n), dtype=np.int64)
    for gap in range(2, n):
        for i in range(n - gap):
            j = i + gap
            k = np.arange(i + 1, j)
            a = 0.5 * np.linalg.norm(np.cross(P[k] - P[i], P[j] - P[i]), axis=1)
            c = W[i, k] + W[k, j] + a
            b = int(np.argmin(c)); W[i, j] = c[b]; K[i, j] = k[b]
    tris, todo = [], [(0, n - 1)]
    while todo:
        i, j = todo.pop()
        if j - i < 2:
            continue
        k = K[i, j]
        tris.append([loop[j], loop[k], loop[i]])         # reversed: matches the faces around the hole
        todo += [(i, k), (k, j)]
    return tris


def _tet_volume(v, faces) -> float:
    t = v[np.asarray(faces)]
    return float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0)


def fill_nonplanar_loops(m: trimesh.Trimesh) -> tuple[int, int, float]:
    """QA B7: close the non-flat boundary loops with a minimum-area patch (trimesh's fill_holes picks an arbitrary
    diagonal and can cut a wedge out). Returns (non-flat loops, loops filled here, volume spread) where the spread
    is how much the volume would differ with a centroid-fan patch instead, i.e. how ambiguous the fill is."""
    tol = 1e-3 * float(max(m.extents.max(), 1e-9)) if len(m.vertices) else 0.0
    v = np.asarray(m.vertices, float)
    found, done, spread, new_faces, edges = 0, 0, 0.0, [], None
    for loop in _boundary_cycles(m):
        pts = v[loop]
        if len(loop) < 4:
            continue
        c = pts - pts.mean(axis=0)
        if np.abs(c @ np.linalg.svd(c, full_matrices=False)[2][-1]).max() <= tol:
            continue
        found += 1
        if len(loop) > MAX_PATCH_LOOP:
            continue
        tris = _min_area_patch(v, loop)
        if edges is None:
            edges = {tuple(e) for e in m.edges_sorted.tolist()}
        if any(tuple(sorted(e)) in edges for t in tris for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))
               if abs(loop.index(e[0]) - loop.index(e[1])) not in (1, len(loop) - 1)):
            continue                                      # a diagonal is already an edge: leave it to the old fill
        fan = [[loop[(i + 1) % len(loop)], a_, len(v)] for i, a_ in enumerate(loop)]
        spread += abs(_tet_volume(v, tris) - _tet_volume(np.vstack([v, pts.mean(axis=0)]), fan))
        new_faces += tris; done += 1
    if new_faces:
        m.faces = np.vstack([m.faces, np.array(new_faces, dtype=np.int64)])
    return found, done, spread


# ------------------------------------------------------------------ transforms
def op_translate(m, p):
    d = [_num(p, k, 0) for k in ("dx", "dy", "dz")]
    return _transform(m, _mat_translate(d)), {}


def op_rotate(m, p):
    """Rotate about the bounding-box centre, X then Y then Z (degrees)."""
    rx, ry, rz = (_num(p, k, 0, -3600, 3600) for k in ("rx", "ry", "rz"))
    lo, hi = _bounds(m); c = (lo + hi) / 2
    R = trimesh.transformations.euler_matrix(math.radians(rx), math.radians(ry), math.radians(rz), "sxyz")
    T = _mat_translate(c) @ R @ _mat_translate(-c)
    return _transform(m, T), {}


def op_scale(m, p):
    """Uniform / per-axis scale, or scale-to-target (longest side / fit bed / target volume)."""
    pivot = p.get("pivot", "base")
    lo, hi = _bounds(m)
    size = hi - lo
    mode = (p.get("mode") or "").lower()
    note = ""
    if mode == "longest" or p.get("target_longest") is not None:
        target = _num(p, "target_longest", None, 1, 1000)
        cur = float(max(size))
        if cur < 1e-9:
            raise OpError("Model has no size to scale.")
        k = target / cur
        sx = sy = sz = k
        note = f"Scaled longest side to {target:g} mm (×{k:.4g})."
    elif mode == "fit_bed" or p.get("fit_bed"):
        bed = p.get("bed") or p.get("bed_mm") or [220, 220, 250]
        if not isinstance(bed, (list, tuple)) or len(bed) < 2:
            raise OpError("fit_bed needs bed [X, Y] or [X, Y, Z] mm.")
        bx, by = float(bed[0]), float(bed[1])
        bz = float(bed[2]) if len(bed) > 2 else 1e9
        margin = _num(p, "margin", 2, 0, 50)
        usable = [max(1.0, bx - margin), max(1.0, by - margin), max(1.0, bz - margin)]
        ratios = [usable[i] / max(float(size[i]), 1e-9) for i in range(3)]
        k = min(ratios)
        if k <= 0:
            raise OpError("Bed size is too small.")
        sx = sy = sz = k
        note = f"Scaled to fit bed {bx:g}×{by:g}" + (f"×{bz:g}" if len(bed) > 2 else "") + f" mm with {margin:g} mm margin (×{k:.4g})."
    elif mode == "volume" or p.get("target_volume_cm3") is not None:
        target_cm3 = _num(p, "target_volume_cm3", None, 0.01, 1e6)
        vol = float(abs(m.volume)) if len(m.faces) else 0.0
        if vol < 1e-9:
            raise OpError("Model has no volume to scale (not watertight?).")
        # volume scales with cube of linear factor
        k = (target_cm3 * 1000.0 / vol) ** (1.0 / 3.0)
        sx = sy = sz = k
        note = f"Scaled to about {target_cm3:g} cm³ (×{k:.4g})."
    else:
        f = p.get("factor")
        sx, sy, sz = ((_num(p, k, f if f is not None else 1.0, 1e-3, 1e3)) for k in ("sx", "sy", "sz"))
    c = {"origin": np.zeros(3), "center": (lo + hi) / 2,
         "base": np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])}.get(pivot)
    if c is None:
        raise OpError("pivot must be base | center | origin")
    S = np.diag([sx, sy, sz, 1.0])
    T = _mat_translate(c) @ S @ _mat_translate(-c)
    out = _transform(m, T)
    rep = {"sx": sx, "sy": sy, "sz": sz}
    if note:
        rep["message"] = note
    return out, rep


def op_mirror(m, p):
    ax = {"x": 0, "y": 1, "z": 2}.get(str(p.get("axis", "")).lower())
    if ax is None:
        raise OpError("axis must be x | y | z")
    lo, hi = _bounds(m); c = (lo + hi) / 2
    S = np.eye(4); S[ax, ax] = -1
    return _transform(m, _mat_translate(c) @ S @ _mat_translate(-c)), {}


def op_place(m, p):
    """Drop to bed (min Z = 0) and/or centre on the bed origin (X/Y)."""
    t = np.zeros(3); lo, hi = _bounds(m)
    if p.get("center_xy"):
        t[:2] = -((lo + hi) / 2)[:2]
    if p.get("drop", True):
        t[2] = -lo[2]
    return _transform(m, _mat_translate(t)), {}


# ------------------------------------------------------------------ repair / simplify
def op_repair(m, p):
    before = analyze(m)
    rep = {"before": {k: before[k] for k in ("triangles", "watertight", "boundary_edges", "nonmanifold_edges", "inverted")}}
    m = m.copy()
    steps = []
    if p.get("remove_duplicates", True):
        nf = len(m.faces)
        m.merge_vertices()
        m.update_faces(m.unique_faces())
        m.update_faces(m.nondegenerate_faces())
        m.remove_unreferenced_vertices()
        steps.append(f"removed {nf - len(m.faces)} duplicate/degenerate faces, merged vertices")
    if p.get("keep_largest", False) and len(m.faces):
        parts = m.split(only_watertight=False)
        if len(parts) > 1:
            parts.sort(key=lambda x: len(x.faces), reverse=True)
            steps.append(f"kept only the largest piece and dropped {len(parts) - 1} other piece(s)")
            m = parts[0]
    if p.get("fix_normals", True):
        trimesh.repair.fix_winding(m)
        trimesh.repair.fix_inversion(m)
        trimesh.repair.fix_normals(m, multibody=True)
        steps.append("made face directions consistent / outward")
    nonflat = patched = 0; spread = 0.0
    if p.get("fill_holes", True):
        was = m.is_watertight
        if not was:
            try:
                nonflat, patched, spread = fill_nonplanar_loops(m)
            except Exception:                             # never let the better patch break a repair
                nonflat = 1
        trimesh.repair.fill_holes(m)
        if not m.is_watertight:
            fill_boundary_loops(m)
        trimesh.repair.fix_normals(m, multibody=True)
        if not was:
            steps.append("filled holes" + (" → now watertight" if m.is_watertight else " (some remain)"))
    m = _check(m)
    after = analyze(m)
    rep["after"] = {k: after[k] for k in ("triangles", "watertight", "boundary_edges", "nonmanifold_edges", "inverted")}
    rep["steps"] = steps
    rep["message"] = ("Mesh is watertight ✔" if after["watertight"] else
                      "Still not watertight — it may have complex holes or self-intersections; the slicer may still cope, "
                      "or try Simplify/Hollow-free workflow in another tool.")
    if nonflat and after["watertight"]:
        # QA B7: a non-flat hole has no single right patch. Non-flat loops now get the smallest-area patch, which
        # follows a bent hole (e.g. across a cube edge) instead of cutting a wedge out; still say how big the doubt is.
        vol = abs(float(m.volume))
        doubt = (f"; another patch would change it by up to {spread:,.1f} mm³ ({100 * spread / max(vol, 1e-9):.1f} %)"
                 if patched == nonflat else "")
        rep["warning"] = (f"{nonflat} filled hole(s) weren't flat. They were closed with the smallest patch that follows the "
                          f"hole's edge (now {vol:,.1f} mm³{doubt}). Check those areas before printing.")
        rep["message"] += " · check filled areas"
    return m, rep


def op_simplify(m, p):
    if not have_simplify():
        raise OpError("Simplify needs the 'fast-simplification' package (pip install fast-simplification).")
    keep = _num(p, "keep_ratio", 0.5, 0.02, 0.98)
    n0 = len(m.faces)
    target = max(8, int(n0 * keep))
    was_ok = bool(m.is_watertight)
    best = None
    for agg in (7, 5, 3):                     # gentler settings first fall back when a setting breaks the surface
        import fast_simplification as fs          # direct call: trimesh's wrapper returned a different (non-manifold) result on flat CAD meshes
        ov, of = fs.simplify(np.asarray(m.vertices, float), np.asarray(m.faces, np.int64), target_reduction=1 - target / n0, agg=agg)
        out = _check(_new(ov, of))
        if _strict_ok(out) or not was_ok:
            best = out; break
    if best is None:
        raise OpError("Simplify would break this model's surface (it would no longer be watertight), so it was left unchanged. "
                      "Try Fix (repair) first, or a higher keep ratio.")
    out = best
    n1 = len(out.faces)
    nm = _nonmanifold(out)
    rep = {"before_triangles": n0, "after_triangles": int(n1), "watertight": _strict_ok(out), "nonmanifold_edges": nm,
           "kept_pct": round(100 * n1 / n0, 1), "message": f"{n0:,} → {n1:,} triangles ({100 * n1 / n0:.1f}% kept)"}
    warn = []
    if not rep["watertight"]:
        warn.append(f"The result is NOT watertight ({nm} non-manifold edge{'s' if nm != 1 else ''}). Run Fix (repair) before printing.")
    wanted, got = 1 - keep, 1 - n1 / n0
    if got < 0.5 * wanted:                    # the target was not met: say so instead of reporting success
        rep["note"] = (f"You asked to keep {keep:.0%} of the triangles, but only {got:.0%} could be removed. This model couldn't "
                       "be simplified further without changing its shape or breaking its surface, so it was left close to the original.")
        rep["target_met"] = False
    else:
        rep["target_met"] = True
    if warn:
        rep["warning"] = " ".join(warn)
        rep["note"] = (rep.get("note", "") + " " + rep["warning"]).strip()
    return out, rep


def _nonmanifold(m) -> int:
    """Counted on a vertex-merged copy: the simplifier can leave coincident duplicate vertices that hide bad edges until export."""
    if not len(m.faces):
        return 0
    m = m.copy(); m.merge_vertices()
    _, cnt = np.unique(np.sort(m.edges, axis=1), axis=0, return_counts=True)
    return int((cnt > 2).sum())


def _strict_ok(m) -> bool:
    mm = m.copy(); mm.merge_vertices()
    return bool(mm.is_watertight) and _nonmanifold(mm) == 0


# ------------------------------------------------------------------ booleans
def _need_boolean():
    if not have_boolean():
        raise OpError("Boolean operations need the 'manifold3d' package (pip install manifold3d).")


def _prep_solid(m, what="model"):
    """Booleans need a closed, outward-oriented mesh: fix cheaply, otherwise explain."""
    if not m.is_watertight or not m.is_winding_consistent:
        m = m.copy(); m.merge_vertices(); trimesh.repair.fix_winding(m); trimesh.repair.fill_holes(m)
        trimesh.repair.fix_normals(m)
    if not m.is_watertight:
        raise OpError(f"The {what} isn't watertight, so a boolean can't be computed. Run Fix (repair) first.")
    if m.volume < 0:
        m = m.copy(); m.invert()
    return m


def _boolean(a, b, kind):
    _need_boolean()
    # A large difference used to run while the voxel grids were still charged to this
    # process. glibc does not return that address space, and the next Manifold build
    # then died with SIGSEGV under the prepare cap. Trim first, and build Manifold
    # ourselves so a non-manifold input becomes an error instead of an abort.
    large = len(getattr(a, "faces", [])) > 100_000 or len(getattr(b, "faces", [])) > 100_000
    if large:
        memtrim.trim()
        if kind == "difference":
            return _boolean_large_difference(a, b)
    a = _prep_solid(a); b = _prep_solid(b, "tool shape")
    try:
        r = {"union": trimesh.boolean.union, "difference": trimesh.boolean.difference,
             "intersection": trimesh.boolean.intersection}[kind]([a, b], engine="manifold")
    except Exception as e:
        raise OpError(f"Boolean failed: {e}")
    if r is None or len(r.faces) == 0:
        raise OpError("The result is empty (shapes may not overlap).")
    return _check(_new(r.vertices, r.faces))


def _boolean_large_difference(a, b):
    """Difference of a large solid minus a tool. Same manifold engine, without an unbounded repair."""
    if manifold3d is None:
        raise OpError("Boolean operations need the 'manifold3d' package (pip install manifold3d).")
    a = _solid_ready(a, "model")
    b = _solid_ready(b, "tool shape")
    try:
        result = _manifold_mesh(a) - _manifold_mesh(b)
    except OpError:
        raise
    except Exception as e:
        raise OpError(f"Boolean failed: {e}") from None
    if result.status() != manifold3d.Error.NoError or result.is_empty() or result.num_tri() == 0:
        raise OpError("The result is empty (shapes may not overlap).")
    mesh = result.to_mesh()
    return _check(_new(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts)))


def _solid_ready(m, what):
    """A closed solid for a large boolean. Do not fan-fill a huge hole; that path crashed."""
    if len(m.faces) > 100_000 and not m.is_watertight:
        raise OpError(f"The {what} isn't watertight, so a boolean can't be computed. Run Fix (repair) first.")
    return _prep_solid(m, what)


def _manifold_mesh(m):
    verts = np.ascontiguousarray(m.vertices, dtype=np.float32)
    faces = np.ascontiguousarray(m.faces, dtype=np.uint32)
    if len(faces) == 0 or not np.isfinite(verts).all() or int(faces.max()) >= len(verts):
        raise OpError("Could not hollow this shape. Try a thicker wall, or turn hollowing off.")
    man = manifold3d.Manifold(manifold3d.Mesh(vert_properties=verts, tri_verts=faces))
    if man.status() != manifold3d.Error.NoError or man.is_empty():
        raise OpError("Could not hollow this shape. Try a thicker wall, or turn hollowing off.")
    return man


def primitive(spec: dict) -> trimesh.Trimesh:
    t = spec.get("type")
    pos = _vec(spec, "position")
    if t == "box":
        ext = _vec(spec, "size", (10, 10, 10), 0.01, 5000)
        m = trimesh.creation.box(extents=ext)
    elif t == "cylinder":
        d = _num(spec, "diameter", 10, 0.01, 5000); h = _num(spec, "height", 10, 0.01, 5000)
        m = trimesh.creation.cylinder(radius=d / 2, height=h, sections=64)
        axis = spec.get("axis", "z")
        if axis == "x":
            m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
        elif axis == "y":
            m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
        elif axis != "z":
            raise OpError("cylinder axis must be x | y | z")
    elif t == "sphere":
        d = _num(spec, "diameter", 10, 0.01, 5000)
        m = trimesh.creation.icosphere(subdivisions=4, radius=d / 2)
    else:
        raise OpError("primitive type must be box | cylinder | sphere")
    m = _new(m.vertices + pos, m.faces)
    return m


def op_boolean(m, p):
    kind = p.get("kind")
    if kind not in ("union", "difference", "intersection"):
        raise OpError("kind must be union | difference | intersection")
    tool = primitive(p.get("primitive") or {})
    out = _boolean(m, tool, kind)
    return out, {"message": f"{kind} with {p['primitive']['type']}"}


def op_on_face(m, p):
    """Place a dimensioned shape on a picked face and add or cut it (direct editing, mesh-native).

    The op is anchored to the picked face's PLANE - a unit normal plus a point on the face, as the
    feature detector reports them - never to triangle ids (those would not survive later edits that
    change the triangulation). This is a fixed workplane, not an associative face reference: a later
    translate/rotate of the model does not move the anchor. Like every op it is stored in the history,
    so it is editable, undoable and replays deterministically.
    """
    shape = p.get("shape", "box")
    if shape not in ("box", "cylinder", "polygon"):
        raise OpError("shape must be box | cylinder | polygon")
    mode = p.get("mode", "add")
    if mode not in ("add", "cut"):
        raise OpError("mode must be add | cut")
    plane = p.get("plane") or {}
    if not isinstance(plane, dict) or not plane.get("normal") or not plane.get("point"):
        raise OpError("plane must be {normal: [x,y,z], point: [x,y,z]} from the face picker")
    try:
        n = np.array([float(v) for v in plane["normal"]], dtype=float).reshape(-1)
        point = np.array([float(v) for v in plane["point"]], dtype=float).reshape(-1)
    except (TypeError, ValueError):
        raise OpError("plane.normal and plane.point must be numbers")
    if n.shape != (3,) or point.shape != (3,):
        raise OpError("plane.normal and plane.point must each be [x, y, z]")
    ln = float(np.linalg.norm(n))
    if not np.isfinite(ln) or ln < 1e-9 or not np.isfinite(point).all():
        raise OpError("the face's plane is degenerate; pick the face again")
    n = n / ln
    height = _num(p, "height", 10, 0.01, 5000)
    offset = _num(p, "offset", 0, -500, 500)
    poly = None
    if shape == "polygon":
        poly = _sketch_polygon(p.get("points"))
        footprint = tuple(float(x) for x in np.ptp(np.array(poly.exterior.coords), axis=0))
    elif shape == "box":
        width = _num(p, "width", 10, 0.01, 5000)
        depth = _num(p, "depth", 10, 0.01, 5000)
        footprint = (width, depth)
    else:
        diameter = _num(p, "diameter", 10, 0.01, 5000)
        footprint = (diameter,)

    # Local frame on the plane: u, v span the face, n is outward (area-weighted face normals
    # of a proper solid point away from the material, which is what the detector reports).
    a = np.zeros(3); a[int(np.argmin(np.abs(n)))] = 1.0
    u = np.cross(n, a); u /= np.linalg.norm(u)
    v = np.cross(n, u)

    if mode == "add":
        z0, z1 = offset, offset + height
    else:
        # Cut into the material; a small skim above the plane avoids coincident-face booleans.
        skim = max(0.02, 0.01 * height)
        z0, z1 = offset - height, offset + skim
    zc = (z0 + z1) / 2

    if shape == "polygon":
        tool = trimesh.creation.extrude_polygon(poly, z1 - z0)
        tool.apply_translation([0, 0, z0])
    elif shape == "box":
        tool = trimesh.creation.box(extents=(footprint[0], footprint[1], z1 - z0))
    else:
        tool = trimesh.creation.cylinder(radius=footprint[0] / 2, height=z1 - z0, sections=64)
    T = np.eye(4); T[:3, :3] = np.column_stack([u, v, n]); T[:3, 3] = point if shape == "polygon" else point + n * zc
    tool.apply_transform(T)

    # Refuse obvious misses instead of silently doing nothing.
    if not _bounds_overlap(m, tool):
        raise OpError("that spot is outside the model - nothing to " + ("add onto" if mode == "add" else "cut"))
    comps_before = _component_count(m)
    vol_before = float(m.volume)
    out = _boolean(m, tool, "union" if mode == "add" else "difference")
    # A bounding-box check can pass over a hole or a concave region; verify the edit really happened.
    if mode == "add" and _component_count(out) > comps_before:
        raise OpError("that spot is not on solid material - the shape would come off detached")
    if mode == "cut" and abs(float(out.volume) - vol_before) < 1e-6:
        raise OpError("nothing to cut there - that spot is not on solid material")
    what = (f"{footprint[0]:g}×{footprint[1]:g} mm box" if shape == "box" else f"{len(poly.exterior.coords) - 1}-point outline" if shape == "polygon" else f"Ø{footprint[0]:g} mm cylinder")
    return out, {"message": ("Added " if mode == "add" else "Cut ") + what + f", {height:g} mm, on the picked face"}


SKETCH_MAX_POINTS = 200


def _sketch_polygon(points):
    """A typed 2D outline in the face's own (u, v) millimetres -> a valid, simple shapely polygon. Raises OpError."""
    from shapely.geometry import Polygon
    if not isinstance(points, list) or not 3 <= len(points) <= SKETCH_MAX_POINTS:
        raise OpError(f"points must be a list of 3 to {SKETCH_MAX_POINTS} [u, v] pairs")
    try:
        pts = [(float(a), float(b)) for a, b in points]
    except (TypeError, ValueError):
        raise OpError("each point must be [u, v] numbers")
    if not all(np.isfinite(c) and abs(c) <= 5000 for xy in pts for c in xy):
        raise OpError("point values must be finite and within ±5000 mm")
    poly = Polygon(pts)
    if not poly.is_valid or poly.area < 1e-4:
        raise OpError("the outline crosses itself or is too small; draw a simple closed shape")
    return poly


def _component_count(m: trimesh.Trimesh) -> int:
    try:
        pieces = m.split(only_watertight=False)
        return len(pieces) if pieces is not None else 1
    except Exception:
        return 1


def _bounds_overlap(a: trimesh.Trimesh, b: trimesh.Trimesh, tol: float = 0.0) -> bool:
    amin, amax = _bounds(a); bmin, bmax = _bounds(b)          # _bounds returns (lo, hi)
    return bool(((amax >= bmin - tol) & (amin <= bmax + tol)).all())


def op_base(m, p):
    """Flat base plate (or thin brim) under the model. style: rect | round | outline (follows the footprint)."""
    style = p.get("style", "outline")
    margin = _num(p, "margin", 3, 0, 500); th = _num(p, "thickness", 2, 0.1, 100)
    overlap = min(0.4, th / 2)
    m = _drop(m); lo, hi = _bounds(m)
    from shapely.geometry import Point, box as sbox
    if style == "rect":
        poly = sbox(lo[0] - margin, lo[1] - margin, hi[0] + margin, hi[1] + margin)
    elif style == "round":
        c = (lo + hi) / 2; r = math.hypot(*(hi - lo)[:2]) / 2 + margin
        poly = Point(c[0], c[1]).buffer(r, 64)
    elif style == "outline":
        from shapely.ops import unary_union
        from shapely.geometry import Polygon
        tri = m.vertices[m.faces][:, :, :2]
        # only footprint-relevant: whole silhouette, via triangles' XY projection (cheap sampling for huge meshes)
        if len(tri) > 200_000:
            tri = tri[np.random.default_rng(0).choice(len(tri), 200_000, replace=False)]
        e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
        area = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) > 1e-9
        polys = [Polygon(t) for t in tri[area]]
        poly = unary_union(polys).buffer(margin, 32).simplify(0.05)
        if poly.is_empty:
            raise OpError("Could not compute the model footprint.")
        if poly.geom_type == "MultiPolygon":
            poly = poly.convex_hull        # separate islands: bridge them with one base
        poly = poly.buffer(0)
    else:
        raise OpError("style must be rect | round | outline")
    plate = trimesh.creation.extrude_polygon(poly, th + overlap)
    plate = _new(plate.vertices + [0, 0, -th], plate.faces)    # spans z = -th .. +overlap
    out = _boolean(m, plate, "union")
    return _drop(out), {"message": f"added {th:g} mm {style} base (+{margin:g} mm margin)"}


# ------------------------------------------------------------------ cut / split
def op_cut(m, p):
    axis = p.get("axis")
    if axis in ("x", "y", "z"):
        normal = np.eye(3)[{"x": 0, "y": 1, "z": 2}[axis]]
        pos = _num(p, "position", None)
        origin = normal * pos
    else:
        normal = _vec(p, "normal", (0, 0, 1)); origin = _vec(p, "origin")
        if np.linalg.norm(normal) < 1e-9:
            raise OpError("plane normal can't be zero")
        normal = normal / np.linalg.norm(normal)
    keep = p.get("keep", "above")
    if keep not in ("above", "below", "both"):
        raise OpError("keep must be above | below | both")
    mm = m
    if not m.is_watertight:
        mm = op_repair(m, {"keep_largest": False})[0]
    cap = bool(mm.is_watertight)
    warn = "" if cap else "Model isn't watertight so the cut faces were left open — run Fix first for a capped cut."
    parts, healed = [], False

    def side(n):
        """One side of the plane. trimesh's capping can leave the cut face open on toothed/holey cross-sections (seen on a gear):
        then redo it as a boolean with a big box, which is exact; if even that fails the piece is kept and the result says it is open."""
        nonlocal healed
        a = mm.slice_plane(origin, n, cap=cap)
        if a is None or not len(a.faces):
            return None
        if cap and not _new(a.vertices, a.faces).is_watertight and have_boolean():
            try:
                L = float(np.linalg.norm(mm.extents)) * 2 + 10
                box = trimesh.creation.box(extents=(L, L, L))
                box = _transform(_new(box.vertices, box.faces), trimesh.geometry.align_vectors([0, 0, 1], n))
                box = _transform(box, _mat_translate(np.asarray(origin, float) + n * (L / 2)))
                b2 = _boolean(mm, box, "intersection")
                if b2.is_watertight:
                    healed = True
                    return b2
            except OpError:
                pass
        return a

    if keep in ("above", "both"):
        a = side(normal)
        if a is not None:
            parts.append(("above", a, normal))
    if keep in ("below", "both"):
        b = side(-normal)
        if b is not None:
            parts.append(("below", b, -normal))
    if not parts:
        raise OpError("The plane doesn't cut through the model (nothing left on the chosen side).")
    join_rep = {}
    join = (p.get("join") or "").lower().strip()
    if keep == "both" and len(parts) == 2 and join and join != "none":
        # parts are ("above", mesh, normal) and ("below", mesh, -normal)
        above = next(x[1] for x in parts if x[0] == "above")
        below = next(x[1] for x in parts if x[0] == "below")
        # Cut plane: origin along +normal from the cut; above sits on +normal side
        from . import smartsplit
        nrm = next(x[2] for x in parts if x[0] == "above")
        if axis in ("x", "y", "z"):
            join_origin = nrm * float(pos)
        else:
            join_origin = np.asarray(origin, float)
        try:
            below, above, join_rep = smartsplit.apply_join(below, above, join_origin, nrm, join, p)
            join_rep["join"] = join
            join_rep["connector_fit"] = "simulated"
            # rebuild parts list with joined meshes
            parts = [("above", above, nrm), ("below", below, -nrm)]
        except Exception as e:
            raise OpError(f"Could not add {join} join on the cut: {e}") from e
    if keep == "both" and len(parts) == 2 and p.get("lay_flat", True):
        gap = _num(p, "gap", 5, 0, 200)
        placed, x = [], 0.0
        for _, part, n in parts:           # rotate so the cut face (outward normal = -n) points down
            R = trimesh.geometry.align_vectors(-n, [0, 0, -1])
            q = _transform(_new(part.vertices, part.faces), R)
            lo, hi = _bounds(q)
            q = _transform(q, _mat_translate([x - lo[0], -(lo[1] + hi[1]) / 2, -lo[2]]))
            x += (hi[0] - lo[0]) + gap
            placed.append(q)
        out = trimesh.util.concatenate(placed)
    elif len(parts) == 1:
        out = parts[0][1]
        if p.get("lay_flat", True):
            R = trimesh.geometry.align_vectors(-parts[0][2], [0, 0, -1])
            out = _drop(_transform(_new(out.vertices, out.faces), R))
    else:
        out = trimesh.util.concatenate([x[1] for x in parts])
    out = _check(_new(out.vertices, out.faces))
    if cap and not out.is_watertight and not warn:       # input was closed but the cut left it open: never report plain success
        warn = "The cut left the model with an open face, so it is not watertight. Try Fix (repair) on the result, or cut at a different height."
    msg = f"kept {keep}; {len(parts)} piece(s)"
    if join_rep.get("join"):
        msg += f" · join={join_rep['join']} (Simulated)"
    if warn:
        msg += " · " + warn
    rep = {"message": msg, "warning": warn, "watertight": bool(out.is_watertight)}
    if join_rep:
        rep["join"] = join_rep
    return out, rep


# ------------------------------------------------------------------ hollow
def _drop_slivers(m, min_cavity_vol: float):
    """After a boolean: keep the outer solid(s) and real cavities; drop zero-volume bits and sealed pockets too small to matter."""
    parts = m.split(only_watertight=False)
    if len(parts) <= 1:
        return m, 0
    biggest = max(abs(c.volume) for c in parts)
    keep = [c for c in parts if (c.volume > 0 and c.volume >= 0.001 * biggest) or (c.volume < 0 and -c.volume >= min_cavity_vol)]
    if not keep or all(c.volume < 0 for c in keep):
        return m, 0
    if len(keep) == len(parts):
        return m, 0
    return _new(*(lambda t: (t.vertices, t.faces))(trimesh.util.concatenate(keep))), len(parts) - len(keep)


def _measure_wall(outer, cavity, n=2500):
    """Honest wall thickness: distance from points on the cavity surface to the outer surface (None if it cannot be measured)."""
    try:
        pts = cavity.vertices
        if len(pts) > n:
            pts = pts[np.random.default_rng(0).choice(len(pts), n, replace=False)]
        _, dist, _ = trimesh.proximity.closest_point(outer, pts)
        return float(dist.min())
    except Exception:
        return None


VOX_FACES = 120_000
# Dense SDF working set (bool grid + two float64 distances + the field). 6e6 cells is about 200 MB.
HOLLOW_MAX_VOXELS = 6_000_000
# Above this, hollowing must not boolean or voxelize the printed shell. A 694k-triangle
# mask with sculpted detail peaked near 3.7 GB while sampling that shell down to the
# voxel pitch; the dense grid and marching cubes were a few tens of MB. The cavity is
# built from a coarse proxy and concatenated, so the outer vertices stay put.
HOLLOW_SHELL_FACES = 80_000
HOLLOW_PROXY_FACES = 80_000
HOLLOW_SHELL_VOXELS = 2_000_000
CAVITY_FACE_CAP = 120_000
# Voids smaller than this share of the main cavity are pockets. They are not cut
# out, so the resin there stays solid instead of a sealed cup.
CAVITY_KEEP_FRAC = 0.05
# A hollow that keeps less of the model than this is not worth the drains.
MIN_HOLLOW_SAVE_PCT = 10.0
LEFT_SOLID_NOTE = "This model is mostly thin walls, so hollowing saved little; it was left solid."


def _vox_source(mm):
    """Decimated copy used only when the global trimesh voxelizer is still cheap.

    That voxelizer subdivides every long edge in one mesh. A detailed model decimated to
    VOX_FACES still has edges many times the pitch, and the temporary mesh tripped the
    prepare memory cap. The boolean and the wall checks keep the full outer surface.
    """
    n0 = len(mm.faces)
    if n0 <= VOX_FACES:
        return mm
    if fast_simplification is None:
        return mm
    try:
        ov, of = fast_simplification.simplify(
            np.asarray(mm.vertices, float), np.asarray(mm.faces, np.int64), target_reduction=1 - VOX_FACES / n0)
        lo = _new(ov, of)
        return lo if len(lo.faces) else mm
    except Exception:
        return mm


def _hollow_pitch(ext, wall):
    """Voxel size for this wall and this bounding box. Coarser when the grid would not fit."""
    span = np.asarray(ext, dtype=np.float64) + 2.0 * float(wall)
    span = np.maximum(span, 1e-6)
    pitch = max(float(wall) / 3.0, float((np.prod(span) / HOLLOW_MAX_VOXELS) ** (1.0 / 3.0)))
    if pitch > float(wall) / 1.5:
        raise OpError(f"Wall {wall:g} mm is too thin for a model this big (needs ≈{pitch * 1.5:.1f} mm+). "
                      "Increase the wall or scale the model down first.")
    dims = np.ceil(span / pitch).astype(np.int64)
    if int(np.prod(dims)) > HOLLOW_MAX_VOXELS * 2:
        raise MemoryError("hollow voxel grid does not fit in the prepare memory budget")
    return pitch


def _bounded_voxels(mm, pitch):
    """True when trimesh's one-shot subdivide voxelizer is likely to exceed the budget."""
    n = len(mm.faces)
    if n > 80_000:
        return True
    if n < 2_000:
        return False
    step = max(1, n // 2_000)
    tri = mm.triangles[::step]
    if len(tri) == 0:
        return False
    longest = float(np.linalg.norm(tri[:, 0] - tri[:, 1], axis=1).max())
    return longest > float(pitch) * 8.0


def _emit_surface_batch(vertices, faces, max_edge, pitch, chunks):
    """Round surface samples of one face batch into voxel indices. Subdivide only this batch."""
    faces = np.asarray(faces, np.int64)
    if len(faces) == 0:
        return
    tri = vertices[faces]
    ab = np.linalg.norm(tri[:, 0] - tri[:, 1], axis=1)
    bc = np.linalg.norm(tri[:, 1] - tri[:, 2], axis=1)
    ca = np.linalg.norm(tri[:, 2] - tri[:, 0], axis=1)
    long = np.maximum(np.maximum(ab, bc), ca) > max_edge
    if np.any(~long):
        chunks.append(np.round(tri[~long].reshape(-1, 3) / pitch).astype(np.int32))
    if not np.any(long):
        return
    if len(faces) > 20_000:
        mid = len(faces) // 2
        _emit_surface_batch(vertices, faces[:mid], max_edge, pitch, chunks)
        _emit_surface_batch(vertices, faces[mid:], max_edge, pitch, chunks)
        return
    used = np.unique(faces[long])
    remap = np.full(len(vertices), -1, np.int64)
    remap[used] = np.arange(len(used))
    sv = vertices[used]
    lf = remap[faces[long]]
    for _ in range(12):
        if len(lf) > 40_000:
            mid = len(lf) // 2
            _emit_surface_batch(sv, lf[:mid], max_edge, pitch, chunks)
            _emit_surface_batch(sv, lf[mid:], max_edge, pitch, chunks)
            return
        tri = sv[lf]
        ab = np.linalg.norm(tri[:, 0] - tri[:, 1], axis=1)
        bc = np.linalg.norm(tri[:, 1] - tri[:, 2], axis=1)
        ca = np.linalg.norm(tri[:, 2] - tri[:, 0], axis=1)
        still = np.maximum(np.maximum(ab, bc), ca) > max_edge
        if np.any(~still):
            chunks.append(np.round(tri[~still].reshape(-1, 3) / pitch).astype(np.int32))
        if not np.any(still):
            return
        sv, lf = trimesh.remesh.subdivide(sv, lf[still])
    tri = sv[lf]
    chunks.append(np.round(tri.reshape(-1, 3) / pitch).astype(np.int32))


def _voxel_fill_bounded(mm, pitch):
    """Filled voxel grid without building one subdivided copy of the whole mesh.

    Samples match trimesh's subdivide voxelizer (vertices of edges shorter than pitch/2,
    rounded to the grid) so the shell stays closed enough to fill. The dense grid is
    capped by the pitch chosen in `_hollow_pitch`.
    """
    max_edge = float(pitch) / 2.0
    verts = np.asarray(mm.vertices, np.float64)
    faces = np.asarray(mm.faces, np.int64)
    # Unique each batch. Holding every sample until the end peaked at about 3.7 GB
    # on a wrinkled 694k-triangle shell; the occupied voxels themselves are small.
    acc = None
    batch = 8_000
    for start in range(0, len(faces), batch):
        chunks = []
        _emit_surface_batch(verts, faces[start:start + batch], max_edge, pitch, chunks)
        if not chunks:
            continue
        block = np.unique(np.vstack(chunks), axis=0)
        del chunks
        acc = block if acc is None else np.unique(np.vstack([acc, block]), axis=0)
        del block
    if acc is None or len(acc) == 0:
        raise OpError("Could not build a cavity for this shape. Try a thicker wall.")
    idx = acc
    origin = idx.min(axis=0)
    local = (idx - origin).astype(np.int64, copy=False)
    dims = local.max(axis=0) + 1
    if int(np.prod(dims, dtype=np.int64)) > HOLLOW_MAX_VOXELS * 4:
        raise MemoryError("hollow voxel grid does not fit in the prepare memory budget")
    grid = VoxelGrid(
        SparseBinaryEncoding(local),
        transform=scale_and_translate(scale=float(pitch), translate=origin.astype(np.float64) * float(pitch)),
    )
    return grid.fill()


def op_hollow(m, p):
    """Hollow with wall thickness via a distance field (voxel SDF → marching cubes → boolean difference).
    Accuracy is ~ one voxel, shown in the report. Optional drain hole at the lowest point of the cavity.
    The outer surface is the original mesh; only the cavity comes from the voxel grid.
    A large mesh is shelled instead: the cavity comes from a coarse proxy and is concatenated,
    so this does not decimate or boolean the printed surface."""
    if not have_hollow():
        raise OpError("Hollow needs 'manifold3d' and 'scikit-image'.")
    wall = _num(p, "wall", 2, 0.2, 100); drain = _num(p, "drain_diameter", 0, 0, 100)
    mm = _prep_solid(m)
    ext = mm.extents
    if wall * 2.2 >= ext.min():
        raise OpError(f"Wall {wall:g} mm is too thick for this model (thinnest side is {ext.min():.1f} mm). "
                      "Lithophanes and thin plates can't be hollowed.")
    if len(mm.faces) > HOLLOW_SHELL_FACES:
        return _hollow_shell(mm, wall, drain, p)
    pitch = _hollow_pitch(ext, wall)
    if _bounded_voxels(mm, pitch):
        vox = _voxel_fill_bounded(mm, pitch)
    else:
        vox = _vox_source(mm).voxelized(pitch).fill()
    inside = np.pad(vox.matrix, 2)
    d_in = ndimage.distance_transform_edt(inside) * pitch
    d_out = ndimage.distance_transform_edt(~inside) * pitch
    sdf = np.where(inside, d_in - 0.5 * pitch, -(d_out - 0.5 * pitch))      # +ve inside, ≈ signed distance to surface
    del d_in, d_out, inside
    return _hollow_from(mm, sdf, vox, pitch, wall, drain, p)


def _proc_mb():
    """Current and peak resident set, in MB. Peak is the process high-water mark."""
    rss = peak = 0.0
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    rss = int(line.split()[1]) / 1024.0
                elif line.startswith("VmHWM:"):
                    peak = int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return rss, peak


class _HollowStages:
    """Per-stage RSS for a large hollow. The UI shows `message` only."""

    def __init__(self):
        self.rows = []
        self.t0 = time.perf_counter()

    def mark(self, name, **info):
        rss, peak = _proc_mb()
        row = {"name": name, "rss_mb": round(rss, 1), "peak_mb": round(peak, 1),
               "ms": round((time.perf_counter() - self.t0) * 1000.0)}
        row.update(info)
        self.rows.append(row)
        log.info("hollow %s", row)
        self.t0 = time.perf_counter()


def _shell_pitch(ext, wall):
    """Coarse cavity pitch. One voxel is the wall tolerance; the printed shell is not this grid."""
    span = np.maximum(np.asarray(ext, dtype=np.float64) + 2.0 * float(wall), 1e-6)
    pitch = max(float(wall) / 2.0, float((float(np.prod(span)) / HOLLOW_SHELL_VOXELS) ** (1.0 / 3.0)))
    if pitch > float(wall) / 1.5:
        raise OpError(f"Wall {wall:g} mm is too thin for a model this big (needs ≈{pitch * 1.5:.1f} mm+). "
                      "Increase the wall or scale the model down first.")
    dims = np.ceil(span / pitch).astype(np.int64) + 4
    if int(np.prod(dims, dtype=np.int64)) > HOLLOW_SHELL_VOXELS * 4:
        raise MemoryError("hollow voxel grid does not fit in the prepare memory budget")
    return float(pitch)


def _cavity_proxy(mm):
    """Decimated stand-in for the cavity only. The returned flag is false when this is the real shell."""
    n = len(mm.faces)
    if n <= HOLLOW_PROXY_FACES or fast_simplification is None:
        return mm, False
    try:
        ov, of = fast_simplification.simplify(
            np.ascontiguousarray(mm.vertices, dtype=np.float64),
            np.ascontiguousarray(mm.faces, dtype=np.int64),
            target_reduction=1.0 - HOLLOW_PROXY_FACES / n,
        )
        proxy = _new(ov, of)
        if len(proxy.faces) == 0:
            return mm, False
        return proxy, True
    except MemoryError:
        raise
    except Exception:
        return mm, False


def _proxy_outward_mm(full, proxy):
    """How far the proxy pokes outside the real shell, from vertex normals. 0 when it sits inside."""
    pts = np.asarray(proxy.vertices, np.float64)
    if len(pts) > 4000:
        pts = pts[np.random.default_rng(0).choice(len(pts), 4000, replace=False)]
    verts = np.asarray(full.vertices, np.float64)
    _dist, idx = cKDTree(verts).query(pts, workers=1)
    normals = np.asarray(full.vertex_normals, np.float64)[idx]
    signed = np.einsum("ij,ij->i", pts - verts[idx], normals)
    return float(max(0.0, np.percentile(signed, 98)))


def _proxy_sdf(source, pitch):
    """Float32 signed distance of a filled voxelization. Positive inside. The grid is freed by the caller."""
    vox = _voxel_fill_bounded(source, pitch)
    matrix = np.asarray(vox.matrix, dtype=bool)
    filled = int(matrix.sum())
    inside = np.pad(matrix, 2)
    del matrix
    raw = ndimage.distance_transform_edt(inside, sampling=float(pitch))
    d_in = np.asarray(raw, dtype=np.float32)
    del raw
    raw = ndimage.distance_transform_edt(np.logical_not(inside), sampling=float(pitch))
    d_out = np.asarray(raw, dtype=np.float32)
    del raw
    half = np.float32(0.5 * pitch)
    sdf = np.where(inside, d_in - half, -(d_out - half))
    if sdf.dtype != np.float32:
        sdf = np.asarray(sdf, dtype=np.float32)
    del d_in, d_out, inside
    return sdf, vox, filled


def _cavity_from_sdf(sdf, vox, pitch, offset):
    """Marching-cubes cavity at `offset` mm inside the proxy, capped so the void stays coarse."""
    field = np.ascontiguousarray(sdf - np.float32(offset), dtype=np.float32)
    if float(field.max()) <= 0.0:
        return None
    verts, faces, _, _ = skimage_measure.marching_cubes(field, 0.0, spacing=(pitch, pitch, pitch))
    world = trimesh.transform_points(verts / pitch - 2.0, vox.transform)
    del verts, field
    cav = _close_cavity(_new(world, faces[:, ::-1]))
    del world, faces
    if len(cav.faces) > CAVITY_FACE_CAP and fast_simplification is not None:
        try:
            cv, cf = fast_simplification.simplify(
                np.ascontiguousarray(cav.vertices, dtype=np.float64),
                np.ascontiguousarray(cav.faces, dtype=np.int64),
                target_reduction=1.0 - CAVITY_FACE_CAP / len(cav.faces),
            )
            reduced = _close_cavity(_new(cv, cf))
            if len(reduced.faces) and reduced.volume > 0:
                cav = reduced
        except MemoryError:
            raise
        except Exception:
            pass
    return cav


def _cavity_parts(cav, wall):
    """Keep voids large enough to drain. Dropped pieces are not cut out of the shell.

    A pocket under a few percent of the main void, or a thin crumb beside it, would
    be a sealed cup if it were left in and not drained. Leaving it out fills that
    region solid. The largest void is kept here; the save check can still reject it.
    """
    min_abs = (1.5 * float(wall)) ** 3
    all_parts = [c for c in cav.split(only_watertight=False) if c.volume > 0]
    if not all_parts:
        return [], 0
    main = max(float(c.volume) for c in all_parts)
    floor = max(min_abs, CAVITY_KEEP_FRAC * main)
    thin_span = max(1.5, float(wall) * 0.75)
    kept = []
    for part in all_parts:
        vol = float(part.volume)
        span = float(np.min(part.extents))
        if vol + 1e-6 >= main:
            kept.append(part)
            continue
        if vol < floor or (span < thin_span and vol < 0.25 * main):
            continue
        kept.append(part)
    return kept, len(all_parts) - len(kept)


def _merge_cavity_parts(parts, gap):
    """Union voids whose boxes meet, so one pocket is not stored as two shells."""
    if len(parts) <= 1:
        return parts
    parent = list(range(len(parts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    boxes = []
    for part in parts:
        lo, hi = np.asarray(part.bounds, dtype=np.float64)
        boxes.append((lo - gap, hi + gap))
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            lo_i, hi_i = boxes[i]
            lo_j, hi_j = boxes[j]
            if np.all(lo_i <= hi_j) and np.all(lo_j <= hi_i):
                parent[find(i)] = find(j)
    groups = {}
    for i, part in enumerate(parts):
        groups.setdefault(find(i), []).append(part)
    if all(len(group) == 1 for group in groups.values()):
        return parts
    merged = []
    for group in groups.values():
        if len(group) == 1:
            merged.append(group[0])
            continue
        try:
            union = trimesh.boolean.union(group, engine="manifold")
        except Exception:
            merged.extend(group)
            continue
        if union is None or len(union.faces) == 0:
            merged.extend(group)
            continue
        pieces = [c for c in union.split(only_watertight=False) if c.volume > 0]
        merged.extend(pieces or group)
    return merged or parts


def _face_spans(faces, nvert):
    """Vertex → incident faces, as slices of one face-index array."""
    flat_v = np.ascontiguousarray(faces, dtype=np.int64).ravel()
    flat_f = np.repeat(np.arange(len(faces), dtype=np.int64), 3)
    order = np.argsort(flat_v, kind="mergesort")
    flat_v = flat_v[order]
    flat_f = flat_f[order]
    change = np.empty(len(flat_v), dtype=bool)
    change[0] = True
    change[1:] = flat_v[1:] != flat_v[:-1]
    starts_u = np.flatnonzero(change)
    counts_u = np.diff(np.append(starts_u, len(flat_v)))
    start = np.full(nvert, -1, dtype=np.int64)
    count = np.zeros(nvert, dtype=np.int64)
    start[flat_v[starts_u]] = starts_u
    count[flat_v[starts_u]] = counts_u
    return start, count, flat_f


def _faces_of(vert_ids, start, count, flat_f):
    blocks = []
    for v in np.atleast_1d(vert_ids):
        n = int(count[int(v)])
        if n:
            s = int(start[int(v)])
            blocks.append(flat_f[s:s + n])
    if not blocks:
        return np.zeros(0, dtype=np.int64)
    return np.unique(np.concatenate(blocks))


def _closest_clearance(point, tris):
    """Distance, signed distance, and closest point from one point to triangles.

    Signed distance is positive on the outward side of the triangle normals.
    """
    point = np.asarray(point, dtype=np.float64)
    pts = np.repeat(point.reshape(1, 3), len(tris), axis=0)
    closest = trimesh.triangles.closest_point(np.asarray(tris, dtype=np.float64), pts)
    dist = np.linalg.norm(pts - closest, axis=1)
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    signed = np.einsum("ij,ij->i", point - closest, normals)
    k = int(np.argmin(dist))
    return float(dist[k]), float(signed[k]), closest[k]


def _min_wall(outer, cavity, tree=None, spans=None):
    """Thinnest distance from cavity vertices to the full-resolution outer surface.

    Uses a vertex tree and the faces around the nearest vertices, not a triangle rtree.
    Returns (millimetres or None, count of cavity samples that landed outside the shell).
    `tree` and `spans` belong to the outer shell and are reused across cavities and retries.
    """
    overts = np.ascontiguousarray(outer.vertices, dtype=np.float64)
    ofaces = np.ascontiguousarray(outer.faces, dtype=np.int64)
    cverts = np.ascontiguousarray(cavity.vertices, dtype=np.float64)
    if len(cverts) == 0 or len(ofaces) == 0:
        return None, 0
    k = min(16, len(overts))
    if tree is None:
        tree = cKDTree(overts)
    dist, nn = tree.query(cverts, k=k, workers=1)
    nearest = dist if dist.ndim == 1 else dist[:, 0]
    order = np.argsort(nearest)[:min(2500, len(cverts))]
    if spans is None:
        start, count, flat_f = _face_spans(ofaces, len(overts))
    else:
        start, count, flat_f = spans
    # Face normals flip on a wrinkle even when the sample is inside the solid.
    # The nearest vertex normal is the inside/outside test; the faces give the distance.
    normals = np.asarray(outer.vertex_normals, dtype=np.float64)
    worst = None
    outside = 0
    for i in order:
        vids = np.atleast_1d(nn[i])
        fis = _faces_of(vids, start, count, flat_f)
        if len(fis) == 0:
            continue
        d, _signed, _pt = _closest_clearance(cverts[i], overts[ofaces[fis]])
        nv = int(vids[0])
        if float(np.dot(cverts[i] - overts[nv], normals[nv])) > 0.5:
            outside += 1
            d = 0.0
        worst = d if worst is None else min(worst, d)
    return worst, outside


def _nearest_outer_point(outer, point, tree=None, spans=None):
    """Closest point of the full-resolution shell to `point`."""
    overts = np.ascontiguousarray(outer.vertices, dtype=np.float64)
    ofaces = np.ascontiguousarray(outer.faces, dtype=np.int64)
    if tree is None:
        tree = cKDTree(overts)
    _d, nn = tree.query(np.asarray(point, dtype=np.float64), k=min(16, len(overts)), workers=1)
    if spans is None:
        start, count, flat_f = _face_spans(ofaces, len(overts))
    else:
        start, count, flat_f = spans
    fis = _faces_of(nn, start, count, flat_f)
    if len(fis) == 0:
        return overts[int(np.atleast_1d(nn)[0])]
    _dist, _signed, hit = _closest_clearance(point, overts[ofaces[fis]])
    return hit


def _edge_counts(faces):
    if len(faces) == 0:
        return 0, 0
    edges = np.sort(np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _uniq, counts = np.unique(edges, axis=0, return_counts=True)
    return int(np.sum(counts == 1)), int(np.sum(counts > 2))


def _ray_first_t(origin, direction, verts, faces):
    """Distance to the first triangle a ray meets, or None. One pass, no triangle index."""
    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    e1 = v1 - v0
    e2 = v2 - v0
    pvec = np.cross(direction, e2)
    det = np.einsum("ij,ij->i", e1, pvec)
    ok = np.abs(det) > 1e-8
    inv = np.zeros(len(faces), dtype=np.float64)
    inv[ok] = 1.0 / det[ok]
    tvec = origin - v0
    u = np.einsum("ij,ij->i", tvec, pvec) * inv
    qvec = np.cross(tvec, e1)
    v = np.einsum("ij,j->i", qvec, direction) * inv
    t = np.einsum("ij,ij->i", e2, qvec) * inv
    hit = ok & (u >= 0.0) & (v >= 0.0) & (u + v <= 1.0) & (t > 1e-4)
    if not np.any(hit):
        return None
    return float(t[hit].min())


def _faces_along_hole(verts, faces, inner_pt, outer_pt, radius):
    """Triangles that can meet a ray down the drain. The rest cannot change the answer."""
    direction = outer_pt - inner_pt
    length = float(np.linalg.norm(direction))
    if length < 1e-8:
        return verts, faces
    direction = direction / length
    rel = verts - inner_pt
    along = rel @ direction
    radial = np.linalg.norm(rel - along[:, None] * direction, axis=1)
    near = (radial <= float(radius)) & (along >= -float(radius)) & (along <= length + float(radius))
    if not np.any(near):
        return verts, faces
    mask = near[faces].any(axis=1)
    if not np.any(mask):
        return verts, faces
    sub = faces[mask]
    used = np.unique(sub)
    remap = np.full(len(verts), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    return np.ascontiguousarray(verts[used]), np.ascontiguousarray(remap[sub])


def _hole_is_open(verts, faces, inner_pt, outer_pt):
    """True when the wall midpoint can see both out of the hole and into the cavity.

    A sealed wall is hit within about half the wall thickness. An open tunnel is clear
    at least that far in both directions.
    """
    inner_pt = np.asarray(inner_pt, dtype=np.float64)
    outer_pt = np.asarray(outer_pt, dtype=np.float64)
    verts = np.asarray(verts, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    direction = outer_pt - inner_pt
    length = float(np.linalg.norm(direction))
    if length < 1e-5:
        return False
    direction /= length
    if len(faces) > 20_000:
        verts, faces = _faces_along_hole(verts, faces, inner_pt, outer_pt, 6.0)
    mid = (inner_pt + outer_pt) * 0.5
    limit = max(length * 0.75, 0.4)
    # A straight axis can clip a jagged but still open tunnel. Accept the hole when any
    # line parallel to the axis, within the cutter, clears both the outside and the cavity.
    helper = np.array([1.0, 0.0, 0.0]) if abs(direction[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(direction, helper)
    u /= np.linalg.norm(u)
    v = np.cross(direction, u)
    clear = 0
    for ang in np.linspace(0.0, 2.0 * np.pi, 4, endpoint=False):
        offset = (u * np.cos(ang) + v * np.sin(ang)) * 0.35
        start = mid + offset
        outward = _ray_first_t(start, direction, verts, faces)
        inward = _ray_first_t(start, -direction, verts, faces)
        if (outward is None or outward > limit) and (inward is None or inward > limit):
            clear += 1
    return clear >= 1


def _drain_cylinder(inner_pt, outer_pt, radius):
    """Cylinder through one wall, or None when the segment is degenerate."""
    inner_pt = np.asarray(inner_pt, dtype=np.float64)
    outer_pt = np.asarray(outer_pt, dtype=np.float64)
    direction = outer_pt - inner_pt
    length = float(np.linalg.norm(direction))
    if length < 1e-5 or radius <= 0.0:
        return None
    direction = direction / length
    height = length + 2.0 * float(radius) + 1.2
    cyl = trimesh.creation.cylinder(radius=float(radius), height=height, sections=24)
    cyl.apply_transform(trimesh.geometry.align_vectors([0.0, 0.0, 1.0], direction))
    cyl.apply_translation((inner_pt + outer_pt) * 0.5)
    return cyl


def _union_cutters(meshes):
    """One solid from the drain cylinders. They do not overlap the outer shell's far vertices."""
    if len(meshes) == 1:
        return meshes[0]
    if manifold3d is None:
        raise OpError("Boolean operations need the 'manifold3d' package (pip install manifold3d).")
    parts = []
    for mesh in meshes:
        parts.append(_manifold_mesh(mesh))
    union = manifold3d.Manifold.batch_boolean(parts, manifold3d.OpType.Add)
    if union.status() != manifold3d.Error.NoError or union.is_empty():
        raise OpError("Could not hollow this shape. Try a thicker wall, or turn hollowing off.")
    out = union.to_mesh()
    return _new(np.asarray(out.vert_properties)[:, :3], np.asarray(out.tri_verts))


def _batch_punch(verts, faces, holes):
    """Cut every drain in one boolean, then keep the ray check along each hole.

    A 694k-triangle shell pays for the whole mesh on every boolean. One pass for
    all cylinders is the same cut as punching them one by one. Holes that stay
    blocked are omitted and the shell is cut once more without them.
    """
    source_v = np.asarray(verts, dtype=np.float64)
    source_f = np.asarray(faces, dtype=np.int64)
    pending = [(np.asarray(inner, dtype=np.float64), np.asarray(outer, dtype=np.float64), float(radius))
               for inner, outer, radius in holes]
    opened = [False] * len(pending)
    best_v, best_f = source_v, source_f
    if not pending:
        return source_v, source_f, opened
    for scale in (1.0, 1.35):
        if scale != 1.0 and all(opened):
            break
        tools = []
        which = []
        for i, (inner, outer, radius) in enumerate(pending):
            used = radius if opened[i] else radius * scale
            tool = _drain_cylinder(inner, outer, used)
            if tool is None:
                continue
            tools.append(tool)
            which.append(i)
        if not tools:
            break
        try:
            memtrim.trim()
            cut = _boolean(_new(source_v, source_f), _union_cutters(tools), "difference")
        except MemoryError:
            raise
        except OpError:
            continue
        cut_v = np.asarray(cut.vertices, dtype=np.float64)
        cut_f = np.asarray(cut.faces, dtype=np.int64)
        now = [False] * len(pending)
        for i in which:
            inner, outer, _radius = pending[i]
            now[i] = _hole_is_open(cut_v, cut_f, inner, outer)
        if sum(now) >= sum(opened) and any(now):
            best_v, best_f = cut_v, cut_f
            opened = now
        if all(opened[i] for i in which):
            break
    return best_v, best_f, opened


def _concat_cavity(outer, parts):
    """Outer shell plus each cavity flipped so its volume is the void. Vertices of `outer` are copied as they are."""
    blocks_v = [np.ascontiguousarray(outer.vertices, dtype=np.float64)]
    blocks_f = [np.ascontiguousarray(outer.faces, dtype=np.int64)]
    for part in parts:
        piece = part.copy()
        if piece.volume > 0:
            piece.invert()
        shift = sum(len(v) for v in blocks_v)
        blocks_v.append(np.ascontiguousarray(piece.vertices, dtype=np.float64))
        blocks_f.append(np.ascontiguousarray(piece.faces, dtype=np.int64) + shift)
    return np.vstack(blocks_v), np.vstack(blocks_f)


def _parse_drain_specs(p, drain):
    """User drain points as (x, y, z, diameter, direction or None)."""
    raw = p.get("drain_points") or []
    if raw and not isinstance(raw, list):
        raise OpError("drain_points must be a list of {x,y,z} or [x,y,z].")
    specs = []
    for i, pt in enumerate(raw):
        if isinstance(pt, dict):
            xyz = [pt.get("x"), pt.get("y"), pt.get("z")]
            diameter = float(pt.get("diameter", drain or 3))
            direc = pt.get("direction")
        elif isinstance(pt, (list, tuple)) and len(pt) >= 3:
            xyz = list(pt[:3])
            diameter = float(drain or 3)
            direc = None
        else:
            raise OpError(f"drain_points[{i}] must be {{x,y,z}} or [x,y,z].")
        try:
            xyz = [float(v) for v in xyz]
        except (TypeError, ValueError):
            raise OpError(f"drain_points[{i}] needs numeric x,y,z.")
        if diameter > 0:
            specs.append((xyz, diameter, direc))
    return specs


def _shell_volume(mm, parts, body):
    """Outer shell plus flipped cavities. Returns vertices, faces, and the shell volume."""
    verts, faces = _concat_cavity(mm, parts)
    shell_vol = float(_new(verts, faces).volume)
    if shell_vol <= 0.0 or (body > 0 and shell_vol >= body * 0.98):
        n_outer = len(mm.faces)
        faces = np.array(faces, copy=True)
        faces[n_outer:, :] = faces[n_outer:, ::-1]
        shell_vol = float(_new(verts, faces).volume)
    return verts, faces, shell_vol


def _open_shell_drains(mm, parts, wall, drain, p, body, tree, spans, stages=None):
    """Punch two drains per kept cavity. A cavity that does not open is left out of the shell."""
    per = int(p.get("per_cavity") or 0)
    specs = _parse_drain_specs(p, drain)
    need = min(per, 2) if per >= 1 and drain > 0 and not specs else 0
    active = list(parts)
    dropped_now = 0
    verts = faces = None
    holes_made = []
    axes = []
    shell_vol = 0.0
    marked_shell = False
    rounds = max(1, len(active))
    for _round in range(rounds):
        if not active:
            break
        verts, faces, shell_vol = _shell_volume(mm, active, body)
        if shell_vol <= 0.0 or (body > 0 and shell_vol >= body * 0.98):
            raise OpError("Could not build a hollow shell for this shape. Try a thicker wall.")
        if stages is not None and not marked_shell:
            stages.mark("shell", volume_mm3=round(shell_vol))
            marked_shell = True
        targets = []
        holes_made = []
        if specs:
            for xyz, diameter, direc in specs:
                inner_pt = None
                best = None
                for part in active:
                    dist = np.linalg.norm(np.asarray(part.vertices, dtype=np.float64) - xyz, axis=1)
                    k = int(np.argmin(dist))
                    if best is None or dist[k] < best:
                        best = float(dist[k])
                        inner_pt = np.asarray(part.vertices[k], dtype=np.float64)
                outer_pt = np.asarray(xyz, dtype=np.float64)
                if direc and len(direc) == 3:
                    axis = np.asarray(direc, dtype=np.float64)
                    norm = float(np.linalg.norm(axis))
                    if norm > 1e-8 and inner_pt is not None:
                        outer_pt = inner_pt + axis / norm * max(float(wall), 0.5)
                if inner_pt is not None:
                    targets.append((inner_pt, outer_pt, diameter / 2.0))
            groups = [list(range(len(targets)))]
        elif per >= 1 and drain > 0:
            groups = []
            for part in active:
                v = np.asarray(part.vertices, dtype=np.float64)
                picks = [v[int(np.argmin(v[:, 2]))], v[int(np.argmax(v[:, 2]))]][:per]
                groups.append(list(range(len(targets), len(targets) + len(picks))))
                for inner_pt in picks:
                    targets.append((np.asarray(inner_pt, dtype=np.float64), None, drain / 2.0))
        elif drain > 0:
            part = max(active, key=lambda c: c.volume)
            v = np.asarray(part.vertices, dtype=np.float64)
            targets.append((v[int(np.argmin(v[:, 2]))], None, drain / 2.0))
            groups = [list(range(len(targets)))]
        else:
            groups = []
        resolved = []
        for inner_pt, outer_pt, radius in targets:
            if outer_pt is None:
                outer_pt = _nearest_outer_point(mm, inner_pt, tree=tree, spans=spans)
            resolved.append((inner_pt, np.asarray(outer_pt, dtype=np.float64), radius))
        if resolved:
            verts, faces, oks = _batch_punch(verts, faces, resolved)
        else:
            oks = []
        made_counts = []
        axes = []
        for group in groups:
            n = 0
            for ti in group:
                if ti < len(oks) and oks[ti]:
                    n += 1
                    inner_pt, outer_pt, _radius = resolved[ti]
                    axes.append([[round(float(c), 3) for c in inner_pt], [round(float(c), 3) for c in outer_pt]])
            made_counts.append(n)
        holes_made = made_counts
        if need < 1 or not holes_made or all(n >= need for n in holes_made):
            break
        kept = [part for part, n in zip(active, holes_made) if n >= need]
        dropped_now += len(active) - len(kept)
        if not kept or len(kept) == len(active):
            active = kept
            break
        active = kept
    return verts, faces, shell_vol, holes_made, axes, active, dropped_now


def _left_solid(mm, pitch, stages, dropped=0):
    """The solid shell, with the note prepare shows when hollowing is not worth it."""
    stages.mark("left_solid", save_pct=0.0)
    return mm, {
        "message": "Left solid.",
        "resolution_mm": round(float(pitch), 3),
        "volume_saved_pct": 0.0,
        "left_solid": True,
        "note": LEFT_SOLID_NOTE,
        "cavity_fragments_dropped": int(dropped),
        "floating_pieces_dropped": 0,
        "thinnest_wall_mm": None,
        "holes_made": [],
        "stages": stages.rows,
    }


def _hollow_shell(mm, wall, drain, p):
    """Hollow a large mesh without booleaning or decimating the printed shell.

    The cavity is a coarse offset of a decimated proxy. It is flipped and concatenated
    with the original shell, which resin slicers treat as the solid between the two.
    Drain holes are cut locally and stitched, so the outer vertices away from the holes stay.
    """
    stages = _HollowStages()
    pitch = _shell_pitch(mm.extents, wall)
    stages.mark("pitch", pitch_mm=round(pitch, 3), faces=int(len(mm.faces)))
    proxy, simplified = _cavity_proxy(mm)
    gap = _proxy_outward_mm(mm, proxy) if simplified else 0.0
    stages.mark("proxy", faces=int(len(proxy.faces)), outward_mm=round(gap, 2))
    sdf, vox, filled = _proxy_sdf(proxy, pitch)
    body = abs(float(mm.volume))
    vox_vol = filled * float(pitch) ** 3
    if body > 0 and (vox_vol < 0.35 * body or vox_vol > 1.45 * body):
        del sdf, vox
        memtrim.trim()
        stages.mark("proxy_leak", vox_mm3=round(vox_vol))
        sdf, vox, filled = _proxy_sdf(mm, pitch)
        gap = 0.0
        vox_vol = filled * float(pitch) ** 3
        if body > 0 and (vox_vol < 0.35 * body or vox_vol > 1.45 * body):
            # The sheet is too thin for this grid. Hollowing it would not be an honest cavity.
            del sdf, vox
            memtrim.trim()
            return _left_solid(mm, pitch, stages, 0)
    stages.mark("sdf", cells=int(sdf.size), mb=round(sdf.nbytes / (1024.0 * 1024.0), 1))
    del proxy
    floor = float(wall) - pitch
    target = float(wall) - 0.25 * pitch
    base_offset = float(wall) + min(float(wall), max(0.0, gap)) + 0.5 * pitch
    offset = base_offset
    parts = None
    wall_min = None
    dropped = 0
    outside = 0
    save_est = 0.0
    stop_solid = False
    overts = np.ascontiguousarray(mm.vertices, dtype=np.float64)
    shell_tree = cKDTree(overts)
    shell_spans = _face_spans(np.ascontiguousarray(mm.faces, dtype=np.int64), len(overts))
    for attempt in range(4):
        cav = _cavity_from_sdf(sdf, vox, pitch, offset)
        if cav is None or len(cav.faces) == 0:
            stop_solid = True
            stages.mark("cavity", attempt=attempt, offset_mm=round(offset, 2), empty=True)
            break
        parts, dropped = _cavity_parts(cav, wall)
        if parts:
            parts = _merge_cavity_parts(parts, float(pitch))
        if not parts:
            stop_solid = True
            stages.mark("cavity", attempt=attempt, offset_mm=round(offset, 2), kept=0, dropped=int(dropped))
            break
        save_est = 100.0 * sum(float(part.volume) for part in parts) / body if body > 0.0 else 0.0
        wall_min = None
        outside = 0
        for part in parts:
            measured, n_out = _min_wall(mm, part, tree=shell_tree, spans=shell_spans)
            outside += n_out
            if measured is not None:
                wall_min = measured if wall_min is None else min(wall_min, measured)
        wall_ok = wall_min is not None and wall_min + 1e-6 >= target and outside == 0
        broke = outside > 0 or (wall_min is not None and wall_min < 0.35)
        far = offset > base_offset + float(wall)
        stages.mark(
            "cavity", attempt=attempt, faces=int(sum(len(part.faces) for part in parts)),
            wall_mm=None if wall_min is None else round(wall_min, 2),
            offset_mm=round(offset, 2), outside=int(outside),
            save_pct=round(save_est, 1), kept=len(parts),
        )
        # A deeper offset only shrinks the void. Stop once the shell is thin,
        # or the wall only appears after the inset has moved well past the request.
        if wall_ok and save_est + 1e-6 < MIN_HOLLOW_SAVE_PCT:
            stop_solid = True
            break
        if wall_ok:
            break
        if save_est + 1e-6 < MIN_HOLLOW_SAVE_PCT and (not broke or attempt >= 1):
            stop_solid = True
            break
        if far and (broke or save_est < MIN_HOLLOW_SAVE_PCT + 5.0):
            stop_solid = True
            break
        if attempt == 3:
            break
        short = target - (wall_min if wall_min is not None else 0.0)
        step = max(pitch * 0.5, short + 0.05 * pitch, pitch if outside else 0.0)
        # A cavity that breaks the surface only needs a small pull-back. A big
        # jump shrinks a thin relief until the void is not worth keeping.
        if broke and save_est < 40.0:
            step = min(step, pitch * 0.5)
        if save_est < 25.0:
            room = base_offset + float(wall) - offset
            if room <= 0.05:
                stop_solid = True
                break
            step = min(step, room)
        offset += step
    if stop_solid:
        del sdf, vox
        memtrim.trim()
        return _left_solid(mm, pitch, stages, dropped)
    del sdf, vox
    memtrim.trim()
    if parts is None or wall_min is None or wall_min < floor or outside:
        # Still breaking through after the allowed inset. Leave the solid rather
        # than ship a cavity that crosses the surface.
        if outside or wall_min is None or wall_min < 0.35:
            return _left_solid(mm, pitch, stages, dropped)
        raise OpError("Could not keep the wall thickness on this shape. Try a thicker wall.")
    if sum(len(part.faces) for part in parts) > CAVITY_FACE_CAP * 3:
        raise MemoryError("hollow cavity does not fit in the prepare memory budget")
    verts, faces, shell_vol, holes_made, axes, parts, missed = _open_shell_drains(
        mm, parts, wall, drain, p, body, shell_tree, shell_spans, stages)
    dropped += missed
    if not parts or verts is None:
        return _left_solid(mm, pitch, stages, dropped)
    out = _new(verts, faces)
    out.remove_unreferenced_vertices()
    shell_vol = float(out.volume)
    saved = 100.0 * (1.0 - shell_vol / body) if shell_vol > 0.0 and body > 0.0 else 0.0
    stages.mark("drain", holes=list(holes_made), open_edges=_edge_counts(out.faces)[0])
    memtrim.trim()
    n_holes = sum(holes_made)
    rep = {
        "message": (f"hollowed: wall {wall:g} mm, volume −{saved:.0f}% (resolution ≈ {pitch:.2f} mm)"
                    + (f", {n_holes} drain hole(s)" if n_holes else "")),
        "resolution_mm": round(pitch, 3),
        "volume_saved_pct": round(saved, 1),
        "cavity_fragments_dropped": int(dropped),
        "floating_pieces_dropped": 0,
        "thinnest_wall_mm": None if wall_min is None else round(float(wall_min), 2),
        "stages": stages.rows,
    }
    if holes_made:
        rep["holes_made"] = holes_made
    if axes:
        rep["drain_axes"] = axes
    if wall_min is not None and wall_min < 0.75 * wall:
        rep["note"] = (f"The thinnest wall is about {wall_min:.1f} mm, less than the {wall:g} mm you asked for "
                       "(thin or very detailed parts of the shape). It may print badly: try a thicker wall or check it in your slicer.")
    return out, rep


def _ray_wall(m, n=1500):
    """1st-percentile wall from inward rays at surface samples (the QA probe). None if it can't be measured."""
    try:
        pts, fi = trimesh.sample.sample_surface(m, n, seed=1)
        nn = m.face_normals[fi]; org = pts - nn * 0.02
        # Cast in small batches: trimesh's fallback ray engine builds per-ray candidate arrays, and 1500 rays at once
        # on a ~300k-face hollow model took many GB (the TorchC0 "too big or complex" 422 on ordinary 9 MB STLs).
        ds = []
        for i in range(0, len(org), 20):
            loc, ir, _ = m.ray.intersects_location(org[i:i + 20], -nn[i:i + 20], multiple_hits=False)
            ds.append(np.linalg.norm(loc - org[i:i + 20][ir], axis=1))
        d = np.concatenate(ds) if ds else np.zeros(0)
        return (float(np.percentile(d, 1)), float(d.min())) if len(d) else None
    except Exception:
        return None


def _close_cavity(cav):
    """Make a large marching-cubes cavity a solid. Holes bigger than a quad are left open.

    Fan-filling a boundary of a clipped isosurface builds a self-intersecting sheet.
    Manifold then aborted (SIGSEGV) instead of returning an error.
    """
    cav.merge_vertices()
    cav.update_faces(cav.nondegenerate_faces())
    cav.remove_unreferenced_vertices()
    if len(cav.faces) == 0 or not np.isfinite(cav.vertices).all():
        raise OpError("Could not build a clean cavity for this shape. Try a different wall thickness.")
    trimesh.repair.fix_normals(cav, multibody=True)
    if not cav.is_watertight:
        trimesh.repair.fill_holes(cav, use_fan=False)
    if len(cav.faces) and cav.volume < 0:
        cav.invert()
    return cav


def _hollow_from(mm, sdf, vox, pitch, wall, drain, p, extra=0.0, tries=0):
    field = np.ascontiguousarray(sdf - (wall + extra))                       # cavity = points deeper than `wall` (+ margin on retries)
    if field.max() <= 0:
        raise OpError("Nothing left to hollow with this wall thickness.")
    verts, faces, _, _ = skimage_measure.marching_cubes(field, 0.0, spacing=(pitch, pitch, pitch))
    # grid index -> world (voxel transform, minus the 2-voxel pad)
    idx = verts / pitch - 2
    world = trimesh.transform_points(idx, vox.transform)
    del field, verts, idx
    cav = _new(world, faces[:, ::-1])
    del world, faces
    large = len(mm.faces) > 80_000 or len(cav.faces) > 150_000
    if large:
        # sdf stays alive for a possible retry. Trim the voxel step's freed arenas
        # before the boolean so Manifold can allocate under the prepare cap.
        memtrim.trim()
        cav = _close_cavity(cav)
    else:
        cav.merge_vertices(); trimesh.repair.fix_normals(cav); trimesh.repair.fill_holes(cav)
    if cav.volume < 0:
        cav.invert()
    if not cav.is_watertight or len(cav.faces) == 0:
        raise OpError("Could not build a clean cavity for this shape. Try a different wall thickness.")
    # marching cubes leaves hundreds of tiny disconnected cavity fragments on thin/detailed shapes: each would become a sealed void
    # (trapped air, slicer artefacts). Keep only cavity pieces big enough to matter; say how many were dropped.
    min_cav = (1.5 * wall) ** 3
    all_parts = [c for c in cav.split(only_watertight=False) if c.volume > 0]
    parts = [c for c in all_parts if c.volume >= min_cav]
    dropped = len(all_parts) - len(parts)
    if not parts:
        raise OpError("Nothing left to hollow with this wall thickness (only tiny pockets would remain). Try a thinner wall.")
    cav = trimesh.util.concatenate(parts) if len(parts) > 1 else parts[0]
    out = _boolean(mm, cav, "difference")
    # User-placed drain holes: list of {x,y,z} (or [x,y,z]) on the outer surface.
    # Each punches a cylinder of diameter `drain` (or per-hole diameter) inward along -Z by default,
    # or along `direction` if given. Falls back to one auto hole at the cavity floor when drain>0 and no points.
    drain_points = p.get("drain_points") or []
    if drain_points and not isinstance(drain_points, list):
        raise OpError("drain_points must be a list of {x,y,z} or [x,y,z].")
    holes = []
    for i, pt in enumerate(drain_points):
        if isinstance(pt, dict):
            xyz = [pt.get("x"), pt.get("y"), pt.get("z")]
            d_i = float(pt.get("diameter", drain or 3))
            direc = pt.get("direction")
        elif isinstance(pt, (list, tuple)) and len(pt) >= 3:
            xyz = list(pt[:3]); d_i = float(drain or 3); direc = None
        else:
            raise OpError(f"drain_points[{i}] must be {{x,y,z}} or [x,y,z].")
        try:
            xyz = [float(v) for v in xyz]
        except (TypeError, ValueError):
            raise OpError(f"drain_points[{i}] needs numeric x,y,z.")
        if d_i <= 0:
            continue
        holes.append((xyz, d_i, direc))
    if not holes and drain > 0 and int(p.get("per_cavity") or 0) < 1:
        low = cav.vertices[cav.vertices[:, 2] < cav.bounds[0][2] + pitch * 1.5]
        xy = low[:, :2].mean(0)
        holes.append(([xy[0], xy[1], float(mm.bounds[0][2])], drain, None))
    for xyz, d_i, direc in holes:
        if direc and len(direc) == 3:
            n = np.asarray(direc, float)
            n = n / (np.linalg.norm(n) or 1)
        else:
            n = np.array([0.0, 0.0, -1.0])  # punch downward by default (resin drain)
        length = float(np.linalg.norm(mm.extents)) * 0.6 + wall * 2 + 2.0
        cyl = trimesh.creation.cylinder(radius=d_i / 2, height=length, sections=48)
        # Align cylinder +Z to n
        T = trimesh.geometry.align_vectors([0, 0, 1], n)
        cyl = _transform(_new(cyl.vertices, cyl.faces), T)
        # Centre of cylinder at xyz, extending both ways so it breaks the wall
        cyl = _new(cyl.vertices + np.asarray(xyz, float), cyl.faces)
        out = _boolean(out, cyl, "difference")
    out, floating = _drop_slivers(out, min_cav)
    wall_min = _measure_wall(mm, cav)
    probe = _ray_wall(out)
    floor = wall - pitch                                                     # what a voxel method can promise
    if ((probe and probe[0] < floor) or (wall_min is not None and wall_min < floor)) and tries < 2:                             # enforce the minimum: deepen the margin and rebuild
        return _hollow_from(mm, sdf, vox, pitch, wall, drain, p, extra + pitch, tries + 1)
    # Large prepares punch drain+vent here from the cavity we already have, so
    # prepare does not have to split the hollowed mesh again (that hit the cap).
    holes_made = []
    per = int(p.get("per_cavity") or 0)
    if per >= 1 and drain > 0 and not (p.get("drain_points") or []):
        del sdf, vox
        memtrim.trim()
        from scipy.spatial import cKDTree
        tree = cKDTree(np.ascontiguousarray(mm.vertices, dtype=np.float64))
        for cav_part in parts:
            v = cav_part.vertices
            targets = [v[np.argmin(v[:, 2])], v[np.argmax(v[:, 2])]][:per]
            n = 0
            for t in targets:
                _dist, idx = tree.query(np.asarray(t, dtype=np.float64), workers=1)
                cp = np.ascontiguousarray(mm.vertices, dtype=np.float64)[int(idx)]
                d = cp - t
                L = float(np.linalg.norm(d))
                if L < 1e-6:
                    continue
                axis = d / L
                h = L + 2 * drain + 1.0
                cyl = trimesh.creation.cylinder(radius=drain / 2, height=h, sections=32)
                T = trimesh.geometry.align_vectors([0, 0, 1], axis)
                T[:3, 3] = t + axis * (L / 2)
                cyl.apply_transform(T)
                try:
                    out = _boolean(out, cyl, "difference")
                    n += 1
                except OpError:
                    pass
            holes_made.append(n)
    rep_extra = {"cavity_fragments_dropped": dropped, "floating_pieces_dropped": floating,
                 "thinnest_wall_mm": None if wall_min is None else round(wall_min, 2)}
    if holes_made:
        rep_extra["holes_made"] = holes_made
    if probe:
        rep_extra["wall_p1_mm"], rep_extra["wall_min_probe_mm"] = round(probe[0], 2), round(probe[1], 2)
    if probe and probe[1] < floor:
        rep_extra["warning"] = (f"Some walls are thinner than the {wall:g} mm you asked for: the thinnest spot measured is {probe[1]:.2f} mm "
                                f"(1% of the surface is under {probe[0]:.2f} mm). Those spots may print badly or break: try a thicker wall, or check them in your slicer.")
        rep_extra["note"] = rep_extra["warning"]
    elif wall_min is not None and wall_min < 0.75 * wall:
        rep_extra["note"] = (f"The thinnest wall is about {wall_min:.1f} mm, less than the {wall:g} mm you asked for "
                             "(thin or very detailed parts of the shape). It may print badly: try a thicker wall or check it in your slicer.")
    saved = 100 * (1 - out.volume / mm.volume) if out.volume > 0 else 0
    if len(out.faces) > 100_000:
        memtrim.trim()
    n_holes = len(holes) or sum(holes_made)
    return out, {"message": f"hollowed: wall {wall:g} mm, volume −{saved:.0f}% (resolution ≈ {pitch:.2f} mm)"
                 + (f", {n_holes} drain hole(s)" if n_holes else ""), "resolution_mm": round(pitch, 3),
                 "volume_saved_pct": round(saved, 1), **rep_extra}


# ------------------------------------------------------------------ text
FONTS = {"sans": ("DejaVu Sans", "normal"), "sans-bold": ("DejaVu Sans", "bold"),
         "serif": ("DejaVu Serif", "normal"), "serif-bold": ("DejaVu Serif", "bold"),
         "mono": ("DejaVu Sans Mono", "normal"),
         "mono-bold": ("DejaVu Sans Mono", "bold"),
         "liberation-sans": ("Liberation Sans", "normal"),
         "liberation-serif": ("Liberation Serif", "normal"),
         "liberation-mono": ("Liberation Mono", "normal")}
# Extra TTF paths (bundled or user-uploaded under data/fonts/). Key = font id for the UI.
CUSTOM_FONT_DIRS = [
    Path(__file__).resolve().parents[2] / "data" / "fonts",
    Path(__file__).resolve().parents[2] / "static" / "fonts",
]


def list_fonts() -> list[str]:
    """Built-in + any *.ttf / *.otf found in CUSTOM_FONT_DIRS (stem as id)."""
    ids = list(FONTS)
    seen = set(ids)
    for d in CUSTOM_FONT_DIRS:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.ttf")) + sorted(d.glob("*.otf")):
            key = f.stem.lower().replace(" ", "-")
            if key not in seen:
                ids.append(key); seen.add(key)
    return ids


def _font_prop(font: str):
    """matplotlib FontProperties for a built-in id or a custom TTF path."""
    from matplotlib.font_manager import FontProperties
    if font in FONTS:
        fam, weight = FONTS[font]
        return FontProperties(family=fam, weight=weight)
    # custom file
    for d in CUSTOM_FONT_DIRS:
        for ext in (".ttf", ".otf", ".TTF", ".OTF"):
            cand = d / f"{font}{ext}"
            if cand.is_file():
                return FontProperties(fname=str(cand))
            # allow stem match ignoring case
        if d.is_dir():
            for f in d.iterdir():
                if f.suffix.lower() in (".ttf", ".otf") and f.stem.lower().replace(" ", "-") == font:
                    return FontProperties(fname=str(f))
    fam, weight = FONTS["sans"]
    return FontProperties(family=fam, weight=weight)
# face -> (normal, u (text right), v (text up)); right-handed so text reads correctly seen from outside
FACES = {"top": ([0, 0, 1], [1, 0, 0], [0, 1, 0]), "bottom": ([0, 0, -1], [1, 0, 0], [0, -1, 0]),
         "front": ([0, -1, 0], [1, 0, 0], [0, 0, 1]), "back": ([0, 1, 0], [-1, 0, 0], [0, 0, 1]),
         "left": ([-1, 0, 0], [0, -1, 0], [0, 0, 1]), "right": ([1, 0, 0], [0, 1, 0], [0, 0, 1])}


def text_polygon(text: str, font: str, height: float):
    """Text outline as a shapely (Multi)Polygon, capital-letter height = `height` mm, centred on (0,0)."""
    from matplotlib.textpath import TextPath
    from shapely.geometry import Polygon
    from shapely import affinity
    fp = _font_prop(font)
    cap = TextPath((0, 0), "H", size=100, prop=fp).get_extents().height
    tp = TextPath((0, 0), text, size=100 * height / cap, prop=fp)
    rings = [r for r in tp.to_polygons(closed_only=True) if len(r) >= 3]
    if not rings:
        raise OpError("That text has no printable outlines (try letters/numbers).")
    geom = None
    for r in rings:                      # even-odd fill → holes in O, A, 8 …
        pg = Polygon(r).buffer(0)
        geom = pg if geom is None else geom.symmetric_difference(pg)
    minx, miny, maxx, maxy = geom.bounds
    return affinity.translate(geom, -(minx + maxx) / 2, -(miny + maxy) / 2)


def op_text(m, p):
    """Emboss/deboss text on a BB face, or on a tapped surface point (curved-surface text).

    placement: "face" (default, flat BB face) | "surface" (point + normal from a click)
    wrap: when True on surface, sample the mesh near the text baseline so glyphs follow curvature
          (approximate; works best on gently curved surfaces).
    """
    txt = str(p.get("text", "")).strip()
    if not txt or len(txt) > 60:
        raise OpError("Text must be 1–60 characters.")
    if any(ord(c) < 32 for c in txt):
        raise OpError("Text contains control characters.")
    height = _num(p, "height", 8, 1, 500); depth = _num(p, "depth", 1, 0.1, 100)
    mode = p.get("mode", "emboss")
    if mode not in ("emboss", "deboss"):
        raise OpError("mode must be emboss|deboss")
    ou, ov = _num(p, "offset_u", 0), _num(p, "offset_v", 0)
    rot = _num(p, "rotation", 0, -360, 360)
    poly = text_polygon(txt, p.get("font", "sans"), height)
    placement = (p.get("placement") or "face").lower()
    wrap = bool(p.get("wrap") or p.get("curved"))
    overlap = 0.3
    z0, z1 = (-overlap, depth) if mode == "emboss" else (-depth, overlap + 0.2)
    polys = [g for g in (poly.geoms if hasattr(poly, "geoms") else [poly]) if g.area > 1e-6]
    note_bits = []

    if placement == "surface":
        pt = p.get("point") or p.get("position")
        nrm = p.get("normal")
        if not pt or not nrm:
            raise OpError("Surface text needs point [x,y,z] and normal [x,y,z] from a click on the model.")
        face_pt = np.asarray(pt, float).reshape(3)
        n = np.asarray(nrm, float).reshape(3)
        ln = np.linalg.norm(n)
        if ln < 1e-9 or not np.isfinite(face_pt).all():
            raise OpError("Surface point/normal is invalid.")
        n = n / ln
        # Local frame
        a = np.zeros(3); a[int(np.argmin(np.abs(n)))] = 1.0
        u = np.cross(n, a); u /= (np.linalg.norm(u) or 1)
        v = np.cross(n, u)
        a_rad = math.radians(rot)
        ca, sa = math.cos(a_rad), math.sin(a_rad)
        u2 = ca * u + sa * v
        v2 = -sa * u + ca * v
        u, v = u2, v2
        if wrap and len(m.faces) and len(m.faces) < 500_000:
            # Project each glyph polygon onto the nearest surface (ray from offset along -n)
            tools = []
            for g in polys:
                # Centroid of glyph in UV
                cx, cy = g.centroid.x + ou, g.centroid.y + ov
                origin = face_pt + u * cx + v * cy + n * (max(m.extents) * 0.05 + 2)
                # Ray toward the model
                loc, ri, ti = m.ray.intersects_location([origin], [-n], multiple_hits=False)
                if len(loc):
                    hit = loc[0]
                    hn = m.face_normals[ti[0]]
                    # Rebuild local frame at hit
                    aa = np.zeros(3); aa[int(np.argmin(np.abs(hn)))] = 1.0
                    hu = np.cross(hn, aa); hu /= (np.linalg.norm(hu) or 1)
                    hv = np.cross(hn, hu)
                    # Keep text "up" roughly aligned with v
                    if np.dot(hv, v) < 0:
                        hu, hv = -hu, -hv
                    solid = trimesh.creation.extrude_polygon(g, z1 - z0)
                    verts = solid.vertices + [0, 0, z0]
                    # Centre glyph at its own centroid so hit is the glyph centre
                    verts = verts - [g.centroid.x, g.centroid.y, 0]
                    world = hit + np.outer(verts[:, 0], hu) + np.outer(verts[:, 1], hv) + np.outer(verts[:, 2], hn)
                    f = solid.faces
                    if np.linalg.det(np.array([hu, hv, hn])) < 0:
                        f = f[:, ::-1]
                    tools.append(_new(world, f))
                else:
                    # Fallback: flat at face_pt
                    solid = trimesh.creation.extrude_polygon(g, z1 - z0)
                    verts = solid.vertices + [0, 0, z0]
                    x = verts[:, 0] + ou; y = verts[:, 1] + ov
                    world = face_pt + np.outer(x, u) + np.outer(y, v) + np.outer(verts[:, 2], n)
                    tools.append(_new(world, solid.faces))
            tool = trimesh.util.concatenate(tools) if len(tools) > 1 else tools[0]
            note_bits.append("Curved-surface wrap: each letter follows the nearest surface (approximate).")
        else:
            solid = trimesh.util.concatenate([trimesh.creation.extrude_polygon(g, z1 - z0) for g in polys])
            verts = solid.vertices + [0, 0, z0]
            x = verts[:, 0] + ou; y = verts[:, 1] + ov
            world = face_pt + np.outer(x, u) + np.outer(y, v) + np.outer(verts[:, 2], n)
            f = solid.faces
            if np.linalg.det(np.array([u, v, n])) < 0:
                f = f[:, ::-1]
            tool = _new(world, f)
            note_bits.append("Surface text at the clicked point (flat on the local tangent).")
        out = _boolean(m, tool, "union" if mode == "emboss" else "difference")
        return out, {"message": f"{mode} “{txt}” on surface", "note": " ".join(note_bits), "placement": "surface"}

    # --- classic BB-face placement ---
    face = p.get("face", "top")
    if face not in FACES:
        raise OpError("face one of " + "|".join(FACES))
    n, u, v = (np.array(x, float) for x in FACES[face])
    lo, hi = _bounds(m); c = (lo + hi) / 2
    half = (hi - lo) / 2
    face_pt = c + n * np.abs(n * half).sum()
    solid = trimesh.util.concatenate([trimesh.creation.extrude_polygon(g, z1 - z0) for g in polys])
    verts = solid.vertices + [0, 0, z0]
    a = math.radians(rot)
    x = verts[:, 0] * math.cos(a) - verts[:, 1] * math.sin(a) + ou
    y = verts[:, 0] * math.sin(a) + verts[:, 1] * math.cos(a) + ov
    world = face_pt + np.outer(x, u) + np.outer(y, v) + np.outer(verts[:, 2], n)
    f = solid.faces
    if np.linalg.det(np.array([u, v, n])) < 0:
        f = f[:, ::-1]
    tool = _new(world, f)
    hu, hv = float(np.abs(u * half).sum()), float(np.abs(v * half).sum())
    tx0, tx1, ty0, ty1 = float(x.min()), float(x.max()), float(y.min()), float(y.max())
    if tx1 < -hu or tx0 > hu or ty1 < -hv or ty0 > hv:
        raise OpError("The text is completely off this face, so it would not touch the model. Move it back with the shift boxes, or make it smaller.")
    overhang = tx0 < -hu - 1e-6 or tx1 > hu + 1e-6 or ty0 < -hv - 1e-6 or ty1 > hv + 1e-6
    out = _boolean(m, tool, "union" if mode == "emboss" else "difference")
    nominal = sum(g.area for g in polys) * depth
    if mode == "deboss" and abs(float(m.volume) - float(out.volume)) < 1e-4 * max(nominal, 1e-9):
        raise OpError("Nothing was cut: the text doesn't reach the model here (it may be over a curved or sloped part). Move it, or use emboss.")
    floating = 0
    if mode == "emboss" and len(m.faces) < 400_000 and len(out.faces) < 400_000:
        floating = len(out.split(only_watertight=False)) - len(m.split(only_watertight=False))
        if floating >= len(polys):
            raise OpError("The raised text would float free of the model (it doesn't touch it here), so it was not added. Move it onto the model or make it smaller.")
    note = "Text is placed on the flat bounding-box face; on curved/sloped surfaces it may float or sink. Use placement=surface for a clicked point."
    if overhang:
        note = (f"Part of the text goes past the edge of the {face} face ({2 * hu:.0f} × {2 * hv:.0f} mm), so only the part over the model is "
                + ("added" if mode == "emboss" else "cut") + (", and the raised part that overhangs hangs in the air" if mode == "emboss" else "") + ". " + note)
    if floating > 0:
        note = f"{floating} separate piece{'s' if floating != 1 else ''} of the text (e.g. letters over a curved part) do not touch the model and would float in the air. Make the text smaller or move it. " + note
    return out, {"message": f"{mode} “{txt}” on {face}", "note": note, "placement": "face"}



def op_lay_flat(m, p):
    from . import orient
    return orient.lay_flat(m)


def op_best_orient(m, p):
    from . import orient
    return orient.best_position(m)


def op_smart_split(m, p):
    from . import smartsplit
    return smartsplit.smart_split(m, p)


def op_thread(m, p):
    from . import cadthread
    return cadthread.op_thread(m, p)


def op_plate(m, p):
    from . import plate
    try:
        return plate.apply(m, p)
    except plate.PlateError as e:
        raise OpError(str(e))


from . import parts        # the parts builder op (bottom of this table): recipe -> mesh
from . import voxremesh
from . import sculpt    # the voxel-remesh op: one-click watertight rebuild

OPS = {"plate": op_plate, "lay_flat": op_lay_flat, "best_orient": op_best_orient, "smart_split": op_smart_split, "translate": op_translate, "rotate": op_rotate, "scale": op_scale, "mirror": op_mirror, "place": op_place,
       "repair": op_repair, "simplify": op_simplify, "cut": op_cut, "hollow": op_hollow, "base": op_base,
       "boolean": op_boolean, "text": op_text, "on_face": op_on_face, "thread": op_thread,
       "parts": parts.op_parts,        # the parts builder (app/core/parts.py): recipe -> mesh
       "voxremesh": voxremesh.op_voxremesh,   # voxel remesh (app/core/voxremesh.py): watertight rebuild
       "sculpt": sculpt.op_sculpt}             # sculpt brushes (app/core/sculpt.py): smooth/flatten/inflate
from . import cadops as _cadops                 # CAD workspace solids (app/core/cadops.py): extrude/revolve/fillet/pattern...
if hasattr(_cadops, "OPS"):                   # (when cadops is imported first it registers itself at its end)
    OPS.update(_cadops.OPS)


def label(op: str, p: dict) -> str:
    g = lambda k, d="": p.get(k, d)
    if op in getattr(_cadops, "OPS", ()):
        return _cadops.label(op, p) or op
    try:
        return {
            "translate": lambda: f"Move ({g('dx', 0):g}, {g('dy', 0):g}, {g('dz', 0):g}) mm",
            "rotate": lambda: f"Rotate ({g('rx', 0):g}°, {g('ry', 0):g}°, {g('rz', 0):g}°)",
            "scale": lambda: "Scale ×" + ("%g" % g('factor') if p.get('factor') is not None else f"({g('sx', 1):.3g}, {g('sy', 1):.3g}, {g('sz', 1):.3g})"),
            "mirror": lambda: f"Mirror {str(g('axis')).upper()}",
            "place": lambda: "Drop to bed" + (" + centre" if p.get("center_xy") else ""),
            "parts": lambda: f"Parts ({len((p.get('parts') or []))} primitives)",
            "voxremesh": lambda: "Voxel remesh (watertight rebuild)",
            "sculpt": lambda: f"Sculpt {str(g('brush', 'smooth')).title()} ({g('radius', 0):g} mm brush)",
            "repair": lambda: "Fix / repair",
            "lay_flat": lambda: "Lay flat",
            "best_orient": lambda: "Best position (least overhang)",
            "smart_split": lambda: f"Smart Split ({g('mode', 'auto')}, join={g('join', 'glue')})",
            "simplify": lambda: f"Simplify (keep {g('keep_ratio', 0.5) * 100:.0f}%)",
            "cut": lambda: f"Cut {str(g('axis', 'plane')).upper()}={g('position', '')} keep {g('keep', 'above')}",
            "hollow": lambda: f"Hollow {g('wall', 2):g} mm wall" + (f" + Ø{g('drain_diameter'):g} drain" if p.get('drain_diameter') else ""),
            "base": lambda: f"Add base ({g('style', 'outline')}, {g('thickness', 2):g} mm)",
            "boolean": lambda: f"{str(g('kind')).title()} {(p.get('primitive') or {}).get('type', '')}",
            "on_face": lambda: ("Add " if g("mode", "add") == "add" else "Cut ") + ("outline" if g("shape", "box") == "polygon" else f"Ø{g('diameter', 10):g} hole/cyl" if g("shape", "box") == "cylinder" else f"{g('width', 10):g}×{g('depth', 10):g} box") + f", {g('height', 10):g} mm on face",
            "text": lambda: f"{str(g('mode', 'emboss')).title()} “{g('text')}”",
            "thread": lambda: f"Thread M{g('diameter', 6):g} {g('mode', 'add')}",
            "import": lambda: str(g("label", "Import")),
            "plate": lambda: __import__("app.core.plate", fromlist=["label"]).label(p),
        }[op]()
    except Exception:
        return op


# Ops whose memory/time can blow up with mesh size: run under the runtime ceiling (core/guard.py).
HEAVY_OPS = {"remesh", "pattern", "round_edges", "body_boolean", "boolean", "simplify", "sketch_extrude",
             "revolve", "repair", "hollow", "shell", "smooth", "subdivide", "thicken",
             # CADRT-9: the rest of the CAD / sculpt ops too (cheap per op, but unbounded on big meshes)
             "align", "face_offset", "body_transform", "sculpt_stroke", "sculpt", "scale", "cut", "smart_split", "thread",
             "mirror", "translate", "rotate", "merge_bodies", "smart_merge"}
HEAVY_MIN_FACES = 20_000          # tiny meshes are not worth a separate process


def apply(m: trimesh.Trimesh, op: str, params: dict) -> tuple[trimesh.Trimesh, dict]:
    fn = OPS.get(op)
    if not fn:
        raise OpError(f"unknown operation '{op}'")
    if op in HEAVY_OPS and len(m.faces) >= HEAVY_MIN_FACES:
        from . import guard
        try:
            out, rep = guard.run(fn, m, params or {})
        except guard.Busy:
            raise OpError("The server is busy with other heavy steps right now. Please try again in a moment.")
        except guard.Tripped:
            raise OpError("That step needs more memory or time than this server allows for one step, "
                          "so it was stopped and your model is unchanged. Try a smaller value, fewer copies, "
                          "or Simplify first.")
    else:
        out, rep = fn(m, params or {})
    return _cadops.preserve_body_ids(m, _check(out)), rep


# ------------------------------------------------------------------ import / validation
ALLOWED = {"stl", "obj", "3mf"}
IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "bmp", "gif", "heic", "heif"}


def sniff(data: bytes, ext: str) -> str:
    """Validate that the bytes really are what the extension claims. Returns '' or an error message."""
    if ext == "stl":
        if len(data) >= 84:
            n = int.from_bytes(data[80:84], "little")
            if 84 + 50 * n == len(data):
                return ""
        head = data[:1024].lstrip().lower()
        if head.startswith(b"solid") and b"facet" in data[:4096].lower():
            return ""
        return "This doesn't look like a valid STL file (neither binary nor ASCII STL)."
    if ext == "obj":
        try:
            txt = data[:65536].decode("utf-8", "strict") if True else ""
        except UnicodeDecodeError:
            try:
                txt = data[:65536].decode("latin-1")
            except Exception:
                return "This doesn't look like a text OBJ file."
        if any(ord(ch) < 9 for ch in txt):
            return "This doesn't look like a text OBJ file (binary data found)."
        if "\nv " not in "\n" + txt:
            return "No vertices found — not a valid OBJ file."
        return ""
    if ext == "3mf":
        if not data.startswith(b"PK"):
            return "This isn't a 3MF (zip) file."
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            names = z.namelist()
            if not any(n.lower().endswith(".model") for n in names):
                return "3MF has no 3D model part."
            infos = z.infolist()
            total = sum(i.file_size for i in infos)
            packed = sum(i.compress_size for i in infos) or 1
            extra = sum(i.file_size for i in infos if not i.filename.lower().endswith(".model"))
            if total > 128 * 1024 * 1024 or len(infos) > 200:
                return "3MF expands to an unreasonable size (possible zip bomb)."
            if extra > 16 * 1024 * 1024 or (total > 8 * 1024 * 1024 and total / packed > 200):
                return "3MF has a suspiciously large packed member (possible zip bomb). Re-export it from your slicer."
        except zipfile.BadZipFile:
            return "Corrupt 3MF (bad zip)."
        return ""
    return f"Unsupported file type .{ext}"


_3MF_MIMES = ("model/3mf", "application/vnd.ms-package.3dmanufacturing-3dmodel+xml")


def guess_model_ext(name: str, data: bytes, mime: str = "") -> str:
    """Work out which 3D format an upload is, trusting the CONTENT over the name.
    iPhones/iPads hand files over with odd names: 'part.3mf.zip', 'part.gcode.3mf', no extension at all, or a 3MF
    (which is a zip package) typed application/zip or application/octet-stream. Returns 'stl'/'obj'/'3mf' or ''."""
    n = (name or "").lower().strip()
    ext = n.rsplit(".", 1)[-1] if "." in n else ""
    if ext in ALLOWED:
        return ext
    if n.endswith((".3mf.zip", ".3mf.bin")) or (mime or "").lower() in _3MF_MIMES:
        return "3mf"
    if data[:2] == b"PK" and not sniff(data, "3mf"):
        return "3mf"
    if ext in IMAGE_EXT:
        return ""
    for e in ("stl", "obj"):
        if not sniff(data, e):
            return e
    return ""


def _3mf_unit_scale(data: bytes) -> float:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        name = next(n for n in z.namelist() if n.lower().endswith(".model"))
        head = z.read(name)[:2000].decode("utf-8", "ignore")
        import re
        mt = re.search(r'unit="(\w+)"', head)
        return {"micron": 0.001, "millimeter": 1.0, "centimeter": 10.0, "inch": 25.4, "foot": 304.8, "meter": 1000.0}.get(mt.group(1), 1.0) if mt else 1.0
    except Exception:
        return 1.0


def size_warnings(size_mm: float) -> list[str]:
    """The 'is that the right unit?' hint for a model whose largest side is `size_mm` (already in mm)."""
    if size_mm < 2:
        return [f"The model is only {size_mm:.3g} mm across — if it should be bigger, re-import with units set to inch/cm/m."]
    if size_mm > 1500:
        return [f"The model is {size_mm:.0f} mm across — if that's wrong, re-import with units set to mm/in correctly."]
    return []


def load_document(data: bytes, ext: str, units_scale: float = 1.0, mtl: bytes | None = None, *,
                  split_shells: bool = False) -> tuple[trimesh.Trimesh, list[dict], list[str]]:
    """One mesh plus the part list (name, colour, source material, face runs).

    `meshparts` imports this module, so the import stays inside the function.
    `split_shells` is only for the editor: STL is never auto-split, and a large
    3MF/OBJ is not walked for shells.
    """
    from .meshparts import load_document as _load
    return _load(data, ext, units_scale, mtl, split_shells=split_shells)


def load_mesh(data: bytes, ext: str, units_scale: float = 1.0) -> tuple[trimesh.Trimesh, list[str]]:
    """Parse STL/OBJ/3MF into ONE mesh (mm). Part colours are not returned here.

    Slicing, repair, and resin use this and still receive a single mesh. The editor uses
    `load_document`, which keeps the part list. `units_scale` is the factor the caller will
    apply for the user's chosen units (e.g. 25.4 for inches; ignored for 3MF, which declares
    its own). The mesh is returned unscaled, but the size warning is judged on the converted
    size, so a 1 in cube imported as inches is not called "only 1 mm across" (QA B9).
    """
    mesh, parts, warnings = load_document(data, ext, units_scale, split_shells=False)
    if len(parts) > 1:
        warnings = [*warnings, f"{len(parts)} objects were merged into one mesh (colours/materials are not kept)."]
    return mesh, warnings
