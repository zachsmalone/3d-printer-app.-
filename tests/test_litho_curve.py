"""Curved panel lithophane: bend 0..180 deg, arc length + aspect kept, thickness along the normal, watertight,
built-in stand in the same solid, bed-fit against the chosen printer."""
import numpy as np
import pytest
import trimesh
from PIL import Image

from app.core import exporters, geometry, litho_shapes
from app.services import willprint

TMIN, TMAX = 0.8, 3.0


def half_image(w=200, h=100):
    a = np.zeros((h, w, 3), np.uint8)
    a[:, : w // 2] = 255                     # left half white (thin), right half black (thick)
    return Image.fromarray(a)


def make(bend, stand=False, width=100, im=None):
    p = dict(shape="curve", width_mm=width, bend_deg=bend, stand=stand, min_thickness=TMIN, max_thickness=TMAX,
             border_mm=2, resolution=100, auto_contrast=False, smooth=0)
    return geometry.build(im or half_image(), "lithophane", p)


def tm(m):
    v, f = m.solid()
    return trimesh.Trimesh(v, f, process=False)


@pytest.mark.parametrize("bend", [0, 30, 90, 135, 180])
@pytest.mark.parametrize("stand", [False, True])
def test_watertight_on_bed_one_body(bend, stand):
    m = make(bend, stand)
    t = tm(m)
    assert t.is_watertight and t.is_winding_consistent and t.volume > 0
    assert len(m.bodies) == 1 and m.info["shape"] == "curve" and m.info["bend_deg"] == bend
    assert t.bounds[0][2] == pytest.approx(0, abs=1e-9)
    assert willprint.bed_fit(tuple(t.extents), "creality_k1")["ok"]
    assert ("stand" in m.info) == stand


def test_aspect_kept_height_follows_photo():
    for bend in (0, 180):
        m = make(bend)
        assert m.info["panel_height_mm"] == pytest.approx(50.0)          # 200x100 photo, 100 mm along the arc
        assert tm(m).extents[2] == pytest.approx(50.0, abs=1e-6)


def test_footprint_matches_arc_geometry():
    flat, half = tm(make(0)).extents, tm(make(180)).extents
    assert flat[0] == pytest.approx(100, abs=0.01) and flat[1] == pytest.approx(TMAX, abs=0.01)
    r = 100 / np.pi                                                       # arc length kept: 100 mm = pi * r
    assert make(180).info["radius_mm"] == pytest.approx(r, abs=0.01)
    assert half[0] == pytest.approx(2 * (r + TMAX), abs=0.05)
    assert half[1] == pytest.approx(r + TMAX, abs=0.05)


@pytest.mark.parametrize("bend", [0, 90, 180])
def test_thickness_along_normal_bright_thin(bend):
    s = np.linspace(-50, 50, 2001)
    xy, n = litho_shapes.arc_frame(s, 100, bend)
    assert np.allclose(np.linalg.norm(n, axis=1), 1)
    seg = np.linalg.norm(np.diff(xy, axis=0), axis=1).sum()
    assert seg == pytest.approx(100, rel=1e-4)                             # inner surface keeps the arc length
    v, f, info, thick = litho_shapes.curved_panel(half_image(), 100, bend, min_thickness=TMIN, max_thickness=TMAX,
                                                  border_mm=2, resolution=100, auto_contrast=False, smooth=0)
    R, C = thick.shape
    k = len(v) // 2
    outer, inner = v[:k].reshape(R, C, 3), v[k:].reshape(R, C, 3)
    t = np.linalg.norm(outer - inner, axis=-1)                              # measured along the normal
    assert np.allclose(t, thick[::-1], atol=1e-6)
    mid = R // 2
    assert t[mid, C // 4] == pytest.approx(TMIN, abs=0.05)                  # white -> thin (image left = -X)
    assert t[mid, 3 * C // 4] == pytest.approx(TMAX, abs=0.05)
    assert inner[mid, C // 4, 0] < 0 < inner[mid, 3 * C // 4, 0]


def test_stand_widens_footprint_and_stays_one_piece():
    a, b = tm(make(90)), tm(make(90, stand=True))
    assert b.extents[1] > a.extents[1] and b.extents[2] > a.extents[2]
    assert b.body_count == 1


def test_bend_out_of_range_refused():
    with pytest.raises(ValueError):
        make(181)
    with pytest.raises(ValueError):
        make(-1)


def test_hang_holes_refused_for_curve():
    with pytest.raises(ValueError):
        geometry.build(half_image(), "lithophane", dict(shape="curve", width_mm=80, bend_deg=90, hang="top",
                                                       min_thickness=TMIN, max_thickness=TMAX, resolution=80))


def test_exports_all_formats():
    m = make(120, stand=True)
    for ext, fn in exporters.WRITERS.items():
        assert len(fn(m)) > 100, ext


def test_big_panel_bed_fit_warns_for_small_printer():
    t = tm(make(0, width=300))
    assert not willprint.bed_fit(tuple(t.extents), "creality_k1")["ok"]   # a warning value, the build still exists


def test_ui_has_curve_controls_line_icon_no_emoji():
    html = open("static/index.html", encoding="utf-8").read()
    card = html.split('data-shape="curve"')[1].split("</label>")[0]
    assert '<use href="#i-curve"/>' in card and "Curved panel" in card
    assert all(ord(ch) < 0x2190 for ch in card)
    assert 'id="bend_deg"' in html and 'min="0" max="180"' in html and 'id="curveStand"' in html
    block = html.split('id="curveOpts"')[1].split('id="hangOpts"')[0].lower()
    for w in ("child", "kid", "family", "better than", "best"):
        assert w not in block
    js = open("static/app.js", encoding="utf-8").read()
    assert 'fd.append("bend_deg"' in js and "You can still export it." in js


# ------------------------------------------------------------------ API chain
def _png():
    import io
    buf = io.BytesIO(); half_image().save(buf, "PNG"); return buf.getvalue()


def _post(**extra):
    from fastapi.testclient import TestClient
    from app.main import app
    data = {"mode": "lithophane", "beginner": "false", "shape": "curve", "width_mm": "100", "resolution": "40",
            "photo_ack": "true", "auto_delete_oldest": "true", **extra}
    return TestClient(app).post("/api/generate", files={"file": ("p.png", _png(), "image/png")}, data=data)


def test_api_curve_stand_export_and_rebuild():
    import io
    r = _post(bend_deg="150", stand="true", printer_id="creality_k1")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["params"]["bend_deg"] == 150 and j["params"]["stand"] is True
    assert j["info"]["shape"] == "curve" and j["info"]["bed_fit"]["ok"] and j["stats"]["watertight"]
    assert len(j["stats"]["bodies"]) == 1
    from fastapi.testclient import TestClient
    from app.main import app
    stl = TestClient(app).get(j["downloads"]["stl"])
    if stl.status_code == 200:
        assert trimesh.load(io.BytesIO(stl.content), file_type="stl").is_watertight
    m = geometry.build(half_image(), "lithophane", {**j["params"], "resolution": 40})   # history reload path
    assert m.info["bend_deg"] == 150 and "stand" in m.info


def test_api_bed_fit_is_a_warning_not_a_block():
    r = _post(width_mm="400", bend_deg="0")
    assert r.status_code == 200, r.text
    assert r.json()["info"]["bed_fit"]["ok"] is False


def test_api_bad_bend_and_unknown_printer():
    assert _post(bend_deg="200").status_code == 400
    r = _post(bend_deg="90", printer_id="no_such_printer")
    assert r.status_code == 200 and r.json()["info"]["bed_fit"]["ok"]       # falls back to the default printer
