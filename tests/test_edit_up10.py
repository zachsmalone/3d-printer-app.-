"""Edit upgrades 1–10 (joints on cut, colour highlights, drain holes, curved text,
checklist fixes, volcost, scale-to-target, custom fonts/styles, threads, adjustable supports)."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from app.core import cadthread, meshedit, printcheck, volcost
from app.main import app
from app.services import support_paint as sp
from tests.b1 import ADULT, client


def _box(x=40, y=30, z=20):
    m = trimesh.creation.box([x, y, z])
    m.apply_translation([0, 0, z / 2])
    return m


# --- 1. Joints on plain cuts with tolerance ---
@pytest.mark.parametrize("join", ["glue", "magnet", "pin", "dovetail"])
def test_cut_join_options(join):
    out, rep = meshedit.op_cut(_box(60, 40, 30), {
        "axis": "z", "position": 15, "keep": "both", "gap": 2, "join": join,
        "magnet_diameter": 6, "magnet_thickness": 3, "clearance": 0.25, "count": 2,
        "pin_diameter": 3, "engagement": 6,
        "depth": 4, "mouth_width": 8, "root_width": 5,
    })
    assert out is not None and len(out.faces) > 0
    assert rep.get("join", {}).get("join") == join or join == "glue"
    if join != "glue":
        assert rep["join"].get("connector_fit") == "simulated"


def test_cut_join_none_is_plain():
    out, rep = meshedit.op_cut(_box(), {"axis": "z", "position": 10, "keep": "both", "join": "none"})
    assert "join" not in rep or not rep.get("join")


# --- 2. Colour problem highlights ---
def test_printcheck_highlights_and_fixes():
    m = _box(40, 10, 40)
    T = trimesh.transformations.rotation_matrix(np.radians(35), [1, 0, 0])
    m.apply_transform(T)
    m.apply_translation([0, 0, -m.bounds[0][2]])
    r = printcheck.run(m, (220, 220, 250))
    assert "highlights" in r and "faces" in r["highlights"]
    assert "colors" in r["highlights"]
    assert any(i.get("code") == "overhang" for i in r["issues_meta"])
    ids = {f["id"] for f in r["fixes"]}
    assert "paint_supports" in ids or "best_orient_oh" in ids


# --- 3. User-placed resin drain holes ---
def test_hollow_user_drain_points():
    out, rep = meshedit.op_hollow(_box(30, 30, 30), {
        "wall": 2, "drain_diameter": 3,
        "drain_points": [{"x": 0, "y": 0, "z": 0, "diameter": 4}],
    })
    assert "1 drain" in rep["message"].lower() or "drain" in rep["message"].lower()
    assert out.volume < _box(30, 30, 30).volume * 0.95


# --- 4. Curved-surface text ---
def test_text_surface_placement():
    m = _box(40, 40, 20)
    out, rep = meshedit.op_text(m, {
        "text": "OK", "font": "dejavu", "mode": "emboss", "height": 6, "depth": 1.2,
        "placement": "surface", "point": [0, 0, 20], "normal": [0, 0, 1], "wrap": False,
    })
    assert rep.get("placement") == "surface"
    assert out.volume > m.volume  # emboss adds


# --- 5. Checklist one-tap fixes ---
def test_printcheck_endpoint_fixes_payload():
    c = client(ADULT)
    stl = _box(20, 20, 0.4).export(file_type="stl")
    j = c.post("/api/edit/new", files={"file": ("t.stl", io.BytesIO(stl), "model/stl")}).json()
    bid = j.get("id") or j["project"]["id"]
    r = c.get(f"/api/edit/{bid}/printcheck")
    assert r.status_code == 200
    body = r.json()
    assert "fixes" in body and "highlights" in body and "issues_meta" in body
    assert any(f.get("op") or f.get("action") for f in body["fixes"])


# --- 6. Material and cost from volume ---
def test_volcost_estimate():
    r = volcost.estimate(_box(20, 20, 20), "PLA", price_per_kg=20, infill_pct=20)
    assert r["ok"] and r["grams"] > 0 and r["cost"] > 0
    assert r["material"] == "PLA"


def test_volcost_endpoint():
    c = client(ADULT)
    stl = _box(20, 20, 20).export(file_type="stl")
    j = c.post("/api/edit/new", files={"file": ("t.stl", io.BytesIO(stl), "model/stl")}).json()
    bid = j.get("id") or j["project"]["id"]
    r = c.get(f"/api/edit/{bid}/volcost?material=PLA&infill_pct=15&price_per_kg=22")
    assert r.status_code == 200 and r.json()["ok"] is True


# --- 7. Scale to target size / bed / volume ---
def test_scale_longest_fit_bed_volume():
    m = _box(50, 30, 20)
    out, rep = meshedit.op_scale(m.copy(), {"mode": "longest", "target_longest": 100, "pivot": "base"})
    assert abs(max(out.extents) - 100) < 0.5
    assert "longest" in rep.get("message", "").lower() or "100" in rep.get("message", "")

    out2, rep2 = meshedit.op_scale(m.copy(), {"mode": "fit_bed", "bed": [80, 80, 80], "margin": 2, "pivot": "base"})
    assert max(out2.extents) <= 80

    target_cm3 = 10.0
    out3, rep3 = meshedit.op_scale(m.copy(), {"mode": "volume", "target_volume_cm3": target_cm3, "pivot": "base"})
    assert abs(out3.volume / 1000.0 - target_cm3) < 0.5


# --- 8. Custom fonts + list_fonts ---
def test_list_fonts_and_upload(tmp_path, monkeypatch):
    fonts = meshedit.list_fonts()
    assert isinstance(fonts, list) and len(fonts) >= 1
    # Minimal valid-enough TTF-ish file: write a tiny dummy and ensure endpoint rejects garbage or accepts ttf
    c = client(ADULT)
    stl = _box().export(file_type="stl")
    j = c.post("/api/edit/new", files={"file": ("t.stl", io.BytesIO(stl), "model/stl")}).json()
    bid = j.get("id") or j["project"]["id"]
    # Reject non-font
    bad = c.post(f"/api/edit/{bid}/fonts", files={"file": ("x.txt", b"not a font", "text/plain")})
    assert bad.status_code in (400, 415, 422)


# --- 9. Threaded connectors ---
def test_thread_external_and_internal():
    m = _box(30, 30, 25)
    out, rep = meshedit.op_thread(m.copy(), {
        "mode": "external", "axis": "z", "diameter": 8, "length": 12, "pitch": 1.25,
        "clearance": 0.2, "position": [0, 0, 25],
    })
    assert out.volume > m.volume - 1e-3
    assert len(out.faces) > len(m.faces)
    assert rep.get("mode") == "external"
    assert "external" in rep.get("message", "").lower()

    out2, rep2 = meshedit.op_thread(m.copy(), {
        "mode": "internal", "axis": "z", "diameter": 10, "length": 10, "pitch": 1.5,
        "clearance": 0.25, "position": [0, 0, 12],
    })
    assert out2.volume < m.volume
    assert rep2.get("mode") == "internal"


# --- 10. Full adjustable supports ---
def test_adjustable_support_strokes_and_3mf(tmp_path):
    strokes = [
        {"kind": "enforce", "x": 10, "y": 10, "z": 0, "r": 3, "h": 10,
         "tip_r": 0.8, "thickness": 2.5, "filament_slot": "pva"},
        {"kind": "block", "x": 20, "y": 20, "z": 0, "r": 4, "h": 8,
         "tip_r": 1.0, "thickness": 3.0, "filament_slot": 2},
    ]
    parsed = sp.parse_strokes(strokes)
    assert parsed[0]["tip_r"] == pytest.approx(0.8)
    assert parsed[0]["thickness"] == pytest.approx(2.5)
    assert parsed[0]["filament_slot"] == "pva"
    assert parsed[1]["filament_slot"] == 2

    parts = sp.meshes_from_strokes(parsed)
    assert len(parts) == 2
    # Shaft+tip should have more faces than a plain cylinder of same height
    assert len(parts[0][1].faces) > 16

    model = _box(40, 40, 10)
    out = tmp_path / "adj.3mf"
    info = sp.write_paint_3mf(model, parsed, out)
    assert info["enforcers"] == 1 and info["blockers"] == 1
    assert info.get("filament_slots")
    with zipfile.ZipFile(out) as z:
        xml = z.read("3D/3dmodel.model").decode()
    assert "SupportEnforcer" in xml and "SupportBlocker" in xml
    assert "zeim:support_filament_slot" in xml
    assert "zeim:support_tip_r" in xml


def test_edit_js_wires_upgrades():
    js = Path("static/edit.js").read_text()
    for needle in ("syncCutJoin", "drainPick", "textPick", "vcRun", "pcColor",
                   "scale_mode", "fontUpload", "textStyleSave", "data-form=\"thread\"",
                   "wireEditUp10", "setProblemHighlights"):
        assert needle in js, needle
    spjs = Path("static/supportpaint.js").read_text()
    assert "tip_r" in spjs and "filament_slot" in spjs and "thickness" in spjs
    vjs = Path("static/viewer.js").read_text()
    assert "setProblemHighlights" in vjs and "clearProblemHighlights" in vjs
