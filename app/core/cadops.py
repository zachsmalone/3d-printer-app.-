"""CAD workspace solid operations, recorded as ordinary edit-project history steps.

Original ZEIM code. Geometry kernel: manifold3d (Apache-2.0) for extrude / revolve / booleans /
Minkowski; shapely (BSD) for sketch regions. Every op here is a pure function mesh -> mesh
registered in meshedit.OPS, so undo/redo, step editing with replay, exports, slicing and the
plate editor work unchanged.

"Bodies" are the connected pieces of the project mesh (numbered by their position: sorted by
centre x, then y, then z, so numbering is predictable). Body references in a step are indices
into that order at the time the step is replayed; editing an earlier step can renumber them.
"""
from __future__ import annotations

import math

import numpy as np
import trimesh

from . import sketch as sk
from .meshedit import OpError, _check, _new

MAX_PATTERN = 64
MAX_PATTERN_FACES = 600_000      # refuse BEFORE fusing: input faces x count (memory grows with it)
MAX_ROUND_FACES = 60_000         # Minkowski fillet/chamfer cost explodes on dense meshes
LIM = 5000.0


def _num(p, k, d, lo, hi):
    v = p.get(k, d)
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise OpError(f"{k} must be a number.")
    if not math.isfinite(v) or not lo <= v <= hi:
        raise OpError(f"{k} must be between {lo:g} and {hi:g}.")
    return v


def _vec(p, k, d=(0, 0, 0), lim=LIM):
    v = p.get(k, d)
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        raise OpError(f"{k} must be [x, y, z].")
    return np.array([_num({"v": x}, "v", 0, -lim, lim) for x in v])


# ------------------------------------------------------------------ kernel bridges
def _to_manifold(m: trimesh.Trimesh):
    import manifold3d as mf
    if len(m.faces) == 0:
        return mf.Manifold()
    mm = m.copy(); mm.merge_vertices()
    out = mf.Manifold(mf.Mesh(vert_properties=np.asarray(mm.vertices, np.float32), tri_verts=np.asarray(mm.faces, np.uint32)))
    if out.status() != mf.Error.NoError:
        raise OpError("This body isn't a closed solid, so solid tools can't use it. Run Fix / repair first.")
    if out.volume() < 0 or (mm.is_watertight and mm.volume < 0):
        raise OpError("This body is inside-out (negative volume). Run Fix mesh first so solid tools work correctly.")
    return out


def _solid_or_none(x, n_bodies: int):
    """Manifold -> trimesh that stays a closed 2-manifold after vertex merging (as every export does), else None."""
    t = _from_manifold(x)
    mm = trimesh.Trimesh(t.vertices.copy(), t.faces.copy(), process=False)
    mm.merge_vertices()
    if not mm.is_watertight:                  # sliver faces collapse to zero length when merged: drop + close the pin-holes
        mm.update_faces(mm.nondegenerate_faces())
        mm.update_faces(mm.unique_faces())
        mm.remove_unreferenced_vertices()
        trimesh.repair.fill_holes(mm)
        trimesh.repair.fix_normals(mm)
    if len(mm.faces) == 0 or not (mm.is_watertight and mm.is_winding_consistent):
        return None
    if len(bodies(mm)) != n_bodies:
        return None
    return mm


def _from_manifold(x) -> trimesh.Trimesh:
    mesh = x.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3]
    f = np.asarray(mesh.tri_verts)
    return _new(v, f)


def bodies(m: trimesh.Trimesh) -> list[trimesh.Trimesh]:
    if len(m.faces) == 0:
        return []
    mm = m.copy(); mm.merge_vertices()
    shells = list(mm.split(only_watertight=False))
    # an inside-out shell is a hollow (cavity) of the solid around it: keep it with that body
    solid = [b for b in shells if not (b.is_watertight and b.volume < 0)]
    voids = [b for b in shells if b.is_watertight and b.volume < 0]
    groups = [[b] for b in solid]
    for v in voids:
        c = v.bounds.mean(axis=0)
        host = [i for i, b in enumerate(solid) if (b.bounds[0] <= c).all() and (c <= b.bounds[1]).all()]
        if host:
            groups[min(host, key=lambda i: np.prod(solid[i].extents))].append(v)
        else:
            groups.append([v])
    parts = [g[0] if len(g) == 1 else _join_all(g) for g in groups]
    return sorted(parts, key=lambda b: tuple(np.round(b.bounds.mean(axis=0), 3)))


def _join_all(ms):
    out = None
    for x in ms:
        out = _join(out, x)
    return out


def body_info(m: trimesh.Trimesh) -> list[dict]:
    out = []
    for i, b in enumerate(bodies(m)):
        out.append({"index": i, "name": f"Body {i + 1}", "triangles": int(len(b.faces)),
                    "center": np.round(b.bounds.mean(axis=0), 3).tolist(), "size": np.round(b.extents, 3).tolist(),
                    "volume_mm3": round(float(abs(b.volume)), 3) if b.is_watertight else None})
    return out


def _pick(m, p, key="body"):
    """(selected mesh, the rest) for p[key] = body index, or -1 / missing = everything."""
    i = p.get(key, -1)
    try:
        i = int(i)
    except (TypeError, ValueError):
        raise OpError(f"{key} must be a body number.")
    if i < 0:
        return m, None
    bs = bodies(m)
    if i >= len(bs):
        raise OpError(f"There is no Body {i + 1} (the model has {len(bs)}).")
    rest = [b for k, b in enumerate(bs) if k != i]
    return bs[i], (trimesh.util.concatenate(rest) if rest else None)


def _join(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return _new(np.vstack([a.vertices, b.vertices]), np.vstack([a.faces, b.faces + len(a.vertices)]))


def _touching(m) -> bool:
    """True if separate bodies share a face/edge exactly (after vertex merge some edges get >2 faces)."""
    mm = trimesh.Trimesh(m.vertices, m.faces, process=False); mm.merge_vertices()
    if len(mm.faces) == 0:
        return False
    _, cnt = np.unique(mm.edges_sorted, axis=0, return_counts=True)
    return bool((cnt > 2).any())


def _join_sep(a, b, hint="Use Union (Join) instead, or leave a small gap."):
    """Keep b as separate bodies next to a, but refuse a result that would not be a clean solid
    (bodies touching face-to-face become non-manifold when the file is saved). QA B2."""
    out = _join(a, b)
    if a is not None and b is not None and len(a.faces) and len(b.faces) and _touching(out):
        raise OpError("The new body would touch another body face-to-face, which can't be kept as two separate "
                      "solids in a print file. " + hint)
    return out


def _combine(cur, tool, mode, replace=False):
    """Apply a new solid to the model: new (separate body) / join / cut / intersect."""
    if replace or len(cur.faces) == 0:
        if mode in ("cut", "intersect"):
            raise OpError("There is nothing to cut yet - make a solid first.")
        return tool
    if mode == "new":
        return _join_sep(cur, tool)
    a, b = _to_manifold(cur), _to_manifold(tool)
    r = {"join": a + b, "cut": a - b, "intersect": a ^ b}.get(mode)
    if r is None:
        raise OpError("mode must be new | join | cut | intersect")
    if r.is_empty():
        raise OpError("The result is empty (do the shapes overlap?).")
    return _from_manifold(r)


def _frame(o, xd, yd, n):
    T = np.eye(4)
    T[:3, 0], T[:3, 1], T[:3, 2], T[:3, 3] = xd, yd, n, o
    return T


def _cross_section(params):
    import manifold3d as mf
    try:
        sketch = sk.check(params.get("sketch") or {})
        if params.get("solve", True) and sketch["constraints"]:
            sketch = sk.solve(sketch)["sketch"]
        g = sk.regions(sketch, params.get("picks") or None)
    except sk.SketchError as e:
        raise OpError(str(e))
    if g is None:
        raise OpError("The sketch has no closed shape to use. Close the outline (end where you started) or draw a rectangle/circle.")
    polys = list(g.geoms) if hasattr(g, "geoms") else [g]
    rings = []
    for pg in polys:
        rings.append(np.asarray(pg.exterior.coords)[:-1])
        rings += [np.asarray(h.coords)[:-1] for h in pg.interiors]
    return mf.CrossSection([r.astype(np.float64) for r in rings], mf.FillRule.EvenOdd), sketch


# ------------------------------------------------------------------ ops
def op_sketch_extrude(m, p):
    """Extrude closed sketch regions. direction: up | down | both (symmetric); mode: new | join | cut | intersect."""
    import manifold3d as mf
    d = _num(p, "distance", 10, 0.001, LIM)
    direction = p.get("direction", "up")
    if direction not in ("up", "down", "both"):
        raise OpError("direction must be up | down | both")
    try:
        o, xd, yd, n = sk.plane(p.get("plane", "XY"))
    except sk.SketchError as e:
        raise OpError(str(e))
    cs, _ = _cross_section(p)
    taper = _num(p, "taper", 0, -60, 60)
    top = 1.0
    if taper:
        b = cs.bounds(); half = max(b[2] - b[0], b[3] - b[1]) / 2 or 1
        top = max(0.0, 1 - d * math.tan(math.radians(taper)) / half)
    solid = mf.Manifold.extrude(cs, d, 0, 0.0, (top, top))
    z0 = {"up": 0.0, "down": -d, "both": -d / 2}[direction]
    solid = solid.translate((0, 0, z0))
    T = _frame(o, xd, yd, n)
    tool = _from_manifold(solid.transform(T[:3, :]))
    out = _combine(m, tool, p.get("mode", "new"), bool(p.get("replace")))
    return out, {"message": f"Extruded {d:g} mm ({direction}, {p.get('mode', 'new')})."}


def op_revolve(m, p):
    """Revolve sketch regions about an axis line in the sketch plane: axis = {p:[x,y], d:[dx,dy]}."""
    import manifold3d as mf
    ang = _num(p, "angle", 360, 0.1, 360)
    try:
        o, xd, yd, n = sk.plane(p.get("plane", "XY"))
    except sk.SketchError as e:
        raise OpError(str(e))
    ax = p.get("axis") or {"p": [0, 0], "d": [0, 1]}
    try:
        ap = np.array(sk._pt(ax.get("p", [0, 0]), "axis point")); ad = np.array(sk._pt(ax.get("d", [0, 1]), "axis direction"))
    except (sk.SketchError, AttributeError) as e:
        raise OpError(str(e))
    if np.linalg.norm(ad) < 1e-9:
        raise OpError("axis direction can't be zero.")
    ad = ad / np.linalg.norm(ad)
    cs, _ = _cross_section(p)
    # move the profile into "axis = +Y through origin" coordinates; profile must be on one side
    perp = np.array([ad[1], -ad[0]])
    R2 = np.array([[perp[0], perp[1]], [ad[0], ad[1]]])          # rows: new x = perp, new y = axis
    rings = [(np.asarray(r) - ap) @ R2.T for r in cs.to_polygons()]
    xs = np.concatenate([r[:, 0] for r in rings])
    if xs.min() < -1e-6 and xs.max() > 1e-6:
        raise OpError("The profile crosses the axis. Keep the whole shape on one side of the axis line.")
    flip = xs.max() <= 1e-6
    if flip:
        rings = [r * np.array([-1, 1]) for r in rings]
        perp = -perp
    solid = mf.Manifold.revolve(mf.CrossSection(rings, mf.FillRule.EvenOdd), 0, ang)
    # revolve: profile X -> radial, profile Y -> world Z of the result. Map back: Z -> axis, X -> perp
    ax3 = xd * ad[0] + yd * ad[1]; perp3 = xd * perp[0] + yd * perp[1]
    third = np.cross(ax3, perp3)
    origin = o + xd * ap[0] + yd * ap[1]
    T = np.eye(4); T[:3, 0], T[:3, 1], T[:3, 2], T[:3, 3] = perp3, -third, ax3, origin
    tool = _from_manifold(solid.transform(T[:3, :]))
    out = _combine(m, tool, p.get("mode", "new"), bool(p.get("replace")))
    return out, {"message": f"Revolved {ang:g}°."}


def op_body_boolean(m, p):
    """Union / subtract / intersect two bodies (target keeps; tool is consumed)."""
    kind = p.get("kind", "union")
    if kind not in ("union", "subtract", "intersect"):
        raise OpError("kind must be union | subtract | intersect")
    bs = bodies(m)
    try:
        a, b = int(p.get("target", 0)), int(p.get("tool", 1))
    except (TypeError, ValueError):
        raise OpError("target/tool must be body numbers.")
    if a == b or not (0 <= a < len(bs)) or not (0 <= b < len(bs)):
        raise OpError(f"Pick two different bodies (the model has {len(bs)}).")
    A, B = _to_manifold(bs[a]), _to_manifold(bs[b])
    r = {"union": A + B, "subtract": A - B, "intersect": A ^ B}[kind]
    rest = [x for k, x in enumerate(bs) if k not in (a, b)]
    res = _from_manifold(r) if not r.is_empty() else None
    out = None
    for x in rest + ([res] if res is not None else []):
        out = _join(out, x)
    if out is None:
        raise OpError("The result is empty.")
    return out, {"message": f"Boolean {kind}."}


def _edge_capsules(edges, r):
    import manifold3d as mf
    caps = None
    for e in edges:
        a, b = np.array(e[0], float), np.array(e[1], float)
        L = float(np.linalg.norm(b - a))
        if L < 1e-6:
            continue
        cyl = mf.Manifold.cylinder(L, 1.5 * r, 1.5 * r, 32)   # neighbouring edges blend within 1.5 r of the ends
        z = (b - a) / L
        ref = np.array([1.0, 0, 0]) if abs(z[0]) < 0.9 else np.array([0, 1.0, 0])
        x = np.cross(ref, z); x /= np.linalg.norm(x); y = np.cross(z, x)
        T = np.eye(4); T[:3, 0], T[:3, 1], T[:3, 2], T[:3, 3] = x, y, z, a
        c = cyl.transform(T[:3, :])
        caps = c if caps is None else caps + c
    return caps


def op_round_edges(m, p):
    """Fillet (round) or chamfer convex edges by morphological opening (Minkowski with a ball or
    an octahedron). APPROXIMATE: concave (inside) corners are not filleted; the ball is faceted.
    edges = [[[x,y,z],[x,y,z]], ...] limits it to the picked edges; empty = every convex edge."""
    import manifold3d as mf
    r = _num(p, "radius", 1, 0.05, 50)
    style = p.get("style", "fillet")
    if style not in ("fillet", "chamfer"):
        raise OpError("style must be fillet | chamfer")
    sel, rest = _pick(m, p)
    if len(sel.faces) > MAX_ROUND_FACES:
        raise OpError(f"Fillet/chamfer works on bodies up to {MAX_ROUND_FACES:,} triangles (this one has {len(sel.faces):,}). Simplify first.")
    if max(sel.extents) / r > 400:
        raise OpError("The radius is tiny compared with the body; use at least 1/400 of its size.")
    if 2 * r >= min(sel.extents):
        raise OpError(f"Radius {r:g} mm is too big for this body (thinnest side {min(sel.extents):.1f} mm).")
    A = _to_manifold(sel)
    if style == "fillet":
        tool = mf.Manifold.sphere(r, 24)
    else:
        v = np.array([[r, 0, 0], [-r, 0, 0], [0, r, 0], [0, -r, 0], [0, 0, r], [0, 0, -r]], np.float32)
        tool = mf.Manifold.hull_points(v)
    try:
        opened = A.minkowski_difference(tool).minkowski_sum(tool)
    except Exception as e:
        raise OpError(f"Rounding failed on this shape: {e}")
    if opened.is_empty():
        raise OpError("The radius removes the whole body.")
    opened_raw = opened
    opened = opened ^ A                       # never grow past the original faces
    edges = p.get("edges") or []
    if edges:
        if not isinstance(edges, list) or len(edges) > 64:
            raise OpError("edges must be a list of up to 64 [[x,y,z],[x,y,z]] pairs.")
        try:
            caps = _edge_capsules([[list(map(float, e[0]))[:3], list(map(float, e[1]))[:3]] for e in edges], r)
        except (TypeError, ValueError, IndexError):
            raise OpError("edges must be [[x,y,z],[x,y,z]] pairs.")
        if caps is not None:
            opened = A - ((A - opened) ^ caps)
    out = None
    nb = len(bodies(sel))
    cands = [opened] + ([opened_raw] if not edges else [])   # the ^A clip can leave coplanar slivers; the raw opening is already inside A up to facets
    for cand in cands:
        for tol in (1e-3, 5e-3, 2e-2, 5e-2, 0):       # merge the near-coincident sliver vertices Minkowski leaves behind
            out = _solid_or_none(cand.simplify(tol), nb)
            if out is not None:
                break
        if out is not None:
            break
    if out is None:                           # QA B3: never hand back a non-manifold mesh
        raise OpError("The rounded result wouldn't be a clean closed solid on this shape, so it was not applied. "
                      "Try a smaller radius or pick fewer edges.")
    return _join(out, rest), {"message": f"{style.title()} {r:g} mm (approximate, convex edges)."}


def op_face_offset(m, p):
    """Push/pull one flat face along its normal by `distance` (the face's connected coplanar region)."""
    d = _num(p, "distance", 1, -LIM, LIM)
    pt, nrm = _vec(p, "point"), _vec(p, "normal", (0, 0, 1), 10)
    if np.linalg.norm(nrm) < 1e-9:
        raise OpError("normal can't be zero.")
    nrm = nrm / np.linalg.norm(nrm)
    mm = m.copy(); mm.merge_vertices()
    fn = mm.face_normals
    cent = mm.triangles_center
    ok = (fn @ nrm > 0.999) & (np.abs((cent - pt) @ nrm) < 1e-3 * max(1.0, float(mm.scale)))
    if not ok.any():
        raise OpError("No flat face found there. Tap a flat face.")
    cand = np.nonzero(ok)[0]
    seed = cand[np.argmin(np.linalg.norm(cent[cand] - pt, axis=1))]
    # grow the connected coplanar region from the seed face
    adj = mm.face_adjacency
    nb = {}
    for a, b in adj:
        if ok[a] and ok[b]:
            nb.setdefault(a, []).append(b); nb.setdefault(b, []).append(a)
    region, stack = {seed}, [seed]
    while stack:
        f = stack.pop()
        for g in nb.get(f, []):
            if g not in region:
                region.add(g); stack.append(g)
    verts = np.unique(mm.faces[list(region)])
    v = mm.vertices.copy()
    v[verts] += nrm * d
    out = _new(v, mm.faces)
    if mm.is_watertight and out.volume <= 0:
        raise OpError("That offset turns the body inside out.")
    return out, {"message": f"Face moved {d:g} mm ({len(region)} triangles)."}


def _xform_matrix(p, center):
    T = trimesh.transformations.translation_matrix(-center)
    s = _vec(p, "scale", (1, 1, 1), 1000)
    if (s <= 0).any():
        raise OpError("scale values must be positive.")
    T = np.diag([*s, 1]) @ T
    r = _vec(p, "rotate", (0, 0, 0), 3600)
    R = trimesh.transformations.euler_matrix(*np.radians(r), axes="sxyz")
    T = R @ T
    mir = p.get("mirror")
    if mir:
        if mir not in ("x", "y", "z"):
            raise OpError("mirror must be x | y | z")
        M = np.eye(4); M["xyz".index(mir), "xyz".index(mir)] = -1
        T = M @ T
    T = trimesh.transformations.translation_matrix(center + _vec(p, "move")) @ T
    return T


def op_body_transform(m, p):
    """Move / rotate / scale (uniform or per axis) / mirror one body (or all with body = -1), about
    its centre or a given pivot. copy=true keeps the original too (mirror copy)."""
    sel, rest = _pick(m, p)
    piv = p.get("pivot", "center")
    center = sel.bounds.mean(axis=0) if piv == "center" else np.zeros(3) if piv == "origin" else _vec(p, "pivot")
    T = _xform_matrix(p, center)
    # trimesh's apply_transform already flips the winding for a mirror (det < 0); inverting again
    # made mirrored bodies inside-out (-volume). QA N1.
    moved = sel.copy(); moved.apply_transform(T)
    out = _join_sep(_join(rest, sel) if p.get("copy") else rest, moved, "Move it slightly, or Union the bodies.")
    return out, {"message": "Transformed."}


def op_pattern(m, p):
    """Linear (step [dx,dy,dz]) or circular (axis + total angle about centre) copies of a body."""
    kind = p.get("kind", "linear")
    count = int(_num(p, "count", 3, 2, MAX_PATTERN))
    sel, rest = _pick(m, p)
    est = len(sel.faces) * count
    if est > MAX_PATTERN_FACES:
        raise OpError(f"That pattern would make about {est:,} triangles (limit {MAX_PATTERN_FACES:,}). "
                      "Use fewer copies or simplify / remesh coarser first.")
    copies = []
    if kind == "linear":
        step = _vec(p, "step", (20, 0, 0))
        for k in range(count):
            c = sel.copy(); c.apply_translation(step * k); copies.append(c)
    elif kind == "circular":
        axis = _vec(p, "axis", (0, 0, 1), 10)
        if np.linalg.norm(axis) < 1e-9:
            raise OpError("axis can't be zero.")
        tot = _num(p, "angle", 360, 1, 360)
        cen = _vec(p, "center")
        n = count if tot < 360 - 1e-6 else count
        stepa = tot / (count - 1 if tot < 360 - 1e-6 else count)
        for k in range(n):
            c = sel.copy()
            c.apply_transform(trimesh.transformations.rotation_matrix(math.radians(stepa * k), axis, cen)); copies.append(c)
    else:
        raise OpError("kind must be linear | circular")
    if p.get("fuse", True):
        try:
            acc = _to_manifold(copies[0])
            import manifold3d as mf
            acc = mf.Manifold.batch_boolean([_to_manifold(c) for c in copies], mf.OpType.Add)
            pat = _from_manifold(acc)
        except OpError:
            pat = trimesh.util.concatenate(copies)
    else:
        pat = trimesh.util.concatenate(copies)
        if _touching(pat):
            raise OpError("The copies would touch face-to-face, which can't be kept as separate solids. Turn on Fuse, or use a slightly larger spacing.")
    return _join_sep(rest, pat, "Turn on Fuse, or use a slightly larger spacing."), {"message": f"{kind.title()} pattern ×{count}."}


def op_align(m, p):
    """Align a body's min / centre / max on an axis to a value, or to another body's same side."""
    sel, rest = _pick(m, p)
    axis = p.get("axis", "z")
    side = p.get("side", "min")
    if axis not in ("x", "y", "z") or side not in ("min", "center", "max"):
        raise OpError("axis must be x|y|z and side min|center|max")
    k = "xyz".index(axis)
    def at(b):
        lo, hi = b.bounds
        return {"min": lo[k], "max": hi[k], "center": (lo[k] + hi[k]) / 2}[side]
    if p.get("to_body") is not None and int(p["to_body"]) >= 0:
        bs = bodies(m); j = int(p["to_body"])
        if j >= len(bs):
            raise OpError("No such body to align to.")
        target = at(bs[j])
    else:
        target = _num(p, "value", 0, -LIM, LIM)
    mv = np.zeros(3); mv[k] = target - at(sel)
    out = sel.copy(); out.apply_translation(mv)
    return _join(rest, out), {"message": f"Aligned {side} {axis.upper()}."}


OPS = {"sketch_extrude": op_sketch_extrude, "revolve": op_revolve, "body_boolean": op_body_boolean,
       "round_edges": op_round_edges, "face_offset": op_face_offset, "body_transform": op_body_transform,
       "pattern": op_pattern, "align": op_align}

# Keys each CAD op reads. Anything else in a step's params is dropped before it is stored
# (stored params are shown in History and shared with public projects).
PARAM_KEYS = {
    "sketch_extrude": {"sketch", "plane", "picks", "distance", "direction", "mode", "taper", "replace", "solve"},
    "revolve": {"sketch", "plane", "picks", "axis", "angle", "mode", "replace", "solve"},
    "body_boolean": {"kind", "target", "tool"},
    "round_edges": {"radius", "style", "body", "edges"},
    "face_offset": {"point", "normal", "distance"},
    "body_transform": {"body", "move", "rotate", "scale", "mirror", "pivot", "copy"},
    "pattern": {"kind", "count", "step", "axis", "angle", "center", "body", "fuse"},
    "align": {"body", "axis", "side", "to_body", "value"},
    "sculpt_stroke": {"brush", "radius", "strength", "points", "normal", "delta", "symmetry_x"},
    "remesh": {"edge"},
}


def clean_params(op: str, p: dict) -> dict:
    """Drop unknown keys and validate the plane (named plane or a numeric frame only)."""
    keys = PARAM_KEYS.get(op)
    if keys is None:
        return p
    out = {k: v for k, v in p.items() if k in keys}
    if "plane" in out:
        try:
            o, xd, yd, n = sk.plane(out["plane"])
        except (sk.SketchError, TypeError, ValueError, AttributeError) as e:
            raise OpError(str(e) or "Bad plane.")
        if not isinstance(out["plane"], str):
            r = lambda v: [round(float(x), 6) for x in v]
            kind = "offset" if "offset" in out["plane"] else "midplane" if "mid" in out["plane"] else None
            if kind is None and out["plane"].get("construct") in ("offset", "midplane"):
                kind = out["plane"]["construct"]
            out["plane"] = {"origin": r(o), "normal": r(n), "xdir": r(xd)}
            if kind:
                out["plane"]["construct"] = kind   # label only (fixed strings), shown in History
    if "sketch" in out:
        try:
            out["sketch"] = sk.check(out["sketch"])
        except sk.SketchError as e:
            raise OpError(str(e))
    return out

from . import sculptws as _sculptws   # noqa: E402  (workspace sculpt strokes + remesh)
if hasattr(_sculptws, "OPS"):           # sculptws imported first: it registers itself at its end (QA B15)
    OPS.update(_sculptws.OPS)
from . import cadtext as _cadtext   # noqa: E402  (Text & Emboss)
OPS["cad_text"] = _cadtext.op_cad_text
PARAM_KEYS["cad_text"] = _cadtext.KEYS
from . import meshedit as _meshedit   # noqa: E402  (register even when this module is imported first)
_meshedit.OPS.update(OPS)


def label(op: str, p: dict) -> str | None:
    if op in getattr(_sculptws, "OPS", ()):
        return _sculptws.label(op, p)
    if op == "cad_text":
        return _cadtext.label(p)
    g = lambda k, d="": p.get(k, d)
    b = lambda: "" if int(p.get("body", -1) if p.get("body") is not None else -1) < 0 else f" · Body {int(p['body']) + 1}"
    try:
        return {
            "sketch_extrude": lambda: f"Extrude {float(g('distance', 10)):g} mm {g('direction', 'up')} ({g('mode', 'new')})",
            "revolve": lambda: f"Revolve {float(g('angle', 360)):g}° ({g('mode', 'new')})",
            "body_boolean": lambda: f"Boolean {g('kind', 'union')} Body {int(g('target', 0)) + 1} / Body {int(g('tool', 1)) + 1}",
            "round_edges": lambda: f"{str(g('style', 'fillet')).title()} {float(g('radius', 1)):g} mm" + (f" ({len(g('edges'))} edges)" if g("edges") else " (all convex edges)") + b(),
            "face_offset": lambda: f"Face offset {float(g('distance', 1)):g} mm",
            "body_transform": lambda: ("Mirror copy" if g("copy") and g("mirror") else "Mirror" if g("mirror") else "Move/Rotate/Scale") + b(),
            "pattern": lambda: f"{str(g('kind', 'linear')).title()} pattern ×{int(float(g('count', 3)))}" + b(),
            "align": lambda: f"Align {g('side', 'min')} {str(g('axis', 'z')).upper()}" + b(),
        }[op]()
    except Exception:
        return None
