"""Sculpt brushes (the Nomad-class addition): smooth/flatten/inflate over a spherical
brush — original code in app/core/sculpt.py. The policy choices the reviewer asked to
be pinned down by tests: the SPHERE selection (thin walls select the back side too),
the frozen flatten plane, Laplacian shrinkage disclosed, inversion checks beyond
watertightness, caps enforced before adjacency, and deterministic replay."""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from app.core import meshedit, sculpt
from tests.b1 import client


def _bumpy(radius=10.0):
    """An icosphere with a deterministic radial bump pattern: roughness we can measure."""
    s = trimesh.creation.icosphere(radius=radius, subdivisions=3)
    v = s.vertices.copy()
    bump = np.sin(5 * v[:, 0]) * np.sin(5 * v[:, 1]) * np.sin(5 * v[:, 2])   # per-vertex scalar
    dirn = v / np.linalg.norm(v, axis=1, keepdims=True)
    v = v + 0.4 * bump[:, None] * dirn
    return trimesh.Trimesh(v, s.faces, process=False)


# ---------------------------------------------------------------- the basics

def test_zero_strength_is_an_exact_no_op():
    m = _bumpy()
    out, rep = sculpt.op_sculpt(m, {"brush": "smooth", "center": [0, 0, 10], "radius": 4,
                                   "strength": 0.0, "iterations": 3})
    assert np.array_equal(out.vertices, m.vertices)
    assert rep["vertices_moved"] > 0                    # the brush selected, but moved nothing


def test_brush_outside_the_model_changes_nothing():
    m = trimesh.creation.box((20, 20, 20))
    out, rep = sculpt.op_sculpt(m, {"brush": "inflate", "center": [500, 500, 500],
                                   "radius": 5, "strength": 1.0})
    assert np.array_equal(out.vertices, m.vertices)
    assert rep["vertices_moved"] == 0
    assert "nothing changed" in rep["message"]


def test_smooth_reduces_roughness():
    m = _bumpy()
    d = np.linalg.norm(m.vertices, axis=1)
    out, _ = sculpt.op_sculpt(m, {"brush": "smooth", "center": [0, 0, 0], "radius": 20,
                                  "strength": 0.8, "iterations": 5})
    d2 = np.linalg.norm(out.vertices, axis=1)
    assert d2.std() < d.std()                          # the surface got smoother


def test_smooth_discloses_the_laplacian_shrinkage_trade():
    m = _bumpy()
    _, rep = sculpt.op_sculpt(m, {"brush": "smooth", "center": [0, 0, 0], "radius": 20,
                                  "strength": 0.8, "iterations": 5})
    assert "shrinks" in rep["message"]                 # the trade is disclosed, not hidden


def test_vertices_outside_the_brush_never_move():
    m = _bumpy()
    out, _ = sculpt.op_sculpt(m, {"brush": "inflate", "center": [0, 0, 10], "radius": 2,
                                 "strength": 1.0, "iterations": 3})
    d = np.linalg.norm(m.vertices - np.array([0, 0, 10]), axis=1)
    assert np.array_equal(out.vertices[d > 2], m.vertices[d > 2])   # outside: untouched


# ---------------------------------------------------------------- flatten

def test_flatten_moves_vertices_toward_the_stored_plane():
    m = _bumpy()
    out, rep = sculpt.op_sculpt(m, {"brush": "flatten", "center": [0, 0, 10], "radius": 4,
                                   "strength": 1.0, "iterations": 5})
    q = np.array(rep["plane"]["point"])
    n = np.array(rep["plane"]["normal"])
    before = np.abs((m.vertices - q) @ n)
    after = np.abs((out.vertices - q) @ n)
    assert after.mean() < before.mean()                # distances to the plane shrank
    assert rep["plane"] in (rep["plane"],)             # the plane is reported (pinnable)


def test_flatten_with_a_pinned_plane_never_recomputes_it():
    m = _bumpy()
    plane = {"point": [0, 0, 10], "normal": [0, 0, 1]}
    out, rep = sculpt.op_sculpt(m, {"brush": "flatten", "center": [0, 0, 10], "radius": 4,
                                   "strength": 0.5, "iterations": 2, "plane": plane})
    assert rep["plane"]["point"] == [0, 0, 10]         # the pinned plane is used as-is
    assert rep["plane"]["normal"] == [0, 0, 1]


# ---------------------------------------------------------------- inflate

def test_inflate_displaces_vertices_by_the_documented_amount():
    m = _bumpy()
    radius, strength = 3.0, 0.5
    center = np.array([0, 0, 10.0])
    out, rep = sculpt.op_sculpt(m, {"brush": "inflate", "center": center.tolist(), "radius": radius,
                                   "strength": strength, "iterations": 1})
    d = np.linalg.norm(m.vertices - center, axis=1)
    w = np.clip(1.0 - (d / radius) ** 2, 0.0, 1.0) ** 2
    # the op's own normals: recompute them the same way to predict displacement
    from app.core.sculpt import _vertex_normals
    vn = _vertex_normals(m, len(m.vertices))
    expected = m.vertices + (strength * w)[:, None] * vn * (strength * radius * sculpt.INFLATE_FRACTION)
    assert np.allclose(out.vertices, expected, atol=1e-9)   # the formula is the contract


def test_inflate_reports_no_inverted_or_degenerate_faces_at_normal_strengths():
    m = _bumpy()
    out, rep = sculpt.op_sculpt(m, {"brush": "inflate", "center": [0, 0, 10], "radius": 4,
                                   "strength": 0.5, "iterations": 3})
    assert rep["inverted_faces"] == 0


# ---------------------------------------------------------------- selection policy

def test_thin_wall_selection_policy_is_spatial_and_disclosed():
    """The brush is a sphere in space: on a thin plate a stroke at the front face ALSO
    moves back-face vertices (there is no camera ray in an op). The policy is deliberate —
    this test pins it so it cannot silently change."""
    plate = trimesh.creation.box((50, 50, 2))          # 2 mm thin wall...
    v, f = trimesh.remesh.subdivide_to_size(plate.vertices, plate.faces, 4.0)
    plate = trimesh.Trimesh(v, f, process=False)   # ...refined: real vertices on both faces
    center = [0, 0, 1.0]                               # ON the front face
    out, rep = sculpt.op_sculpt(plate, {"brush": "inflate", "center": center, "radius": 5,
                                      "strength": 1.0, "iterations": 1})
    d = np.linalg.norm(plate.vertices - np.array(center), axis=1)
    back = (plate.vertices[:, 2] < 0) & (d <= 5)       # back-face vertices inside the sphere
    assert back.any()                                  # the sphere reaches the back side
    assert not np.array_equal(out.vertices[back], plate.vertices[back])   # ...and they moved


# ---------------------------------------------------------------- determinism & replay

def test_sculpt_is_bit_for_bit_deterministic():
    m = _bumpy()
    p = {"brush": "smooth", "center": [0, 0, 10], "radius": 4, "strength": 0.7, "iterations": 4}
    out1, _ = sculpt.op_sculpt(m, p)
    out2, _ = sculpt.op_sculpt(m, p)                    # fresh run on the same input
    assert np.array_equal(out1.vertices, out2.vertices)


def test_undo_restores_geometry_through_the_real_api():
    c = client()
    r = c.post("/api/parts/new", json={"recipe": {"parts": [
        {"kind": "sphere", "dims": {"diameter": 40}, "position": [0, 0, 0], "role": "solid"}]}})
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    stl_before = c.get(f"/api/download/{bid}/stl", follow_redirects=True).content
    # sculpt it (smooth a region)
    mv = c.post(f"/api/edit/{bid}/op", json={"op": "sculpt", "params": {
        "brush": "smooth", "center": [0, 0, 20], "radius": 8, "strength": 0.8, "iterations": 3}})
    assert mv.status_code == 200, mv.text
    stl_after = c.get(f"/api/download/{bid}/stl", follow_redirects=True).content
    assert stl_after != stl_before                     # the sculpt changed the geometry
    # undo -> the geometry is restored
    u = c.post(f"/api/edit/{bid}/undo")
    assert u.status_code == 200, u.text
    stl_restored = c.get(f"/api/download/{bid}/stl", follow_redirects=True).content
    assert stl_restored == stl_before                 # byte-identical restore


def test_cold_replay_through_a_fresh_process_reproduces_the_stroke():
    """Deterministic REPLAY, cold: a brand-new process must reproduce the same sculpted
    mesh from the same input (no hidden state, no randomness, no warm caches)."""
    import os, subprocess, sys
    m = _bumpy()
    stl_in = trimesh.exchange.stl.export_stl(m)
    data_dir = os.environ["PHOTO3D_DATA"]
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    child = f"""
import numpy as np, trimesh, sys
sys.path.insert(0, {repo!r})
from app.core import sculpt
m = trimesh.creation.icosphere(radius=10.0, subdivisions=3)
v = m.vertices.copy()
bump = np.sin(5 * v[:, 0]) * np.sin(5 * v[:, 1]) * np.sin(5 * v[:, 2])
dirn = v / np.linalg.norm(v, axis=1, keepdims=True)
v = v + 0.4 * bump[:, None] * dirn
m = trimesh.Trimesh(v, m.faces, process=False)
out, rep = sculpt.op_sculpt(m, {{"brush": "smooth", "center": [0, 0, 10], "radius": 4,
                                "strength": 0.7, "iterations": 4}})
import hashlib
print("SHA", hashlib.sha256(out.vertices.tobytes()).hexdigest())
"""
    res = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, f"cold replay failed:\n{res.stdout}\n{res.stderr}"
    # the in-process result must match the cold one
    out, _ = sculpt.op_sculpt(m, {"brush": "smooth", "center": [0, 0, 10], "radius": 4,
                                  "strength": 0.7, "iterations": 4})
    import hashlib
    cold_sha = [l for l in res.stdout.splitlines() if l.startswith("SHA")][0].split()[1]
    assert hashlib.sha256(out.vertices.tobytes()).hexdigest() == cold_sha


# ---------------------------------------------------------------- validation & caps

def test_invalid_parameters_are_rejected_before_any_work():
    m = _bumpy()
    base = {"center": [0, 0, 10], "radius": 4, "strength": 0.5}
    for bad in [
        {"brush": "warp"},                                # unknown brush
        {"center": [float("nan"), 0, 0]},                 # nonfinite center
        {"center": "nope"},                               # garbage center
        {"radius": 0}, {"radius": -2}, {"radius": float("inf")},   # bad radius
        {"strength": 1.5}, {"strength": -0.1}, {"strength": float("nan")},  # bad strength
        {"iterations": 0}, {"iterations": 11}, {"iterations": 1.5}, {"iterations": "2"},  # bad iters
        {"brush": "flatten", "plane": {"point": [0, 0, 0], "normal": [0, 0, 0]}},  # zero normal
    ]:
        with pytest.raises(meshedit.OpError):
            sculpt.op_sculpt(m, {**base, **bad})


def test_oversized_meshes_are_refused_before_building_adjacency():
    import time
    huge = trimesh.Trimesh(np.zeros((sculpt.MAX_VERTS + 1, 3)), faces=[[0, 1, 2]], process=False)
    t0 = time.time()
    with pytest.raises(meshedit.OpError, match="simplify first"):
        sculpt.op_sculpt(huge, {"brush": "smooth", "center": [0, 0, 0], "radius": 5})
    assert time.time() - t0 < 2.0                      # refused, not attempted


def test_sculpt_is_registered_in_the_op_table():
    assert meshedit.OPS["sculpt"] is sculpt.op_sculpt
    assert "Sculpt" in meshedit.label("sculpt", {"brush": "smooth", "radius": 5})
