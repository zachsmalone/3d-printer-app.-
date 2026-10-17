"""Display stand for flat lithophanes (app/core/litho_stand.py, geometry wiring).

Checks the channel geometry (watertight, dimensions, groove fit, printable walls) plus
the request -> build -> export -> reload chain through the API, including the two-body
export (lithophane + stand in one download).
"""
import io

import numpy as np
import pytest
import trimesh
from PIL import Image

from app.core import geometry, litho_stand


def img():
    a = np.zeros((120, 160, 3), np.uint8)
    a[:, :60] = 255
    a[30:70, 100:140] = 128
    return Image.fromarray(a)


def build(**extra):
    p = dict(shape="rect", width_mm=100, min_thickness=0.8, max_thickness=3.0,
             border_mm=3, resolution=40, auto_contrast=False, smooth=0)
    p.update(extra)
    return geometry.build(img(), "lithophane", p)


def stand_mesh(**kw):
    v, f, info = litho_stand.stand(**{**dict(panel_width_mm=100, panel_thickness_mm=3.0), **kw})
    return trimesh.Trimesh(v, f), info


# ------------------------------------------------------------------ geometry
def test_stand_is_a_watertight_box_with_groove():
    t, info = stand_mesh()
    assert t.is_watertight
    assert t.euler_number == 2                                   # solid, no through holes
    assert t.volume > 0
    lo, hi = t.bounds
    assert hi[0] - lo[0] == pytest.approx(info["length_mm"], abs=1e-6)
    assert hi[2] - lo[2] == pytest.approx(info["height_mm"], abs=1e-6)
    assert lo[2] == pytest.approx(0.0, abs=1e-9)                  # sits flat on the plate


def test_groove_fits_the_panel():
    for th in (0.8, 1.5, 3.0, 6.0):
        t, info = stand_mesh(panel_thickness_mm=th)
        assert litho_stand.fits(info["groove_width_mm"], th)
        # groove measured from the mesh: top-face vertices stop at the groove edge
        top = t.vertices[t.vertices[:, 2] > info["height_mm"] - 1e-6]
        half_g = np.abs(top[:, 1]).min()
        assert 2 * half_g == pytest.approx(info["groove_width_mm"], abs=0.05)


def test_groove_clearance():
    # slip fit: the panel's thickest section drops in, with clearance to spare
    t, info = stand_mesh(panel_thickness_mm=3.0)
    assert info["groove_width_mm"] >= 3.0 + litho_stand.GROOVE_CLEARANCE_MM - 1e-9


def test_groove_measured_from_mesh():
    # the groove floor is exactly groove_depth below the top, present in the mesh
    t, info = stand_mesh()
    floor = info["height_mm"] - info["groove_depth_mm"]
    assert any(abs(z - floor) < 1e-6 for z in np.unique(np.round(t.vertices[:, 2], 6)))
    # volume = box - groove (cutter runs past both ends, so the notch is exactly L*g*gd)
    exp = (info["length_mm"] * info["depth_mm"] * info["height_mm"]
           - info["length_mm"] * info["groove_width_mm"] * info["groove_depth_mm"])
    assert t.volume == pytest.approx(exp, rel=1e-6)


def test_printable_walls_measured_from_mesh():
    t, info = stand_mesh(panel_thickness_mm=3.0)
    floor = info["height_mm"] - info["groove_depth_mm"]
    assert floor >= litho_stand.MIN_WALL_MM                     # base under the groove
    assert info["groove_depth_mm"] >= 4.0                       # panel sits deep enough to stand
    # side walls: the top face spans |y| up to depth/2 with the groove edge at g/2
    top = t.vertices[t.vertices[:, 2] > info["height_mm"] - 1e-6]
    half_d = np.abs(top[:, 1]).max()
    assert half_d == pytest.approx(info["depth_mm"] / 2, abs=0.05)
    assert half_d - info["groove_width_mm"] / 2 >= litho_stand.MIN_WALL_MM - 0.05


def test_length_covers_the_panel():
    t, info = stand_mesh(panel_width_mm=100)
    assert info["length_mm"] == 100 + 2 * litho_stand.MARGIN_MM


@pytest.mark.parametrize("kw, msg", [
    (dict(panel_width_mm=10, panel_thickness_mm=3.0), "wide"),
    (dict(panel_width_mm=500, panel_thickness_mm=3.0), "wide"),
    (dict(panel_width_mm=100, panel_thickness_mm=0.2), "thick"),
    (dict(panel_width_mm=100, panel_thickness_mm=15), "thick"),
])
def test_validation(kw, msg):
    with pytest.raises(ValueError, match=msg):
        litho_stand.stand(**kw)


# ------------------------------------------------------------------ model wiring
def test_stand_never_overlaps_the_panel():
    # both parts print in one combined export: they must sit apart on the bed
    m = build(stand=True)
    tp = trimesh.Trimesh(m.bodies[0].vertices, m.bodies[0].faces)
    ts = trimesh.Trimesh(m.bodies[1].vertices, m.bodies[1].faces)
    assert ts.bounds[0][1] >= tp.bounds[1][1] + 4.0                 # clear gap in Y
    assert ts.bounds[0][0] >= tp.bounds[0][0] - 1e-6 \
        and ts.bounds[1][0] <= tp.bounds[1][0] + 1e-6 + 2 * litho_stand.MARGIN_MM + 1e-6


def test_stand_is_a_second_body():
    m = build(stand=True)
    assert len(m.bodies) == 2
    names = [b.name for b in m.bodies]
    assert names == ["lithophane", "stand"]
    t = trimesh.Trimesh(m.bodies[1].vertices, m.bodies[1].faces)
    assert t.is_watertight
    assert m.info["stand"]["panel_thickness_mm"] == 3.0
    lo, hi = t.bounds
    assert hi[0] - lo[0] == pytest.approx(100 + 2 * litho_stand.MARGIN_MM, abs=1e-6)


def test_stand_groove_matches_max_thickness():
    m = build(stand=True, max_thickness=4.0)
    assert litho_stand.fits(m.info["stand"]["groove_width_mm"], 4.0)


def test_shape_shapes_get_a_stand():
    m = build(shape="circle", stand=True)
    assert len(m.bodies) == 2 and m.info["stand"]["panel_width_mm"] == 100


def test_default_build_has_one_body():
    m = build()
    assert len(m.bodies) == 1 and "stand" not in m.info


# ------------------------------------------------------------------ API chain
def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def _png():
    buf = io.BytesIO(); img().save(buf, "PNG"); return buf.getvalue()


def test_api_stand_build_export_reload():
    c = _client()
    r = c.post("/api/generate", files={"file": ("p.png", _png(), "image/png")}, data={
        "mode": "lithophane", "shape": "rect", "width_mm": "100", "resolution": "40",
        "photo_ack": "true", "stand": "true"})
    assert r.status_code == 200, r.text
    j = r.json()
    bodies = j["stats"]["bodies"]
    assert len(bodies) == 2 and all(b["watertight"] for b in bodies)
    assert j["stats"]["watertight"]
    for ext, loader in (("stl", "stl"), ("obj", "obj"), ("3mf", "3mf")):
        data = c.get(j["downloads"][ext])
        assert data.status_code == 200
        loaded = trimesh.load(io.BytesIO(data.content), file_type=loader)
        geoms = list(loaded.geometry.values()) if isinstance(loaded, trimesh.Scene) else loaded.split(only_watertight=False)
        assert len(geoms) == 2                                 # both parts in one download
        assert all(g.is_watertight for g in geoms)
    # saved params rebuild both bodies (history reload path)
    m = geometry.build(img(), "lithophane", {**j["params"], "resolution": 40})
    assert len(m.bodies) == 2


def test_api_rejects_stand_on_curved():
    c = _client()
    r = c.post("/api/generate", files={"file": ("p.png", _png(), "image/png")}, data={
        "mode": "lithophane", "shape": "nightlight", "width_mm": "100", "resolution": "40",
        "diameter_mm": "40", "height_mm": "60", "photo_ack": "true", "stand": "true"})
    assert r.status_code == 400 and "flat" in r.json()["detail"]


def test_api_default_still_works():
    c = _client()
    r = c.post("/api/generate", files={"file": ("p.png", _png(), "image/png")}, data={
        "mode": "lithophane", "shape": "rect", "width_mm": "100", "resolution": "40", "photo_ack": "true"})
    assert r.status_code == 200 and len(r.json()["stats"]["bodies"]) == 1
