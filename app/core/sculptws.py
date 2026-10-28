"""Workspace sculpting: brush strokes recorded as history steps (original ZEIM code).

Workflow ideas (brush set, size/strength, X symmetry, remesh for detail) follow how public sculpting
apps are documented to behave (e.g. Nomad Sculpt, Blender sculpt mode); no code from them is used.
A stroke = the dab centres the user dragged over (surface points), the surface normal at the start,
brush, radius, strength, optional X symmetry and (grab) a move vector. Replaying the step re-applies
the same dabs, so strokes stay in History with undo/redo/delete like every other step.
Limits: the brush is a sphere, but only vertices facing the stroke normal move. The back
of a thin wall stays put. A stroke that would fold a touched face, or move a vertex outside
the brush, is refused and the model is left unchanged. "remesh" is uniform subdivision to a
target edge length (no dynamic topology while stroking). It does not build a new surface.
"""
from __future__ import annotations

import numpy as np
import trimesh

from .meshedit import OpError, _check, _new

BRUSHES = ("draw", "carve", "smooth", "inflate", "pinch", "flatten", "grab")
MAX_VERTS = 400_000
MAX_DABS = 400


def _f(p, k, d, lo, hi):
    try:
        v = float(p.get(k, d))
    except (TypeError, ValueError):
        raise OpError(f"{k} must be a number.")
    if not np.isfinite(v) or not lo <= v <= hi:
        raise OpError(f"{k} must be {lo:g}..{hi:g}.")
    return v


def _pts(x, what, n_max):
    try:
        a = np.asarray(x, float)
    except (TypeError, ValueError):
        raise OpError(f"{what} must be a list of [x, y, z].")
    if a.ndim != 2 or a.shape[1] != 3 or not 1 <= len(a) <= n_max or not np.isfinite(a).all():
        raise OpError(f"{what} must be 1..{n_max} points [x, y, z].")
    return a


def _neighbours(m):
    import scipy.sparse as sp
    e = m.edges_unique
    n = len(m.vertices)
    A = sp.coo_matrix((np.ones(len(e) * 2), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(n, n)).tocsr()
    deg = np.asarray(A.sum(axis=1)).ravel()
    deg[deg == 0] = 1
    return A, deg


def _outside_brush(pts, dabs, radius, sym, cx):
    """Vertices farther than the brush from every dab (and from the mirrored dabs)."""
    d = np.linalg.norm(pts[:, None, :] - dabs[None, :, :], axis=2).min(axis=1)
    inside = d <= radius + 1e-4
    if sym:
        mir = pts.copy()
        mir[:, 0] = 2 * cx - mir[:, 0]
        d2 = np.linalg.norm(mir[:, None, :] - dabs[None, :, :], axis=2).min(axis=1)
        inside |= d2 <= radius + 1e-4
    return ~inside


def _clamp_thin_wall(v, v0, vn, n_stroke, min_wall=0.4, reach=8.0):
    """Hold a move that would pinch a nearby back face below min_wall mm. Returns how many were held."""
    moved = np.nonzero(np.linalg.norm(v - v0, axis=1) > 1e-8)[0]
    if not len(moved):
        return 0
    back = np.nonzero(vn @ n_stroke < -0.2)[0]
    if not len(back):
        return 0
    from scipy.spatial import cKDTree
    dist, j = cKDTree(v0[back]).query(v0[moved])
    near = dist < reach
    partner = v0[back][j]
    sep = np.linalg.norm(v[moved] - partner, axis=1)
    bad = near & (dist + 1e-9 >= min_wall) & (sep < min_wall)
    if not bad.any():
        return 0
    p0 = v0[moved][bad]
    delta = v[moved][bad] - p0
    q = partner[bad]
    a = np.einsum("ij,ij->i", delta, delta)
    b = 2 * np.einsum("ij,ij->i", p0 - q, delta)
    c = np.einsum("ij,ij->i", p0 - q, p0 - q) - min_wall ** 2
    disc = b * b - 4 * a * c
    ok = (a > 1e-12) & (disc >= 0)
    root = np.sqrt(np.maximum(disc, 0.0))
    denom = 2 * np.maximum(a, 1e-12)
    s1 = np.where(ok, (-b - root) / denom, np.nan)
    s2 = np.where(ok, (-b + root) / denom, np.nan)
    s1 = np.where((s1 >= 0) & (s1 <= 1), s1, np.nan)
    s2 = np.where((s2 >= 0) & (s2 <= 1), s2, np.nan)
    s = np.nanmin(np.vstack([s1, s2]), axis=0)
    s = np.where(np.isfinite(s), s, 0.0)
    v[moved[np.nonzero(bad)[0]]] = p0 + s[:, None] * delta
    return int(bad.sum())


def _folded(v, faces, old_fn, touched):
    """Degenerate or flipped faces among faces the stroke touched."""
    if not touched.any():
        return 0
    sel = touched[faces].any(axis=1)
    if not sel.any():
        return 0
    f = faces[sel]
    tri = v[f]
    new_fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = np.linalg.norm(new_fn, axis=1)
    degenerate = area < 1e-12
    live = ~degenerate
    flipped = live & (np.einsum("ij,ij->i", new_fn, old_fn[sel]) < 0)
    return int(degenerate.sum() + flipped.sum())


def op_sculpt_stroke(m: trimesh.Trimesh, p: dict):
    brush = p.get("brush")
    if brush not in BRUSHES:
        raise OpError(f"brush must be one of {', '.join(BRUSHES)}")
    r = _f(p, "radius", 5, 0.05, 500)
    s = _f(p, "strength", 0.5, 0.0, 1.0)
    dabs = _pts(p.get("points"), "points", MAX_DABS)
    n0 = _pts([p.get("normal", [0, 0, 1])], "normal", 1)[0]
    if np.linalg.norm(n0) < 1e-9:
        raise OpError("normal can't be zero.")
    n0 = n0 / np.linalg.norm(n0)
    grab = _pts([p.get("delta", [0, 0, 0])], "delta", 1)[0]
    mm = m.copy(); mm.merge_vertices()
    if len(mm.vertices) > MAX_VERTS:
        raise OpError(f"Too detailed to sculpt here ({len(mm.vertices):,} points; limit {MAX_VERTS:,}).")
    v0 = mm.vertices.copy()
    # X symmetry mirrors about the model's own centre plane (QA B5), not world x = 0;
    # a client can pass the plane it showed the user as `sym_x`.
    cx = float(p["sym_x"]) if isinstance(p.get("sym_x"), (int, float)) and np.isfinite(p["sym_x"]) else float(mm.bounds.mean(axis=0)[0])
    M = np.array([-1.0, 1, 1])
    nb = {}
    base_vn = trimesh.Trimesh(v0, mm.faces, process=False).vertex_normals
    touched = np.zeros(len(v0), dtype=bool)
    tri0 = v0[mm.faces]
    old_fn = np.cross(tri0[:, 1] - tri0[:, 0], tri0[:, 2] - tri0[:, 0])

    def run(D, n, g):
        v = v0.copy()
        D = D[:1] if brush == "grab" else D                  # grab: one dab at the start, moved by delta
        for c in D:
            d = np.linalg.norm(v - c, axis=1)
            idx = np.nonzero(d < r)[0]
            # Front of the stroke only. A thin wall's back face points the other way and stays put.
            if len(idx):
                idx = idx[(base_vn[idx] @ n) > 0.2]
            if not len(idx):
                continue
            touched[idx] = True
            w = (1 - (d[idx] / r) ** 2) ** 2 * s
            if brush in ("draw", "carve"):
                v[idx] += np.outer(w, n) * (0.15 * r) * (1 if brush == "draw" else -1)
            elif brush == "inflate":
                vn = trimesh.Trimesh(v, mm.faces, process=False).vertex_normals[idx]
                v[idx] += vn * (w * 0.15 * r)[:, None]
            elif brush == "smooth":
                if "A" not in nb:
                    nb["A"], nb["deg"] = _neighbours(mm)
                avg = (nb["A"][idx] @ v) / nb["deg"][idx, None]
                v[idx] += (avg - v[idx]) * w[:, None]
            elif brush == "pinch":
                t = c - v[idx]
                t -= np.outer(t @ n, n)
                v[idx] += t * (w * 0.3)[:, None]
            elif brush == "flatten":
                ctr = v[idx].mean(axis=0)
                v[idx] -= np.outer(((v[idx] - ctr) @ n) * w, n)
            elif brush == "grab":
                v[idx] += np.outer(w / max(s, 1e-9), g)          # grab follows the finger fully at the centre
        return v - v0

    d1 = run(dabs, n0, grab)
    if p.get("symmetry_x"):
        mir = dabs.copy(); mir[:, 0] = 2 * cx - mir[:, 0]
        dm = run(mir, n0 * M, grab * M)                     # covers vertices with no mirror partner
        # Exact symmetry (QA B6): both halves come from ONE stroke field. For a vertex whose mirror
        # partner exists, its mirrored contribution is the partner's displacement, reflected.
        from scipy.spatial import cKDTree
        q = v0.copy(); q[:, 0] = 2 * cx - q[:, 0]
        dist, j = cKDTree(v0).query(q)
        tol = max(1e-6, 1e-4 * float(np.max(mm.extents)))
        ok = dist <= tol
        dm[ok] = d1[j[ok]] * M
        d1 = d1 + dm
    v = v0 + d1
    clamped = _clamp_thin_wall(v, v0, base_vn, n0)
    # A small margin: a symmetry partner can sit just past the brush radius on a curved mesh.
    outside = _outside_brush(v0, dabs, r + max(0.5, 0.02 * r), bool(p.get("symmetry_x")), cx)
    if outside.any() and float(np.max(np.linalg.norm(v[outside] - v0[outside], axis=1))) > 1e-5:
        raise OpError("the stroke would change dimensions outside the brush — refused; the model was left unchanged.")
    folded = _folded(v, mm.faces, old_fn, touched)
    if folded:
        raise OpError(
            f"the sculpt stroke folded {folded} face(s) — refused; the model was left unchanged. "
            "Lower the strength or the brush size and try again.")
    moved_n = int(np.count_nonzero(np.linalg.norm(v - v0, axis=1) > 1e-8))
    if moved_n == 0:
        in_radius = np.linalg.norm(v0[:, None, :] - dabs[None, :, :], axis=2).min(axis=1) <= r
        if in_radius.any():
            raise OpError(
                "the brush only reached the back of the surface, so nothing was changed. "
                "Turn the model and sculpt the side you can see. The back of a thin wall stays put.")
        return m, {"message": f"{brush.title()} stroke was outside the model: nothing changed.",
                   "vertices_moved": 0, "thin_wall_protected": True}
    out = _check(_new(v, mm.faces))
    note = " Front of the brush only; the back of a thin wall stays. Size outside the brush is unchanged."
    if clamped:
        note += f" {clamped} move(s) were held so the wall stayed at least 0.4 mm."
    return out, {"message": f"{brush.title()} stroke ({len(dabs)} dabs, {r:g} mm brush{', X symmetry' if p.get('symmetry_x') else ''})." + note,
                 "vertices_moved": moved_n, "thin_wall_protected": True, "thin_wall_clamped": clamped}


MAX_REMESH_FACES = 200_000      # = what the CAD workspace can show and sculpt (api/cad.MAX_SCENE_FACES)


def op_remesh(m: trimesh.Trimesh, p: dict):
    """Uniform detail: split triangles until no edge is longer than `edge` mm (adds points to sculpt)."""
    e = _f(p, "edge", 1.0, 0.05, 100)
    mm = m.copy(); mm.merge_vertices()
    # subdivide_to_size halves every long edge until it fits, so a face whose longest edge is L
    # becomes 4**ceil(log2(L/e)) faces. Sum that (exact for the splitter; the old area estimate was ~3x low).
    longest = mm.edges_unique_length[mm.faces_unique_edges].max(axis=1) if len(mm.faces) else np.zeros(0)
    k = np.ceil(np.log2(np.maximum(longest / e, 1.0)))
    est = float(np.sum(4.0 ** np.minimum(k, 12)))
    if est > MAX_REMESH_FACES:
        raise OpError(f"That would make about {est:,.0f} triangles; the CAD workspace handles up to "
                      f"{MAX_REMESH_FACES:,}. Use a larger edge length (or remesh only once).")
    try:
        v, f = trimesh.remesh.subdivide_to_size(mm.vertices, mm.faces, max_edge=e, max_iter=12)
    except ValueError as er:
        raise OpError(f"Remesh failed: {er}")
    out = _new(v, f); out.merge_vertices()
    if len(out.faces) > MAX_REMESH_FACES:
        raise OpError(f"Remesh made {len(out.faces):,} triangles (limit {MAX_REMESH_FACES:,}); left unchanged. Use a larger edge length.")
    return out, {"message": f"Uniform subdivision: edges at most {e:g} mm ({len(out.faces):,} triangles). "
                            "This splits long edges. It does not build a new surface."}


OPS = {"sculpt_stroke": op_sculpt_stroke, "remesh": op_remesh}


def label(op, p):
    if op == "remesh":
        return f"Uniform subdivision ≤ {p.get('edge', 1)} mm"
    if op == "sculpt_stroke":
        return f"Sculpt {str(p.get('brush', '')).title()} ({float(p.get('radius', 5)):g} mm)" + (" · X sym" if p.get("symmetry_x") else "")
    return None


from . import meshedit as _meshedit   # noqa: E402  register even when this module is imported first (QA B15)
_meshedit.OPS.update(OPS)
