"""Mesh editing operations (trimesh / numpy / scipy / shapely; booleans via manifold3d when installed).

Every operation is a pure function  (mesh, params) -> (new_mesh, report)  working in MILLIMETRES, Z up.
Projects store the ORIGINAL upload untouched plus a list of {op, params}; the current mesh is the replay of
that list (see services/editproj.py), which is what makes undo / redo / jump-to-step non-destructive.
"""
from __future__ import annotations

import io
import math
import zipfile

import numpy as np
import trimesh

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
    try:
        import skimage  # noqa: F401
        return have_boolean()
    except Exception:
        return False


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
    f = p.get("factor")
    sx, sy, sz = ((_num(p, k, f if f is not None else 1.0, 1e-3, 1e3)) for k in ("sx", "sy", "sz"))
    pivot = p.get("pivot", "base")
    lo, hi = _bounds(m)
    c = {"origin": np.zeros(3), "center": (lo + hi) / 2,
         "base": np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])}.get(pivot)
    if c is None:
        raise OpError("pivot must be base | center | origin")
    S = np.diag([sx, sy, sz, 1.0])
    out = _transform(m, _mat_translate(c) @ S @ _mat_translate(-c))
    if max(out.extents) > 5000:
        raise OpError("Result would be larger than 5 m — check your units.")
    return out, {}


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
            steps.append(f"dropped {len(parts) - 1} small floating piece(s)")
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
    a = _prep_solid(a); b = _prep_solid(b, "tool shape")
    try:
        r = {"union": trimesh.boolean.union, "difference": trimesh.boolean.difference,
             "intersection": trimesh.boolean.intersection}[kind]([a, b], engine="manifold")
    except Exception as e:
        raise OpError(f"Boolean failed: {e}")
    if r is None or len(r.faces) == 0:
        raise OpError("The result is empty (shapes may not overlap).")
    return _check(_new(r.vertices, r.faces))


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
    return out, {"message": f"kept {keep}; {len(parts)} piece(s)" + ((" · " + warn) if warn else ""), "warning": warn, "watertight": bool(out.is_watertight)}


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


def op_hollow(m, p):
    """Hollow with wall thickness via a distance field (voxel SDF → marching cubes → boolean difference).
    Accuracy is ~ one voxel, shown in the report. Optional drain hole at the lowest point of the cavity."""
    if not have_hollow():
        raise OpError("Hollow needs 'manifold3d' and 'scikit-image'.")
    from scipy import ndimage
    from skimage import measure
    wall = _num(p, "wall", 2, 0.2, 100); drain = _num(p, "drain_diameter", 0, 0, 100)
    mm = _prep_solid(m)
    ext = mm.extents
    if wall * 2.2 >= ext.min():
        raise OpError(f"Wall {wall:g} mm is too thick for this model (thinnest side is {ext.min():.1f} mm). "
                      "Lithophanes and thin plates can't be hollowed.")
    pitch = max(wall / 3.0, float((np.prod(ext + 2 * wall) / 6e6) ** (1 / 3)))
    if pitch > wall / 1.5:
        raise OpError(f"Wall {wall:g} mm is too thin for a model this big (needs ≈{pitch * 1.5:.1f} mm+). "
                      "Increase the wall or scale the model down first.")
    vox = mm.voxelized(pitch).fill()
    inside = np.pad(vox.matrix, 2)
    d_in = ndimage.distance_transform_edt(inside) * pitch
    d_out = ndimage.distance_transform_edt(~inside) * pitch
    sdf = np.where(inside, d_in - 0.5 * pitch, -(d_out - 0.5 * pitch))      # +ve inside, ≈ signed distance to surface
    return _hollow_from(mm, sdf, vox, pitch, wall, drain, p)


def _ray_wall(m, n=1500):
    """1st-percentile wall from inward rays at surface samples (the QA probe). None if it can't be measured."""
    try:
        pts, fi = trimesh.sample.sample_surface(m, n, seed=1)
        nn = m.face_normals[fi]; org = pts - nn * 0.02
        loc, ir, _ = m.ray.intersects_location(org, -nn, multiple_hits=False)
        d = np.linalg.norm(loc - org[ir], axis=1)
        return (float(np.percentile(d, 1)), float(d.min())) if len(d) else None
    except Exception:
        return None


def _hollow_from(mm, sdf, vox, pitch, wall, drain, p, extra=0.0, tries=0):
    from skimage import measure
    field = sdf - (wall + extra)                                             # cavity = points deeper than `wall` (+ margin on retries)
    if field.max() <= 0:
        raise OpError("Nothing left to hollow with this wall thickness.")
    verts, faces, _, _ = measure.marching_cubes(field, 0.0, spacing=(pitch, pitch, pitch))
    # grid index -> world (voxel transform, minus the 2-voxel pad)
    idx = verts / pitch - 2
    world = trimesh.transform_points(idx, vox.transform)
    cav = _new(world, faces[:, ::-1])
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
    if drain > 0:
        low = cav.vertices[cav.vertices[:, 2] < cav.bounds[0][2] + pitch * 1.5]
        xy = low[:, :2].mean(0)
        z0 = mm.bounds[0][2] - 1.0; z1 = cav.bounds[0][2] + wall * 0.5 + pitch
        cyl = trimesh.creation.cylinder(radius=drain / 2, height=z1 - z0, sections=48)
        cyl = _new(cyl.vertices + [xy[0], xy[1], (z0 + z1) / 2], cyl.faces)
        out = _boolean(out, cyl, "difference")
    out, floating = _drop_slivers(out, min_cav)
    wall_min = _measure_wall(mm, cav)
    probe = _ray_wall(out)
    floor = wall - pitch                                                     # what a voxel method can promise
    if ((probe and probe[0] < floor) or (wall_min is not None and wall_min < floor)) and tries < 2:                             # enforce the minimum: deepen the margin and rebuild
        return _hollow_from(mm, sdf, vox, pitch, wall, drain, p, extra + pitch, tries + 1)
    rep_extra = {"cavity_fragments_dropped": dropped, "floating_pieces_dropped": floating,
                 "thinnest_wall_mm": None if wall_min is None else round(wall_min, 2)}
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
    return out, {"message": f"hollowed: wall {wall:g} mm, volume −{saved:.0f}% (resolution ≈ {pitch:.2f} mm)"
                 + (f", drain hole Ø{drain:g}" if drain else ""), "resolution_mm": round(pitch, 3),
                 "volume_saved_pct": round(saved, 1), **rep_extra}


# ------------------------------------------------------------------ text
FONTS = {"sans": ("DejaVu Sans", "normal"), "sans-bold": ("DejaVu Sans", "bold"),
         "serif": ("DejaVu Serif", "normal"), "serif-bold": ("DejaVu Serif", "bold"),
         "mono": ("DejaVu Sans Mono", "normal")}
# face -> (normal, u (text right), v (text up)); right-handed so text reads correctly seen from outside
FACES = {"top": ([0, 0, 1], [1, 0, 0], [0, 1, 0]), "bottom": ([0, 0, -1], [1, 0, 0], [0, -1, 0]),
         "front": ([0, -1, 0], [1, 0, 0], [0, 0, 1]), "back": ([0, 1, 0], [-1, 0, 0], [0, 0, 1]),
         "left": ([-1, 0, 0], [0, -1, 0], [0, 0, 1]), "right": ([1, 0, 0], [0, 1, 0], [0, 0, 1])}


def text_polygon(text: str, font: str, height: float):
    """Text outline as a shapely (Multi)Polygon, capital-letter height = `height` mm, centred on (0,0)."""
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextPath
    from shapely.geometry import Polygon
    from shapely import affinity
    fam, weight = FONTS.get(font, FONTS["sans"])
    fp = FontProperties(family=fam, weight=weight)
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
    txt = str(p.get("text", "")).strip()
    if not txt or len(txt) > 60:
        raise OpError("Text must be 1–60 characters.")
    if any(ord(c) < 32 for c in txt):
        raise OpError("Text contains control characters.")
    height = _num(p, "height", 8, 1, 500); depth = _num(p, "depth", 1, 0.1, 100)
    mode = p.get("mode", "emboss")
    face = p.get("face", "top")
    if mode not in ("emboss", "deboss") or face not in FACES:
        raise OpError("mode must be emboss|deboss and face one of " + "|".join(FACES))
    ou, ov = _num(p, "offset_u", 0), _num(p, "offset_v", 0)
    rot = _num(p, "rotation", 0, -360, 360)
    poly = text_polygon(txt, p.get("font", "sans"), height)
    n, u, v = (np.array(x, float) for x in FACES[face])
    lo, hi = _bounds(m); c = (lo + hi) / 2
    half = (hi - lo) / 2
    face_pt = c + n * np.abs(n * half).sum()                 # centre of the bounding-box face
    overlap = 0.3
    z0, z1 = (-overlap, depth) if mode == "emboss" else (-depth, overlap + 0.2)
    polys = [g for g in (poly.geoms if hasattr(poly, "geoms") else [poly]) if g.area > 1e-6]
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
    # Where does the text sit on the face? (QA-6: text pushed past the face used to be accepted as "success")
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
    note = "Text is placed on the flat bounding-box face; on curved/sloped surfaces it may float or sink."
    if overhang:
        note = (f"Part of the text goes past the edge of the {face} face ({2 * hu:.0f} × {2 * hv:.0f} mm), so only the part over the model is "
                + ("added" if mode == "emboss" else "cut") + (", and the raised part that overhangs hangs in the air" if mode == "emboss" else "") + ". " + note)
    if floating > 0:
        note = f"{floating} separate piece{'s' if floating != 1 else ''} of the text (e.g. letters over a curved part) do not touch the model and would float in the air. Make the text smaller or move it. " + note
    return out, {"message": f"{mode} “{txt}” on {face}", "note": note}


def op_lay_flat(m, p):
    from . import orient
    return orient.lay_flat(m)


def op_best_orient(m, p):
    from . import orient
    return orient.best_position(m)


def op_smart_split(m, p):
    from . import smartsplit
    return smartsplit.smart_split(m, p)


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
       "boolean": op_boolean, "text": op_text, "on_face": op_on_face,
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
            "import": lambda: str(g("label", "Import")),
            "plate": lambda: __import__("app.core.plate", fromlist=["label"]).label(p),
        }[op]()
    except Exception:
        return op


# Ops whose memory/time can blow up with mesh size: run under the runtime ceiling (core/guard.py).
HEAVY_OPS = {"remesh", "pattern", "round_edges", "body_boolean", "boolean", "simplify", "sketch_extrude",
             "revolve", "repair", "hollow", "shell", "smooth", "subdivide", "thicken",
             # CADRT-9: the rest of the CAD / sculpt ops too (cheap per op, but unbounded on big meshes)
             "align", "face_offset", "body_transform", "sculpt_stroke", "sculpt", "scale", "cut", "smart_split",
             "mirror", "translate", "rotate"}
HEAVY_MIN_FACES = 20_000          # tiny meshes are not worth a fork


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
    return _check(out), rep


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


def load_mesh(data: bytes, ext: str, units_scale: float = 1.0) -> tuple[trimesh.Trimesh, list[str]]:
    """Parse STL/OBJ/3MF into ONE mesh (mm). Multiple objects are merged (colours/materials are dropped).
    `units_scale` is the factor the caller will apply for the user's chosen units (e.g. 25.4 for inches; ignored
    for 3MF, which declares its own). The mesh is returned unscaled, but the size warning is judged on the
    converted size, so a 1 in cube imported as inches is not called "only 1 mm across" (QA B9)."""
    warnings = []
    ft = ext.lower()
    try:
        obj = trimesh.load(io.BytesIO(data), file_type=ft, process=False, force="scene" if ft == "3mf" else "mesh",
                           skip_materials=True) if ft != "3mf" else trimesh.load(io.BytesIO(data), file_type=ft, process=False)
    except Exception as e:
        raise OpError(f"Could not read the {ft.upper()} file: {e}")
    if isinstance(obj, trimesh.Scene):
        geoms = [g for g in obj.dump() if isinstance(g, trimesh.Trimesh)]       # applies build transforms
        if not geoms:
            raise OpError("The file contains no triangle meshes.")
        if len(geoms) > 1:
            warnings.append(f"{len(geoms)} objects were merged into one mesh (colours/materials are not kept).")
        mesh = trimesh.util.concatenate(geoms)
    else:
        mesh = obj
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise OpError("The file contains no triangles (maybe it is a curve/point file).")
    if len(mesh.faces) > MAX_FACES:
        raise OpError(f"{len(mesh.faces):,} triangles is above the {MAX_FACES:,} limit.")
    mesh = _new(mesh.vertices, mesh.faces)
    mesh.merge_vertices()
    if not np.isfinite(mesh.vertices).all():
        raise OpError("File contains invalid coordinates.")
    k = 1.0
    if ft == "3mf":
        k = _3mf_unit_scale(data)
        if k != 1.0:
            mesh = _new(mesh.vertices * k, mesh.faces)
            warnings.append(f"3MF declared units; converted to mm (×{k:g}).")
    size = float(mesh.extents.max()) * (1.0 if ft == "3mf" else float(units_scale or 1.0))
    warnings += size_warnings(size)
    return mesh, warnings
