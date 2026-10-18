"""Voxel remesh (the 'best of Nomad' op): one-click watertight rebuild — original code in a
new module; meshedit.py gained exactly one OPS-table line. The op must repair broken meshes,
preserve volume (within the inherent half-voxel inflation), and refuse nonsense input."""
from __future__ import annotations

import pytest
import trimesh

from app.core import meshedit
from app.core.voxremesh import op_voxremesh


def _broken_box():
    """A genuinely open mesh (two faces missing, no processing to repair it)."""
    b = trimesh.creation.box((20, 20, 20))
    return trimesh.Trimesh(b.vertices, b.faces[:-2], process=False)


def test_voxremesh_repairs_a_broken_mesh():
    m = _broken_box()
    assert not m.is_watertight
    out, rep = op_voxremesh(m, {})
    assert out.is_watertight                       # the point: a fresh watertight mesh
    assert rep["watertight"] and rep["triangles_after"] > 0
    assert rep["volume_drift"] is None             # broken input has no meaningful volume: no false alarm
    # and it survives the ordinary apply() checks (what every editor op goes through)
    out2, _ = meshedit.apply(_broken_box(), "voxremesh", {})
    assert out2.is_watertight


def test_voxremesh_preserves_volume_within_tolerance():
    m = trimesh.creation.box((20, 20, 20))         # healthy: the drift guard applies
    out, rep = op_voxremesh(m, {"pitch": 0.5})
    assert out.is_watertight
    assert rep["volume_drift"] == pytest.approx(0.076, abs=0.05)   # the half-voxel inflation, nothing more
    assert abs(out.bounds[1][0] - 10.25) < 0.01   # world units: half a pitch outside the box


def test_voxremesh_rejects_bad_pitch():
    m = trimesh.creation.box((20, 20, 20))
    with pytest.raises(meshedit.OpError, match="pitch"):
        op_voxremesh(m, {"pitch": 0.001})         # below MIN_PITCH: would be 20000^3 voxels
    with pytest.raises(meshedit.OpError, match="pitch"):
        op_voxremesh(m, {"pitch": "abc"})
    with pytest.raises(meshedit.OpError, match="pitch"):
        op_voxremesh(m, {"pitch": 100})           # absurdly coarse


def test_voxremesh_is_registered_in_the_op_table():
    assert "voxremesh" in meshedit.OPS
    assert "Voxel remesh" in meshedit.label("voxremesh", {})


def test_voxremesh_through_the_real_api():
    """The op is reachable from the editor's ordinary /op endpoint (the protected edit.py
    dispatches any registered op — no changes were needed there)."""
    from tests.b1 import box_stl, client
    c = client()
    up = c.post("/api/edit/new", files={"file": ("b.stl", box_stl(), "application/octet-stream")})
    assert up.status_code == 200, up.text
    bid = up.json()["id"]
    r = c.post(f"/api/edit/{bid}/op", json={"op": "voxremesh", "params": {"pitch": 0.5}})
    assert r.status_code == 200, r.text
    steps = r.json()["ops"]
    assert steps[-1]["op"] == "voxremesh"
    # undo works on it like any step
    u = c.post(f"/api/edit/{bid}/undo")
    assert u.status_code == 200 and u.json()["head"] == len(steps) - 1
