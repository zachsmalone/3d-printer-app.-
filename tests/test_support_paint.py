"""Paint-on supports: stroke validation, enforcer/blocker meshes, PrusaSlicer 3MF volume types."""
import json
import zipfile
from pathlib import Path

import pytest
import trimesh
from fastapi.testclient import TestClient

from app.main import app
from app.services import support_paint as sp


def test_painted_column_meets_the_hit_point():
    """The enforcer and the blocker are volumes around the point that was hit, not a mark on an empty bed."""
    hit = {"kind": "enforce", "x": 4.0, "y": -2.0, "z": 18.0, "r": 3, "h": 8, "thickness": 2, "tip_r": 1}
    enf = sp.stroke_mesh(hit)
    assert enf.bounds[0][2] <= 18.0 <= enf.bounds[1][2]
    assert abs(enf.centroid[0] - 4.0) < 3 and abs(enf.centroid[1] + 2.0) < 3
    blk = sp.stroke_mesh({**hit, "kind": "block", "z": 3.0})
    assert blk.bounds[0][2] <= 3.0 <= blk.bounds[1][2]
    with pytest.raises(sp.PaintError):
        sp.parse_strokes([{"kind": "erase", "x": 0, "y": 0}])


def test_view_sample_is_made_of_original_vertices():
    """The on-screen mesh is a subset of the file's own triangles, so a hit on it is a point on the real surface."""
    import base64
    import numpy as np
    from app.services.editproj import iter_binary_stl_preview
    mesh = trimesh.creation.icosphere(2, radius=12)
    data = mesh.export(file_type="stl")
    ready = [e for e in iter_binary_stl_preview(data, max_faces=20) if e["phase"] == "preview_ready"][-1]
    pos = np.frombuffer(base64.b64decode(ready["preview"]["bodies"][0]["positions"]), dtype="<f4").reshape(-1, 3)
    src = np.asarray(mesh.vertices, dtype=np.float32)
    # Every preview vertex is an original vertex (same coordinates, not a shrunk stand-in).
    for p in pos[:: max(1, len(pos) // 30)]:
        d = np.linalg.norm(src - p, axis=1).min()
        assert d < 1e-3, d


def test_paint_persists_for_this_shape_and_hides_after_a_move():
    from tests.b1 import ADULT, client
    c = client(ADULT)
    stl = trimesh.creation.box((12, 10, 8)).export(file_type="stl")
    made = c.post("/api/edit/new", files={"file": ("box.stl", stl, "model/stl")})
    assert made.status_code == 200, made.text
    bid = made.json()["id"]
    strokes = [{"kind": "enforce", "x": 1, "y": 2, "z": 4, "r": 2, "h": 6},
               {"kind": "block", "x": 3, "y": 1, "z": 4, "r": 2, "h": 6}]
    put = c.put(f"/api/edit/{bid}/support-paint", json={"strokes": strokes})
    assert put.status_code == 200, put.text
    view = c.get(f"/api/edit/{bid}").json()["support_paint"]
    assert view["stale"] is False and len(view["strokes"]) == 2
    moved = c.post(f"/api/edit/{bid}/op", json={"op": "translate", "params": {"dz": 3}})
    assert moved.status_code == 200, moved.text
    hidden = c.get(f"/api/edit/{bid}").json()["support_paint"]
    assert hidden["strokes"] == [] and hidden["stale"] is True
    assert c.post(f"/api/edit/{bid}/undo").status_code == 200
    back = c.get(f"/api/edit/{bid}").json()["support_paint"]
    assert back["stale"] is False and len(back["strokes"]) == 2


def test_parse_rejects_bad_kind_and_too_many():
    with pytest.raises(sp.PaintError, match="enforce"):
        sp.parse_strokes([{"kind": "maybe", "x": 0, "y": 0}])
    with pytest.raises(sp.PaintError, match="too many"):
        sp.parse_strokes([{"kind": "enforce", "x": 0, "y": 0, "r": 2}] * (sp.MAX_STROKES + 1))


def test_parse_accepts_json_string_and_empty():
    assert sp.parse_strokes(None) == []
    assert sp.parse_strokes("[]") == []
    got = sp.parse_strokes('[{"kind":"block","x":10,"y":20,"r":3}]')
    assert got[0]["kind"] == "block" and got[0]["x"] == 10.0 and got[0]["y"] == 20.0
    assert got[0]["z"] == 0.0 and got[0]["r"] == 3.0 and got[0]["h"] == sp.H_DEFAULT
    assert got[0].get("filament_slot") == "same"
    assert "tip_r" in got[0] and "thickness" in got[0]


def test_meshes_and_3mf_carry_prusaslicer_volume_types(tmp_path):
    strokes = [
        {"kind": "enforce", "x": 30, "y": 40, "z": 0, "r": 4, "h": 8},
        {"kind": "block", "x": 50, "y": 60, "z": 0, "r": 3, "h": 8},
    ]
    parts = sp.meshes_from_strokes(strokes)
    assert len(parts) == 2 and parts[0][0] == "enforce" and parts[1][0] == "block"
    assert all(m.is_volume or len(m.faces) > 0 for _, m in parts)

    model = trimesh.creation.box(extents=(20, 20, 10))
    model.apply_translation([0, 0, 5])
    out = tmp_path / "paint.3mf"
    info = sp.write_paint_3mf(model, strokes, out)
    assert info["enforcers"] == 1 and info["blockers"] == 1 and info["objects"] == 3
    assert "not K1-tested" in info["note"] or "Not tested" in info["note"]
    with zipfile.ZipFile(out) as z:
        xml = z.read("3D/3dmodel.model").decode()
    assert "SupportEnforcer" in xml and "SupportBlocker" in xml
    assert "slic3rpe:volume type" in xml


def test_slice_api_rejects_bad_paint_and_accepts_good(tmp_path, monkeypatch):
    """Bad paint -> 400 before the engine runs. Good paint builds a 3MF (engine may be stubbed)."""
    client = TestClient(app)
    # tiny STL
    box = trimesh.creation.box(extents=(15, 15, 8))
    stl = tmp_path / "t.stl"
    stl.write_bytes(box.export(file_type="stl"))

    r = client.post("/api/slice", data={"printer_id": "creality_k1", "nozzle": "0.4", "supports": "off",
                                        "support_paint": "not-json", "material": "PLA"},
                    files={"file": ("t.stl", stl.read_bytes(), "application/sla")})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "bad_paint"

    # Stub the engine so CI boxes without a long slice still cover the paint path.
    from app.services import slice_engine as eng

    def fake_slice(model, profile, out_gcode, *, bounds_stl=None, parts=None):
        out_gcode.write_text("; estimated printing time (normal mode) = 1m 0s\n; total filament used [g] = 1.5\n")
        assert model.suffix == ".3mf"
        assert "SupportEnforcer" in zipfile.ZipFile(model).read("3D/3dmodel.model").decode()
        return eng.SliceResult(out_gcode, 60, 1.5, (15.0, 15.0, 8.0), profile)

    monkeypatch.setattr(eng, "slice_model_path", fake_slice)
    paint = json.dumps([{"kind": "enforce", "x": 5, "y": 5, "r": 3}])
    r = client.post("/api/slice", data={"printer_id": "creality_k1", "nozzle": "0.4", "supports": "off",
                                        "support_paint": paint, "material": "PLA", "ventilation_ok": "true"},
                    files={"file": ("t.stl", stl.read_bytes(), "application/sla")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["support_paint"]["enforcers"] == 1
    assert body["support_paint"].get("supports_forced") == "auto"
    assert body["settings"]["supports"] == "auto"
