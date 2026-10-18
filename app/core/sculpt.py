"""Sculpt brushes (the Nomad Sculpt core, applied to ZEIM's job: touch up a mesh in place).

Three brushes, one op: smooth (Laplacian relaxation with falloff), flatten (move vertices
toward a stored plane) and inflate (push vertices out along their normals). Original
code; the Laplacian/falloff/marching conventions are public.

Honest limits, disclosed up front:
* Laplacian smoothing SHRINKS geometry a little (high-frequency detail is volume) —
  that is the trade, same as every brush-based sculptor.
* The brush is a SPHERE in space: every vertex within `radius` of `center` moves —
  on a thin wall that includes the BACK side (there is no camera ray here to tell
  front from back; the selection policy is deliberate and tested, not hidden).
* Inflate at extreme strengths can flip triangles; the result is checked and the count
  of inverted/degenerate faces is REPORTED (watertightness alone would not catch it).
* `plane` may be pinned in the op params (flatten): the plane is derived from the
  selection ONCE per op — never re-derived per iteration, so repeated strokes replay
  identically and cannot drift.
"""
from __future__ import annotations

import numpy as np
import trimesh

MAX_VERTS = 150_000        # the adjacency build is sparse, but still O(faces): refuse first
MAX_FACES = 300_000
MAX_ITER = 10
BRUSHES = ("smooth", "flatten", "inflate")
INFLATE_FRACTION = 0.1     # full-strength inflate moves vertices 0.1 * radius (mm)


def _falloff(d: np.ndarray, radius: float) -> np.ndarray:
    """Smooth brush weight: 1 at the center, 0 at the rim (0 outside)."""
    t = np.clip(1.0 - (d / radius) ** 2, 0.0, 1.0)
    return t * t


def _neighbors(faces: np.ndarray, n: int) -> tuple:
    """Sparse vertex adjacency by edge accumulation — never a dense matrix.

    Returns (rows, cols, degree): rows[i] lists the neighbors of vertex i."""
    e = np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    both = np.vstack([e, e[:, ::-1]])
    rows = both[:, 0]
    cols = both[:, 1]
    degree = np.bincount(rows, minlength=n).astype(float)
    return rows, cols, degree


def _vertex_normals(m: trimesh.Trimesh, n: int) -> np.ndarray:
    """Area-weighted vertex normals without trimesh's full reprocessing."""
    tri = m.vertices[m.faces]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    vn = np.zeros((n, 3))
    for k in range(3):
        np.add.at(vn, m.faces[:, k], fn)
    lens = np.linalg.norm(vn, axis=1, keepdims=True)
    lens[lens == 0] = 1.0
    return vn / lens


def _plane_of(m: trimesh.Trimesh, inside: np.ndarray, vn: np.ndarray) -> tuple:
    """The flatten target: centroid of the selection + averaged (normalized) selection
    normal — computed ONCE from the input mesh, then frozen in the op params."""
    q = m.vertices[inside].mean(axis=0)
    n = vn[inside].sum(axis=0)
    ln = float(np.linalg.norm(n))
    if ln < 1e-12:
        raise _err("the brush selection has no usable normal to flatten onto — pick a smaller radius or another spot.")
    return q, n / ln


def _err(msg: str):
    from .meshedit import OpError
    return OpError(msg)


def op_sculpt(m: trimesh.Trimesh, p: dict) -> tuple[trimesh.Trimesh, dict]:
    from .meshedit import OpError, _check
    """Sculpt one brush stroke. Works on a COPY (the input mesh is never mutated); every
    parameter is validated BEFORE any adjacency work; replay is deterministic (pure
    numpy, stable accumulation)."""
    # ---- validate (cheap first: no geometry touched until all params are sane) ----
    brush = str(p.get("brush", "smooth"))
    if brush not in BRUSHES:
        raise OpError(f"brush must be one of {', '.join(BRUSHES)}.")
    try:
        center = np.asarray(p.get("center", [0.0, 0.0, 0.0]), dtype=float).reshape(-1)[:3]
    except (TypeError, ValueError):
        raise OpError("center must be three finite numbers (x, y, z in mm).")
    if center.size != 3 or not np.isfinite(center).all():
        raise OpError("center must be three finite numbers (x, y, z in mm).")
    try:
        radius = float(p.get("radius", 0.0))
    except (TypeError, ValueError):
        raise OpError("radius must be a number (mm).")
    if not np.isfinite(radius) or radius <= 0 or radius > 10_000:
        raise OpError("radius must be a finite number of mm, 0 < radius <= 10000.")
    try:
        strength = float(p.get("strength", 0.5))
    except (TypeError, ValueError):
        raise OpError("strength must be a number 0..1.")
    if not np.isfinite(strength) or not 0.0 <= strength <= 1.0:
        raise OpError("strength must be a number 0..1.")
    iters = p.get("iterations", 1)
    if not isinstance(iters, int) or isinstance(iters, bool) or not 1 <= iters <= MAX_ITER:
        raise OpError(f"iterations must be an integer 1..{MAX_ITER}.")
    plane = None
    if brush == "flatten" and p.get("plane") is not None:
        pl = p["plane"]
        try:
            q = np.asarray(pl["point"], dtype=float).reshape(-1)[:3]
            n = np.asarray(pl["normal"], dtype=float).reshape(-1)[:3]
        except (TypeError, KeyError, ValueError):
            raise OpError("plane must be {point: [x,y,z], normal: [x,y,z]} in mm.")
        if q.size != 3 or n.size != 3 or not (np.isfinite(q).all() and np.isfinite(n).all()) \
                or np.linalg.norm(n) < 1e-12:
            raise OpError("plane needs finite point and a non-zero normal.")
        plane = (q, n / np.linalg.norm(n))
    # ---- resource caps BEFORE building adjacency (the expensive part) ----
    n = len(m.vertices)
    if n == 0 or len(m.faces) == 0:
        raise OpError("the model is empty.")
    if n > MAX_VERTS:
        raise OpError(f"sculpting needs at most {MAX_VERTS:,} vertices; this model has {n:,} — simplify first.")
    if len(m.faces) > MAX_FACES:
        raise OpError(f"sculpting needs at most {MAX_FACES:,} faces; this model has {len(m.faces):,} — simplify first.")

    # ---- selection (a sphere in space; the policy is deliberate — see the docstring) ----
    d = np.linalg.norm(m.vertices - center, axis=1)
    inside = d <= radius
    if not inside.any():
        rep = {"brush": brush, "radius_mm": radius, "strength": strength, "iterations": iters,
               "vertices_moved": 0, "inverted_faces": 0,
               "message": f"Sculpt ({brush}) — the brush was outside the model: nothing changed."}
        return m, rep
    w = _falloff(d, radius)
    vn = _vertex_normals(m, n)

    # ---- the frozen flatten plane (computed once, reported so it can be pinned) ----
    if brush == "flatten" and plane is None:
        plane = _plane_of(m, inside, vn)

    # ---- work on a copy; the input mesh is untouched from here on ----
    v = m.vertices.copy()
    faces = m.faces
    old_face_normals = None
    if brush == "inflate":
        tri = v[faces]
        old_face_normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])

    try:
        if brush == "smooth":
            rows, cols, degree = _neighbors(faces, n)
            for _ in range(iters):
                # neighbor average via sparse accumulation (bincount per axis — no dense matrix)
                avg = np.empty((n, 3))
                for k in range(3):
                    acc = np.bincount(rows, weights=v[cols, k], minlength=n)
                    avg[:, k] = acc / np.maximum(degree, 1.0)
                lam = (strength * w)[:, None]           # falloff-scaled per vertex
                v = (1.0 - lam) * v + lam * avg
                v[~inside] = m.vertices[~inside]        # anchors: untouched vertices never move
        elif brush == "flatten":
            q, nrm = plane
            for _ in range(iters):
                off = (v - q) @ nrm                       # signed distance to the plane
                v = v - (strength * w)[:, None] * off[:, None] * nrm
                v[~inside] = m.vertices[~inside]
        else:  # inflate
            amount = strength * radius * INFLATE_FRACTION
            for _ in range(iters):
                v = v + (strength * w)[:, None] * vn * amount
    except OpError:
        raise
    except Exception as e:
        raise OpError(f"sculpt failed: {e}")

    out = trimesh.Trimesh(v, faces, process=False)       # exact vertices: no reprocessing

    # ---- inversion / degeneracy check (watertightness alone would not catch these) ----
    inverted = 0
    if brush == "inflate" and old_face_normals is not None:
        tri = out.vertices[faces]
        new_fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        area = np.linalg.norm(new_fn, axis=1)
        degenerate = int((area < 1e-12).sum())
        flipped = int(((np.linalg.norm(new_fn, axis=1) > 1e-12) &
                       (np.einsum("ij,ij->i", new_fn, old_face_normals) < 0)).sum())
        inverted = degenerate + flipped

    rep = {"brush": brush, "radius_mm": radius, "strength": strength, "iterations": iters,
           "vertices_moved": int(inside.sum()), "inverted_faces": inverted,
           "message": f"Sculpt ({brush}) — {int(inside.sum()):,} vertices, {iters} iteration(s)"}
    if brush == "flatten" and plane is not None:
        rep["plane"] = {"point": [float(x) for x in plane[0]], "normal": [float(x) for x in plane[1]]}
        rep["message"] += " toward the stored plane"
    if brush == "smooth":
        rep["message"] += " (Laplacian smoothing shrinks detail slightly — that is the trade)"
    if inverted:
        rep["message"] += f" — WARNING: {inverted} degenerate/flipped face(s); lower the strength"
    return _check(out), rep
