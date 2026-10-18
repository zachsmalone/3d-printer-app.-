"""Workspace sculpting: brush strokes recorded as history steps (original ZEIM code).

Workflow ideas (brush set, size/strength, X symmetry, remesh for detail) follow how public sculpting
apps are documented to behave (e.g. Nomad Sculpt, Blender sculpt mode); no code from them is used.
A stroke = the dab centres the user dragged over (surface points), the surface normal at the start,
brush, radius, strength, optional X symmetry and (grab) a move vector. Replaying the step re-applies
the same dabs, so strokes stay in History with undo/redo/delete like every other step.
Limits: the brush is a sphere in space (thin walls: the back side moves too); "remesh" is uniform
subdivision to a target edge length (no dynamic topology while stroking).
"""
from __future__ import annotations

import numpy as np
import trimesh

from .meshedit import OpError, _new

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

    def run(D, n, g):
        v = v0.copy()
        D = D[:1] if brush == "grab" else D                  # grab: one dab at the start, moved by delta
        for c in D:
            d = np.linalg.norm(v - c, axis=1)
            idx = np.nonzero(d < r)[0]
            if not len(idx):
                continue
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
    out = _new(v, mm.faces)
    return out, {"message": f"{brush.title()} stroke ({len(dabs)} dabs, {r:g} mm brush{', X symmetry' if p.get('symmetry_x') else ''})."}


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
    return out, {"message": f"Remeshed to ≤ {e:g} mm edges ({len(out.faces):,} triangles)."}


OPS = {"sculpt_stroke": op_sculpt_stroke, "remesh": op_remesh}


def label(op, p):
    if op == "remesh":
        return f"Remesh ≤ {p.get('edge', 1)} mm"
    if op == "sculpt_stroke":
        return f"Sculpt {str(p.get('brush', '')).title()} ({float(p.get('radius', 5)):g} mm)" + (" · X sym" if p.get("symmetry_x") else "")
    return None


from . import meshedit as _meshedit   # noqa: E402  register even when this module is imported first (QA B15)
_meshedit.OPS.update(OPS)
