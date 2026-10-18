"""Lindsi's CAD UI fixes: N2 (stale import warning after Fix mesh), B13 (edge length readout) and #shTabs at 320 px."""
import io

import numpy as np
import trimesh
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


def _open_flipped_stl():
    """Same as Kobi's samples/open_flipped.stl: a 20 mm cube with 2 faces removed and 4 flipped."""
    m = trimesh.creation.box(extents=(20, 20, 20)); m.apply_translation((10, 10, 10))
    keep = np.ones(len(m.faces), bool); keep[:2] = False; m.update_faces(keep)
    f = m.faces.copy(); f[:4] = f[:4, ::-1]
    return trimesh.Trimesh(m.vertices, f, process=False).export(file_type="stl")


def _gate(p):
    return [w for w in p["warnings"] if w.startswith("Fix the model before export")]


def test_n2_fix_mesh_clears_stale_not_watertight_warning_and_it_comes_back_on_undo():
    j = c.post("/api/edit/new", files={"file": ("open_flipped.stl", io.BytesIO(_open_flipped_stl()), "model/stl")}).json()
    bid = j.get("id") or j["project"]["id"]
    p = c.get(f"/api/edit/{bid}").json()
    assert not p["analysis"]["watertight"] and _gate(p) and "not watertight" in _gate(p)[0]
    r = c.post(f"/api/edit/{bid}/op", json={"op": "repair", "params": {}}); assert r.status_code == 200, r.text
    p = r.json()
    assert p["analysis"]["watertight"] and p["quality_gate"]["ok"] and "watertight ✔" in p["report"]["message"]
    assert not _gate(p), p["warnings"]                                    # the import-time warning is gone
    assert not _gate(c.get(f"/api/edit/{bid}").json())
    p = c.post(f"/api/edit/{bid}/undo").json()                           # back to the open mesh: the warning is back, once
    p = c.get(f"/api/edit/{bid}").json()
    assert not p["analysis"]["watertight"] and len(_gate(p)) == 1 and "not watertight" in _gate(p)[0]
