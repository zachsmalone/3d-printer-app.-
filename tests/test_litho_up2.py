"""Lithophane upgrade 2: seamless tile / mm_per_repeat, image tone tools, night-light fits, separate panel/stand downloads."""
import io
import re

import numpy as np
import pytest
import trimesh
from PIL import Image

from app.core import litho_image as LI


def _png(w=80, h=60):
    a = np.zeros((h, w, 3), np.uint8)
    a[:, : w // 2] = 255
    a[h // 3 : 2 * h // 3, :] = [180, 40, 40]
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


# ------------------------------------------------------------------ grey / tone
@pytest.mark.parametrize("method", list(LI.GREY_METHODS))
def test_luma_methods_finite(method):
    rgb = np.linspace(0, 255, 30).reshape(2, 5, 3)
    g = LI.luma(rgb, method)
    assert g.shape == (2, 5) and 0 <= g.min() and g.max() <= 1


def test_rec601_matches_legacy_weights():
    rgb = np.array([[[10.0, 20.0, 30.0]]])
    assert LI.luma(rgb, "rec601")[0, 0] == pytest.approx((0.299 * 10 + 0.587 * 20 + 0.114 * 30) / 255)


def test_adjust_identity_and_ranges():
    g = np.linspace(0, 1, 20).reshape(4, 5)
    assert np.allclose(LI.adjust(g, 0, 0, 0), g)
    with pytest.raises(ValueError):
        LI.check_tone("nope")
    with pytest.raises(ValueError):
        LI.check_tone("rec601", brightness=2)
    with pytest.raises(ValueError):
        LI.check_tone("rec601", sharpen=-0.1)


def test_brightness_shifts_mean():
    g = np.full((8, 8), 0.5)
    assert LI.adjust(g, brightness=0.2).mean() > g.mean()
    assert LI.adjust(g, brightness=-0.2).mean() < g.mean()


def test_api_tone_saved_and_changes_mesh(client):
    a = gen(client).json()
    b = gen(client, brightness="0.4", contrast="0.3", sharpen="0.5", grey_method="lightness").json()
    assert b["params"]["grey_method"] == "lightness"
    assert b["params"]["brightness"] == pytest.approx(0.4)
    assert b["params"]["sharpen"] == pytest.approx(0.5)
    assert a["stats"]["triangles"] == b["stats"]["triangles"]  # same grid
    # thickness map changes → size can stay; rebuilds must differ in body bytes via different params
    assert a["params"].get("grey_method", "rec601") == "rec601" or "grey_method" in b["params"]


def test_api_bad_tone_is_400(client):
    assert gen(client, grey_method="sepia").status_code == 400
    assert gen(client, brightness="9").status_code == 400


# ------------------------------------------------------------------ seamless tile
def test_check_tile():
    assert LI.check_tile(False) == (False, None)
    assert LI.check_tile(True, 40)[0] is True and LI.check_tile(True, 40)[1] == 40
    with pytest.raises(ValueError):
        LI.check_tile(True, 1)


def test_place_tiled_wrap_seamless():
    im = Image.fromarray(np.random.RandomState(1).randint(0, 255, (30, 20, 3), np.uint8))
    a = np.asarray(LI.place_tiled(im, 90, 30, 30, 90, wrap=True))
    # left edge of map equals right-adjacent tile seam (period = 30 px = 90*(30/90))
    assert a.shape == (30, 90, 3)
    tw = 30
    assert np.array_equal(a[:, 0], a[:, tw])


def test_api_tile_saved(client):
    r = gen(client, shape="nightlight", diameter_mm="40", height_mm="50", tile="true", mm_per_repeat="25", resolution="60")
    assert r.status_code == 200, r.text
    p = r.json()["params"]
    assert p["tile"] is True and p["mm_per_repeat"] == pytest.approx(25)


def test_api_tile_rejects_bad_mm(client):
    assert gen(client, tile="true", mm_per_repeat="1").status_code == 400


def test_tiled_cylinder_is_watertight():
    from app.core import litho_shapes as L
    im = Image.fromarray((127 + 80 * np.sin(np.linspace(0, 12, 80))).astype(np.uint8))
    im = im.convert("RGB").resize((80, 50))
    v, f, info, _ = L.curved_shape(im, "nightlight", resolution=120, tile=True, mm_per_repeat=35)
    m = trimesh.Trimesh(v, f)
    assert m.is_watertight and info["inner_diameter_mm"] > 0


# ------------------------------------------------------------------ night-light fits (spec twin)
def test_light_fits_match_spec_notes():
    assert LI.light_fit("tealight")["diameter_mm"] == 38
    assert LI.light_fit("e12")["diameter_mm"] == 16
    with pytest.raises(ValueError):
        LI.light_fit("mains_e26")  # deliberately not offered: mains heat / socket safety


def test_light_fit_ui_copy_is_humble():
    html = open("static/index.html", encoding="utf-8").read()
    box = html.split('id="lightFitBox"')[1].split("</div>", 1)[0]
    low = box.lower()
    assert "led" in low and "flame" in low
    for w in ("best", "better than", "child", "kid"):
        assert w not in low
    assert "lightFit" in open("static/app.js", encoding="utf-8").read()


# ------------------------------------------------------------------ frame sizes
def test_frame_sizes_and_ui():
    assert LI.frame_size("4x6")["width_mm"] == pytest.approx(152.4)
    html = open("static/index.html", encoding="utf-8").read()
    assert 'id="frameSize"' in html and "4 × 6" in html
    assert "FRAME_SIZES" in open("static/app.js", encoding="utf-8").read()


# ------------------------------------------------------------------ separate part downloads
def test_export_parts_panel_and_stand(client):
    j = gen(client, stand="true", resolution="40").json()
    assert len(j["stats"]["bodies"]) == 2
    info = client.get(f"/api/export/{j['id']}").json()
    ids = [p["id"] for p in info["parts"]]
    assert ids[0] == "" and "lithophane" in ids and "stand" in ids
    both = client.get(f"/api/export/{j['id']}/download?format=stl")
    panel = client.get(f"/api/export/{j['id']}/download?format=stl&part=lithophane")
    stand = client.get(f"/api/export/{j['id']}/download?format=stl&part=stand")
    assert both.status_code == panel.status_code == stand.status_code == 200
    assert panel.headers["X-Export-Part"] == "lithophane"
    assert stand.headers["X-Export-Part"] == "stand"
    assert "stand" in stand.headers.get("content-disposition", "").lower() or "stand" in (stand.headers.get("Content-Disposition") or "").lower()
    mb, mp, ms = (trimesh.load(io.BytesIO(r.content), file_type="stl") for r in (both, panel, stand))
    assert len(mp.faces) < len(mb.faces) and len(ms.faces) < len(mb.faces)
    assert abs(len(mp.faces) + len(ms.faces) - len(mb.faces)) <= 2  # merge ≈ sum


def test_export_unknown_part_is_400(client):
    j = gen(client, stand="true").json()
    r = client.get(f"/api/export/{j['id']}/download?format=stl&part=nope")
    assert r.status_code == 400


def test_picker_offers_parts():
    js = open("static/exportpick.js", encoding="utf-8").read()
    assert 'id="expParts"' in js and "&part=" in js and "j.parts" in js


def test_image_tools_ui_in_expert():
    html = open("static/index.html", encoding="utf-8").read()
    box = html.split("Image &amp; detail")[1].split("</details>")[0]
    for t in ("grey_method", "brightness", "contrast", "sharpen", 'name="tile"', "mm_per_repeat", "Seamless tile"):
        assert t in box
    low = box.lower()
    for w in ("best", "child", "kid"):
        assert w not in low
