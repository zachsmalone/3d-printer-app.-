"""Lithophane upgrade 1: backing colour (saved with the build, tints the Light on preview), Bambu lithophane print
preset inside the 3MF (optional, honest 'not tested' note), and the workspace layout coming back after a build."""
import io
import json
import re
import xml.dom.minidom
import zipfile

import numpy as np
import pytest
import trimesh
from PIL import Image

from app.core import litho_backing
from app.services import litho_preset


def _png():
    a = np.zeros((60, 80, 3), np.uint8); a[:, :40] = 255
    buf = io.BytesIO(); Image.fromarray(a).save(buf, "PNG"); return buf.getvalue()


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def gen(client, **extra):
    data = {"mode": "lithophane", "beginner": "false", "shape": "rect", "width_mm": "60", "resolution": "40",
            "photo_ack": "true", "auto_delete_oldest": "true", **extra}
    return client.post("/api/generate", files={"file": ("p.png", _png(), "image/png")}, data=data)


# ------------------------------------------------------------------ backing colour
@pytest.mark.parametrize("v,want", [("", ""), ("none", ""), ("warm", "warm"), ("cool", "cool"), ("paper", "paper"),
                                    ("#FFAA00", "#ffaa00"), (" #123abc ", "#123abc")])
def test_backing_normalize(v, want):
    assert litho_backing.normalize(v) == want


@pytest.mark.parametrize("bad", ["red", "#12345", "#12345g", "fff", "javascript:x", "#1234567"])
def test_backing_rejects_junk(bad):
    with pytest.raises(ValueError):
        litho_backing.normalize(bad)


def test_backing_rgb():
    assert litho_backing.rgb("") == (1.0, 1.0, 1.0)
    assert litho_backing.rgb("#ff0000") == (1.0, 0.0, 0.0)
    r, g, b = litho_backing.rgb("warm"); assert r >= g >= b          # warm = more red than blue


def test_backing_js_twin_matches_python():
    js = open("static/lithlight.js", encoding="utf-8").read()
    m = re.search(r"export const BACKINGS = \{([^}]*)\}", js)
    pairs = dict(re.findall(r'(\w+): "(#[0-9a-f]{6})"', m.group(1)))
    assert pairs == {k: v[1] for k, v in litho_backing.BACKINGS.items()}


def test_api_backing_saved_with_build(client):
    r = gen(client, backing="paper")
    assert r.status_code == 200, r.text
    assert r.json()["params"]["backing"] == "paper"
    r = gen(client, backing="#A0B0C0")
    assert r.status_code == 200 and r.json()["params"]["backing"] == "#a0b0c0"
    r = gen(client)
    assert r.status_code == 200 and "backing" not in r.json()["params"]


def test_api_bad_backing_is_400(client):
    assert gen(client, backing="#zzzzzz").status_code == 400


def test_backing_does_not_change_the_mesh(client):
    a, b = gen(client).json(), gen(client, backing="cool").json()
    assert a["stats"]["triangles"] == b["stats"]["triangles"] and a["stats"]["size_mm"] == b["stats"]["size_mm"]


def test_backing_ui_in_lithophane_panel():
    html = open("static/index.html", encoding="utf-8").read()
    box = html.split('id="backingBox"')[1].split("</div>\n      <details")[0]
    for t in ("Warm white", "Cool white", "Paper", "Custom colour", 'type="color"', 'id="backingHex"'):
        assert t in box
    low = box.lower()
    for w in ("child", "kid", "family", "better than", "best"):
        assert w not in low
    assert all(ord(c) < 0x2190 for c in box)                         # no emoji / pictographs
    js = open("static/app.js", encoding="utf-8").read()
    assert 'fd.append("backing"' in js and "setBacking(r.params.backing" in js and "withBacking(" in js


# ------------------------------------------------------------------ Bambu print preset
def _members(data):
    z = zipfile.ZipFile(io.BytesIO(data)); return z, z.namelist()


def test_preset_settings_and_brim_only_when_standing():
    flat, up = litho_preset.settings_for("rect"), litho_preset.settings_for("curve")
    assert flat["sparse_infill_density"][0] == "100%" and flat["layer_height"][0] == "0.12"
    assert "brim_type" not in flat and up["brim_type"][0] == "outer_only"


def test_export_with_preset(client):
    j = gen(client, shape="curve", bend_deg="90", width_mm="60").json()
    info = client.get(f"/api/export/{j['id']}").json()
    pr = info["print_presets"]
    assert pr and pr[0]["id"] == "bambu_litho" and "Not tested on a real Bambu" in pr[0]["note"] and "brim" in pr[0]["desc"]
    r = client.get(f"/api/export/{j['id']}/download?format=3mf&preset=bambu_litho&printer_id=bambu_x1c")
    assert r.status_code == 200 and r.headers["X-Export-Preset"] == "bambu_litho"
    z, names = _members(r.content)
    assert "Metadata/zeim_print_preset.json" in names
    cfg = z.read("Metadata/model_settings.config").decode()
    xml.dom.minidom.parseString(cfg)                                 # still valid XML
    for k in ('key="layer_height" value="0.12"', 'key="sparse_infill_density" value="100%"', 'key="brim_type"', 'key="extruder"'):
        assert k in cfg
    meta = json.loads(z.read("Metadata/zeim_print_preset.json"))
    assert meta["tested_on_hardware"] is False and meta["printer_id"] == "bambu_x1c"
    assert 'Extension="config"' in z.read("[Content_Types].xml").decode()
    m = trimesh.load(io.BytesIO(r.content), file_type="3mf", force="mesh")
    assert len(m.faces) > 0


def test_export_without_preset_is_unchanged(client):
    j = gen(client).json()
    r = client.get(f"/api/export/{j['id']}/download?format=3mf")
    z, names = _members(r.content)
    assert r.headers["X-Export-Preset"] == "" and "Metadata/zeim_print_preset.json" not in names
    assert "layer_height" not in z.read("Metadata/model_settings.config").decode()


def test_preset_on_stl_is_ignored_not_blocked(client):
    j = gen(client).json()
    r = client.get(f"/api/export/{j['id']}/download?format=stl&preset=bambu_litho")
    assert r.status_code == 200 and r.headers["X-Export-Preset"] == ""


def test_unknown_preset_refused(client):
    j = gen(client).json()
    assert client.get(f"/api/export/{j['id']}/download?format=3mf&preset=other").status_code == 422


def test_flat_preset_has_no_brim(client):
    j = gen(client).json()
    r = client.get(f"/api/export/{j['id']}/download?format=3mf&preset=bambu_litho")
    z, _ = _members(r.content)
    assert "brim_type" not in z.read("Metadata/model_settings.config").decode()


def test_no_preset_offered_for_relief(client):
    r = gen(client, mode="relief")
    assert r.status_code == 200, r.text
    assert client.get(f"/api/export/{r.json()['id']}").json()["print_presets"] == []


def test_picker_has_preset_option_with_note():
    js = open("static/exportpick.js", encoding="utf-8").read()
    assert 'id="expPresetOn"' in js and "&preset=" in js and "print_presets" in js


# ------------------------------------------------------------------ workspace layout
def test_layout_watches_obstacles_so_panels_come_back():
    js = open("static/wslayout.js", encoding="utf-8").read()
    assert "function watchObstacles()" in js and "watchObstacles();" in js
    assert "undo the trial edges' classes" in js


def test_core_panel_is_not_minimised_to_make_room():
    """Layout may move a panel. It does not minimise or hide one, including a core panel, to make room."""
    js = open("static/wslayout.js", encoding="utf-8").read()
    assert "chipPri" in js and "layout does not minimise or hide another panel" in js
    assert "a core panel never steps aside" in js
    assert 'classList.add("min", "auto-min")' not in js
    assert 'classList.add("auto-off")' not in js
    assert 'dataset.crowded = "1"' not in js


# ------------------------------------------------------------------ (d) sleeve / cup lip with a sloped edge
def _smooth():
    y, x = np.mgrid[0:80, 0:160]
    return Image.fromarray((127 + 120 * np.sin(x / 9) * np.cos(y / 7)).astype(np.uint8)).convert("RGB")


def _worst_overhang(v, f):
    m = trimesh.Trimesh(v, f)
    n, zc = m.face_normals, m.triangles_center[:, 2]
    keep = zc > 0.3                                   # bed faces are fine
    return m, float(np.degrees(np.arcsin(np.clip(-n[keep, 2], 0, 1))).max())


@pytest.mark.parametrize("shape", ["nightlight", "cup"])
@pytest.mark.parametrize("taper,deg", [("outward", 45), ("inward", 45), ("both", 45), ("outward", 30)])
def test_sloped_lip_is_self_supporting(shape, taper, deg):
    from app.core import litho_shapes as L
    v, f, info, _ = L.curved_shape(_smooth(), shape, resolution=200, lip_mm=2, lip_taper=taper, taper_deg=deg)
    m, worst = _worst_overhang(v, f)
    assert m.is_watertight and worst <= 45.5 and info["lip_taper"] == taper and info["lip_mm"] == 2


def test_flat_ledge_still_available_and_lip0_has_no_band():
    from app.core import litho_shapes as L
    v, f, info, _ = L.curved_shape(_smooth(), "nightlight", resolution=200, lip_mm=2, lip_taper="none")
    assert _worst_overhang(v, f)[1] > 60                       # the old 90-ish degree ledge, kept as a choice
    v0, f0, i0, _ = L.curved_shape(_smooth(), "nightlight", resolution=200, lip_mm=0)
    assert i0["band_mm"] == 0 and _worst_overhang(v0, f0)[1] < 45
    r = lambda v: np.hypot(v[:, 0], v[:, 1]).max()
    assert r(v) > r(v0) + 1.5                                  # the lip reaches out past the wall


def test_inward_lip_reports_narrower_opening():
    from app.core import litho_shapes as L
    *_, info, _ = L.curved_shape(_smooth(), "nightlight", diameter_mm=40, resolution=120, lip_mm=2, lip_taper="inward")
    assert info["lip_inner_diameter_mm"] < info["inner_diameter_mm"]


def test_legacy_builds_unchanged_without_lip_params():
    from app.core import litho_shapes as L
    *_, info, _ = L.curved_shape(_smooth(), "cup", resolution=80)
    assert info["lip_taper"] == "none" and "taper_deg" not in info


@pytest.mark.parametrize("bad", [dict(lip_mm="11"), dict(lip_mm="2", lip_taper="sideways"), dict(lip_mm="2", taper_deg="60")])
def test_api_lip_validation(client, bad):
    assert gen(client, shape="nightlight", diameter_mm="40", height_mm="40", **bad).status_code == 400


def test_api_lip_saved(client):
    r = gen(client, shape="cup", diameter_mm="40", height_mm="40", lip_mm="3", lip_taper="both", taper_deg="40")
    assert r.status_code == 200, r.text
    p = r.json()["params"]
    assert (p["lip_mm"], p["lip_taper"], p["taper_deg"]) == (3.0, "both", 40.0)
    assert r.json()["stats"]["watertight"]


def test_lip_ui_copy():
    html = open("static/index.html", encoding="utf-8").read()
    box = html.split('id="lipBox"')[1].split("</div>\n      </div>")[0]
    for t in ('id="lip_mm"', 'id="lip_taper"', 'id="taper_deg"', 'max="45"', "Sloped outward", "0 means no band"):
        assert t in box
    assert all(ord(c) < 0x2190 for c in box.replace("°", ""))
    js = open("static/app.js", encoding="utf-8").read()
    assert 'fd.append("lip_taper"' in js and "You can still build it." in js
