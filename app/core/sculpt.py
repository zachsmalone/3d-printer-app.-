"""Sculpt brushes (the Nomad Sculpt core, applied to ZEIM's job: touch up a mesh in place).

Three brushes, one op: smooth (Laplacian relaxation with falloff), flatten (move vertices
toward a plane) and inflate (push vertices out along their normals). Original code; the
Laplacian/falloff conventions are public.

Honest limits, disclosed up front and in every report message:
* Laplacian smoothing SHRINKS geometry a little (high-frequency detail is volume) —
  that is the trade, same as every brush-based sculptor.
* The brush is a SPHERE in space: every vertex within `radius` of `center` moves — on a
  thin wall that includes the BACK side (there is no camera ray here to tell front from
  back; the policy is deliberate and tested, not hidden).
* A stroke that folds the mesh (degenerate or flipped faces) is REFUSED, not warned
  about: the model is left untouched and the error says what happened.
* Flatten: the target plane is derived from the selection ONCE, then persisted into the
  saved step's params (editproj merges the op's `_persist` payload), so replays after
  an earlier step changed reuse the SAME plane — never re-derived, never drifting.
"""
from __future__ import annotations

import numpy as np
import trimesh

MAX_VERTS = 150_000        # the adjacency build is sparse, but still O(faces): refuse first
MAX_FACES = 300_000
MAX_ITER = 10
BRUSHES = ("smooth", "flatten", "inflate")
INFLATE_FRACTION = 0.1     # full-strength inflate moves vertices 0.1 * radius (mm)


def _vec3(x, what: str) -> np.ndarray:
    """EXACTLY a 3-vector of finite numbers — no reshaping, so [[1,2,3]], [[1],[2],[3]]
    and 4-coordinate extras are all rejected instead of silently flattened."""
    from .meshedit import OpError
    try:
        a = np.asarray(x, dtype=float)
    except (TypeError, ValueError):
        raise OpError(f"{what} must be exactly three finite numbers.")
    if a.shape != (3,) or not np.isfinite(a).all():
        raise OpError(f"{what} must be exactly three finite numbers.")
    return a


def _falloff(d: np.ndarray, radius: float) -> np.ndarray:
    """Smooth brush weight: 1 at the center, 0 at the rim (0 outside)."""
    t = np.clip(1.0 - (d / radius) ** 2, 0.0, 1.0)
    return t * t


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


def _folded(v: np.ndarray, faces: np.ndarray, old_fn: np.ndarray, touched: np.ndarray) -> int:
    """Degenerate (zero-area) or flipped (normal reversed vs. the input) faces — counted
    only among faces the stroke TOUCHED (a vertex inside the brush): pre-existing damage
    elsewhere in the model is not this stroke's fault and must not block it."""
    sel = touched[faces].any(axis=1)
    if not sel.any():
        return 0
    f = faces[sel]
    tri = v[f]
    new_fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = np.linalg.norm(new_fn, axis=1)
    degenerate = int((area < 1e-12).sum())
    live = area > 1e-12
    flipped = int((live & (np.einsum("ij,ij->i", new_fn, old_fn[sel]) < 0)).sum())
    return degenerate + flipped


def op_sculpt(m: trimesh.Trimesh, p: dict) -> tuple[trimesh.Trimesh, dict]:
    from .meshedit import OpError, _check
    """Sculpt one brush stroke. Works on a COPY (the input mesh is never mutated — a
    refused stroke leaves it untouched); every parameter is validated BEFORE any
    adjacency work; a stroke that folds faces is refused outright; replay is
    deterministic (pure numpy, stable accumulation)."""
    # ---- validate (cheap first: no geometry touched until all params are sane) ----
    brush = str(p.get("brush", "smooth"))
    if brush not in BRUSHES:
        raise OpError(f"brush must be one of {', '.join(BRUSHES)}.")
    center = _vec3(p.get("center", [0.0, 0.0, 0.0]), "center")
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
        try:
            q = _vec3(p["plane"]["point"], "plane point")
            n = _vec3(p["plane"]["normal"], "plane normal")
        except (TypeError, KeyError):
            raise OpError("plane must be {point: [x,y,z], normal: [x,y,z]} in mm.")
        if np.linalg.norm(n) < 1e-12:
            raise OpError("plane needs a non-zero normal.")
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
               "vertices_moved": 0,
               "message": f"Sculpt ({brush}) — the brush was outside the model: nothing changed."}
        return m, rep
    w = _falloff(d, radius)
    vn = _vertex_normals(m, n)

    # ---- the flatten plane: pinned in params, or derived ONCE and persisted ----
    # (only when the stroke can actually move something: a zero-strength stroke is a
    # no-op and must not fail on a selection whose normals cancel — there is nothing
    # to flatten, so no plane is needed)
    persist = {}
    if brush == "flatten" and plane is None and strength > 0:
        q = m.vertices[inside].mean(axis=0)
        nv = vn[inside].sum(axis=0)
        ln = float(np.linalg.norm(nv))
        if ln < 1e-12:
            raise OpError("the brush selection has no usable normal to flatten onto — pick a smaller radius or another spot.")
        plane = (q, nv / ln)
        persist["plane"] = {"point": [float(x) for x in q], "normal": [float(x) for x in plane[1]]}

    # ---- work on a copy; the input mesh is untouched from here on ----
    v = m.vertices.copy()
    faces = m.faces
    tri = m.vertices[faces]
    old_fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])   # for the fold check

    try:
        if brush == "smooth":
            # sparse neighbor adjacency by edge accumulation (bincount per axis — never a dense matrix)
            e = np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
            both = np.vstack([e, e[:, ::-1]])
            rows, cols = both[:, 0], both[:, 1]
            degree = np.bincount(rows, minlength=n).astype(float)
            for _ in range(iters):
                avg = np.empty((n, 3))
                for k in range(3):
                    acc = np.bincount(rows, weights=v[cols, k], minlength=n)
                    avg[:, k] = acc / np.maximum(degree, 1.0)
                lam = (strength * w)[:, None]           # falloff-scaled per vertex
                v = (1.0 - lam) * v + lam * avg
                v[~inside] = m.vertices[~inside]        # anchors: untouched vertices never move
        elif brush == "flatten":
            if plane is None:
                pass                                     # zero-strength: nothing to move, no plane needed
            else:
                q, nrm = plane
                for _ in range(iters):
                    off = (v - q) @ nrm                  # signed distance to the plane
                    v = v - (strength * w)[:, None] * off[:, None] * nrm
                    v[~inside] = m.vertices[~inside]
        else:  # inflate: displacement = falloff * strength * radius * INFLATE_FRACTION
            amount = strength * radius * INFLATE_FRACTION
            for _ in range(iters):
                v = v + (w * amount)[:, None] * vn
    except OpError:
        raise
    except Exception as e:
        raise OpError(f"sculpt failed: {e}")

    # ---- a stroke that FOLDS the mesh is refused: the model is left untouched ----
    folded = _folded(v, faces, old_fn, inside)
    if folded:
        raise OpError(
            f"the sculpt stroke folded {folded} face(s) (degenerate or flipped) — refused; "
            f"lower the strength, radius or iterations and try again.")

    out = trimesh.Trimesh(v, faces, process=False)       # exact vertices: no reprocessing
    rep = {"brush": brush, "radius_mm": radius, "strength": strength, "iterations": iters,
           "vertices_moved": int(inside.sum()),
           **({"plane": {"point": [float(x) for x in plane[0]],
                        "normal": [float(x) for x in plane[1]]}} if plane else {}), **persist,
           "message": f"Sculpt ({brush}) — {int(inside.sum()):,} vertices, {iters} iteration(s)"
                      f" (the brush is a sphere in space: both sides of a thin wall move)"}
    if brush == "smooth":
        rep["message"] += " — Laplacian smoothing shrinks detail slightly; that is the trade"
    if persist:
        rep["_persist"] = persist                        # editproj merges this into the saved params
        rep["message"] += ", plane stored with the step"
    return _check(out), rep
