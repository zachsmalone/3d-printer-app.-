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

@pytest.mark.parametrize("brush", ["smooth", "flatten", "inflate"])
def test_zero_strength_is_an_exact_no_op(brush):
    m = _bumpy()
    out, rep = sculpt.op_sculpt(m, {"brush": brush, "center": [0, 0, 10], "radius": 4,
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


def test_flatten_with_a_pinned_plane_never_recomputes_it():
    m = _bumpy()
    plane = {"point": [0, 0, 10], "normal": [0, 0, 1]}
    out, rep = sculpt.op_sculpt(m, {"brush": "flatten", "center": [0, 0, 10], "radius": 4,
                                   "strength": 0.5, "iterations": 2, "plane": plane})
    assert rep["plane"]["point"] == [0, 0, 10]         # the pinned plane is used as-is
    assert rep["plane"]["normal"] == [0, 0, 1]


# ---------------------------------------------------------------- inflate

def _flat_grid(size=20.0, step=2.5):
    """A flat grid on z=0: every vertex normal is EXACTLY (0,0,1) — displacement is
    analytically known without calling any of the op's internals."""
    xs = np.round(np.arange(-size, size + 1e-9, step), 6)
    n = len(xs)
    xg, yg = np.meshgrid(xs, xs)
    v = np.column_stack([xg.ravel(), yg.ravel(), np.zeros(xg.size)])
    def vid(i, j): return j * n + i          # meshgrid ravel is row-major: row j, col i
    f = []
    for i in range(n - 1):
        for j in range(n - 1):
            a, b, c, d = vid(i, j), vid(i + 1, j), vid(i, j + 1), vid(i + 1, j + 1)
            f += [[a, b, c], [b, d, c]]
    return trimesh.Trimesh(v, np.array(f), process=False)


def test_inflate_displaces_vertices_by_the_documented_amount():
    m = _flat_grid()
    radius, strength = 5.0, 0.5
    center = np.array([0.0, 0.0, 0.0])
    out, _ = sculpt.op_sculpt(m, {"brush": "inflate", "center": center.tolist(), "radius": radius,
                                 "strength": strength, "iterations": 1})
    # analytical expectation: a flat grid's normals are all +z, so the displacement is
    # pure +z: w(d) * strength * radius * INFLATE_FRACTION — computed HERE, independently.
    d = np.linalg.norm(m.vertices - center, axis=1)
    w = np.clip(1.0 - (d / radius) ** 2, 0.0, 1.0) ** 2
    expected_z = w * strength * radius * sculpt.INFLATE_FRACTION
    assert np.allclose(out.vertices[:, 0], m.vertices[:, 0], atol=1e-9)   # x untouched
    assert np.allclose(out.vertices[:, 1], m.vertices[:, 1], atol=1e-9)   # y untouched
    assert np.allclose(out.vertices[:, 2], expected_z, atol=1e-9)         # z = the formula
    # and strength appears ONCE (not squared): the center vertex moves exactly
    # strength * radius * INFLATE_FRACTION — if it were applied twice, this would be
    # strength**2 * radius * INFLATE_FRACTION = half the value at strength 0.5.
    assert abs(expected_z.max() - strength * radius * sculpt.INFLATE_FRACTION) < 1e-12


def test_a_folding_stroke_is_refused_and_the_input_preserved():
    """Adversarial: a stroke whose result contains folded/degenerate faces must be
    REFUSED (not warned about), and the input mesh left untouched — exactly the case
    watertightness checks miss. The brush math (falloff-capped displacement) makes a
    healthy mesh very hard to fold, so the adversarial input carries a degenerate
    (zero-area) face INSIDE the brush area: the stroke refuses rather than carry that
    damage silently into the result. Pre-existing damage OUTSIDE the brush must NOT
    block the stroke (only touched faces count)."""
    m = _flat_grid()
    c = int(np.argmin(np.linalg.norm(m.vertices - [0, 0, 0], axis=1)))   # the centre vertex
    f = m.faces.copy()
    f[0] = [c, c, c + 1]                               # a zero-area face AT the centre (in the brush)
    damaged = trimesh.Trimesh(m.vertices, f, process=False)
    before = damaged.vertices.copy()
    with pytest.raises(meshedit.OpError, match="folded"):
        sculpt.op_sculpt(damaged, {"brush": "inflate", "center": [0, 0, 0], "radius": 5,
                                   "strength": 0.5, "iterations": 1})
    assert np.array_equal(damaged.vertices, before)     # the input mesh is untouched
    # ...but the SAME damage far from the brush does not block the stroke
    f2 = m.faces.copy()
    f2[-1] = [f2[-1][0], f2[-1][0], f2[-1][1]]          # degenerate face at the rim, outside
    far = trimesh.Trimesh(m.vertices, f2, process=False)
    out, _ = sculpt.op_sculpt(far, {"brush": "inflate", "center": [0, 0, 0], "radius": 5,
                                    "strength": 0.5, "iterations": 1})
    assert out.is_watertight or len(out.faces) > 0       # accepted: untouched by the stroke


def test_reasonable_strokes_produce_no_folded_faces():
    for brush, params in [("inflate", {"center": [0, 0, 10], "radius": 4, "strength": 0.5, "iterations": 3}),
                          ("smooth", {"center": [0, 0, 10], "radius": 4, "strength": 0.5, "iterations": 3}),
                          ("flatten", {"center": [0, 0, 10], "radius": 4, "strength": 0.5, "iterations": 3})]:
        m = _bumpy()
        out, _ = sculpt.op_sculpt(m, {"brush": brush, **params})   # no OpError => no folds


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


def test_flatten_plane_is_persisted_into_the_saved_step_params():
    """The advisor's persistence requirement: the auto-derived plane must be SAVED with
    the step (ops[...]["params"]), not just returned in the report — so a replay after
    an earlier step changed reuses the SAME plane instead of deriving a different one."""
    c = client()
    r = c.post("/api/parts/new", json={"recipe": {"parts": [
        {"kind": "sphere", "dims": {"diameter": 40}, "position": [0, 0, 0], "role": "solid"}]}})
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    mv = c.post(f"/api/edit/{bid}/op", json={"op": "sculpt", "params": {
        "brush": "flatten", "center": [0, 0, 20], "radius": 8, "strength": 0.5, "iterations": 2}})
    assert mv.status_code == 200, mv.text
    p = c.get(f"/api/edit/{bid}")
    step = p.json()["ops"][-1]
    assert step["op"] == "sculpt"
    assert "plane" in step["params"]                     # PERSISTED, not just reported
    pl = step["params"]["plane"]
    assert len(pl["point"]) == 3 and len(pl["normal"]) == 3


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
        {"center": [0, 0, 0, 0]},                        # FOUR coordinates: no truncation
        {"center": [[0, 0], [0, 0]]},                   # ragged shape
        {"brush": "flatten", "plane": {"point": [0, 0, 0, 0], "normal": [0, 0, 1]}},  # 4-coord plane
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


def _single_triangle():
    """A=(0,0,0), B=(1,0,0), C=(0,1,0): normal +z. Analytically predictable."""
    v = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    f = np.array([[0, 1, 2]])
    return trimesh.Trimesh(v, f, process=False)


def test_a_flatten_stroke_that_flips_the_face_is_refused():
    """The reviewer's analytical fixture. Flatten at A with radius 0.5 (only A inside),
    strength 1, one iteration, plane point (2,0,0) normal (1,0,0): A moves to (2,0,0)
    and the triangle's normal REVERSES (+z -> -z). The stroke must be refused and the
    input preserved."""
    m = _single_triangle()
    with pytest.raises(meshedit.OpError, match="folded"):
        sculpt.op_sculpt(m, {"brush": "flatten", "center": [0, 0, 0], "radius": 0.5,
                             "strength": 1.0, "iterations": 1,
                             "plane": {"point": [2, 0, 0], "normal": [1, 0, 0]}})
    assert np.array_equal(m.vertices, np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0]]))  # untouched


def test_a_flatten_stroke_that_collapses_the_face_is_refused():
    """Same fixture with plane point (1,0,0): A collapses exactly onto B — a zero-area
    (degenerate) face. Refused, input preserved."""
    m = _single_triangle()
    with pytest.raises(meshedit.OpError, match="folded"):
        sculpt.op_sculpt(m, {"brush": "flatten", "center": [0, 0, 0], "radius": 0.5,
                             "strength": 1.0, "iterations": 1,
                             "plane": {"point": [1, 0, 0], "normal": [1, 0, 0]}})
    assert np.array_equal(m.vertices, np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0]]))


def test_a_folding_stroke_through_the_history_path_changes_nothing():
    """The refusal must hold through the real op endpoint: the step is NOT added, the
    saved ops and the exported STL are byte-identical to before."""
    c = client()
    r = c.post("/api/parts/new", json={"recipe": {"parts": [
        {"kind": "sphere", "dims": {"diameter": 40}, "position": [0, 0, 0], "role": "solid"}]}})
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    stl_before = c.get(f"/api/download/{bid}/stl", follow_redirects=True).content
    ops_before = c.get(f"/api/edit/{bid}").json()["ops"]
    # the analytical flip, transplanted onto the sphere's top vertex region
    mv = c.post(f"/api/edit/{bid}/op", json={"op": "sculpt", "params": {
        "brush": "flatten", "center": [0, 0, 20], "radius": 0.5, "strength": 1.0,
        "iterations": 1, "plane": {"point": [22, 0, 20], "normal": [1, 0, 0]}}})
    assert mv.status_code in (400, 422), mv.text                # refused by the service
    ops_after = c.get(f"/api/edit/{bid}").json()["ops"]
    assert ops_after == ops_before                              # history untouched
    stl_after = c.get(f"/api/download/{bid}/stl", follow_redirects=True).content
    assert stl_after == stl_before                              # exports untouched


def test_editing_a_flatten_step_keeps_its_stored_plane():
    """edit_step must not lose a persisted plane when the caller edits other params —
    and an EARLIER recipe change must not move it either (replay reuses the stored
    plane instead of deriving a new one from the changed mesh)."""
    from app.services import editproj
    c = client()
    r = c.post("/api/parts/new", json={"recipe": {"parts": [
        {"kind": "sphere", "dims": {"diameter": 40}, "position": [0, 0, 0], "role": "solid"}]}})
    bid = r.json()["id"]
    mv = c.post(f"/api/edit/{bid}/op", json={"op": "sculpt", "params": {
        "brush": "flatten", "center": [0, 0, 20], "radius": 6, "strength": 0.5, "iterations": 1}})
    assert mv.status_code == 200, mv.text
    steps = c.get(f"/api/edit/{bid}").json()["ops"]
    stored_plane = steps[1]["params"]["plane"]
    assert stored_plane
    # edit the flatten step (strength only, no plane): the stored plane survives
    editproj.edit_step(bid, 2, {"brush": "flatten", "center": [0, 0, 20], "radius": 6,
                                 "strength": 0.3, "iterations": 1})
    steps2 = c.get(f"/api/edit/{bid}").json()["ops"]
    assert steps2[1]["params"]["plane"] == stored_plane        # NOT re-derived
    # and an EARLIER step change (bigger sphere) must not move the stored plane either
    c.put(f"/api/parts/{bid}/recipe", json={"recipe": {"parts": [
        {"kind": "sphere", "dims": {"diameter": 44}, "position": [0, 0, 0], "role": "solid"}]}})
    steps3 = c.get(f"/api/edit/{bid}").json()["ops"]
    assert steps3[1]["params"]["plane"] == stored_plane        # replay reuses it


def test_strict_vector_shapes_are_rejected():
    m = _bumpy()
    for bad in [
        {"center": [[1, 2, 3]]},              # (1,3): not a 3-vector
        {"center": [[1], [2], [3]]},           # (3,1): not a 3-vector
        {"brush": "flatten", "plane": {"point": [[0, 0, 0]], "normal": [0, 0, 1]}},  # (1,3)
        {"brush": "flatten", "plane": {"point": [[0], [0], [0]], "normal": [0, 0, 1]}},  # (3,1)
    ]:
        with pytest.raises(meshedit.OpError):
            sculpt.op_sculpt(m, {**{"center": [0, 0, 10], "radius": 4, "strength": 0.5}, **bad})


def test_zero_strength_flatten_needs_no_derivable_plane():
    """A zero-strength flatten on a selection whose normals cancel (a stroke that moves
    nothing) must be a clean no-op — not an error about an unusable normal."""
    # two facing triangles: averaged selection normals cancel out
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0.5], [1, 0, 0.5], [0, 1, 0.5]])
    f = np.array([[0, 1, 2], [3, 5, 4]])                     # opposite windings
    m = trimesh.Trimesh(v, f, process=False)
    out, rep = sculpt.op_sculpt(m, {"brush": "flatten", "center": [0.2, 0.2, 0.25],
                                    "radius": 2, "strength": 0.0, "iterations": 3})
    assert np.array_equal(out.vertices, m.vertices)
