"""Hanging holes for flat lithophanes (app/core/litho_hang.py, geometry wiring).

Checks the geometry itself (watertight, handle count, hole size and walls) plus the
request -> validation -> build -> export -> reload chain through the API.
"""
import io

import numpy as np
import pytest
import trimesh
from PIL import Image

from app.core import geometry, litho_hang, litho_shapes


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


def mesh(m, i=0):
    return trimesh.Trimesh(m.bodies[i].vertices, m.bodies[i].faces)


# ------------------------------------------------------------------ option validation
@pytest.mark.parametrize("bad, msg", [
    (dict(hang="middle"), "hang must be"),
    (dict(hang="top", hole_d=1.0), "hole_d"),
    (dict(hang="top", hole_d=9.0), "hole_d"),
    (dict(hang="top", inset_mm=2.0), "inset_mm"),
    (dict(hang="top", inset_mm=16.0), "inset_mm"),
    (dict(hang="two", spacing_mm=10.0), "spacing_mm"),
    (dict(hang="two", spacing_mm=130.0), "spacing_mm"),
])
def test_check_hang_rejects(bad, msg):
    with pytest.raises(ValueError, match=msg):
        litho_hang.check_hang(**bad)


def test_check_hang_accepts():
    o = litho_hang.check_hang("two", 4.0, 6.0, 40.0)
    assert o == dict(hang="two", hole_d=4.0, inset_mm=6.0, spacing_mm=40.0)


def test_border_needed_keeps_hole_in_rim():
    # rim must reach past the far side of the hole plus a printable wall: inset + radius + WALL
    assert litho_hang.border_needed(4.0, 6.0) == 6.0 + 2.0 + litho_hang.WALL_MM


# ------------------------------------------------------------------ placement maths
def test_positions_top_and_two():
    pts = litho_hang.positions("top", 100, 80, 4.0, 6.0, 40.0)
    assert pts == [(50.0, 74.0)]
    pts = litho_hang.positions("two", 100, 80, 4.0, 6.0, 40.0)
    assert pts == [(30.0, 74.0), (70.0, 74.0)]


def test_positions_wall_enforced():
    # hole edge closer than WALL_MM to a side edge is refused, not silently produced
    with pytest.raises(ValueError, match="side edge"):
        litho_hang.positions("two", 40, 80, 4.0, 6.0, 40.0)     # 40 mm spacing on a 40 mm plate
    with pytest.raises(ValueError, match="top or bottom"):
        litho_hang.positions("top", 100, 8, 4.0, 6.0, 40.0)      # plate shorter than the inset


def test_min_wall_from_geometry():
    m = build(hang="top")
    cx, cy = litho_hang.positions("top", 100, mesh(m).bounds[1][1], 4.0, 6.0, 40.0)[0]
    t = mesh(m)
    top = t.bounds[1][1]
    assert top - (cy + 2.0) >= litho_hang.WALL_MM              # wall above the hole
    assert m.info["hang"] == "top" and m.info["hole_d"] == 4.0


def test_points_in_poly():
    poly = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)
    pts = np.array([[5, 5], [15, 5], [5, -1], [9.9, 5], [0, 0]])
    assert list(litho_hang.points_in_poly(pts, poly)) == [True, False, False, True, True]


def test_fit_check_rejects_hole_outside_shape():
    # a hole centred 2 mm from the edge of a 20 mm circle: the wall ring leaves the plate
    poly = litho_shapes.outline("circle", 256) * 10.0 + 10.0
    with pytest.raises(ValueError, match="does not fit"):
        litho_hang.fit_check([(10.0, 18.0)], 4.0, poly)


# ------------------------------------------------------------------ mesh geometry
def test_punch_makes_a_watertight_handle():
    # rect path: watertight, handle count, width unchanged (the rim loop changes plate height,
    # so bounds are compared per axis)
    for hang, holes in (("top", 1), ("two", 2)):
        t = mesh(build(hang=hang))
        assert t.is_watertight
        assert t.euler_number == 2 - 2 * holes                     # +1 handle per hole
    # circle path: rim is geometrically exact there, so volumes compare cleanly
    # (border 12 covers the 9.6 mm the hole + wall needs, so both builds get the same rim)
    before = mesh(build(shape="circle", border_mm=12))
    after = mesh(build(shape="circle", border_mm=12, hang="top"))
    assert after.is_watertight and after.volume < before.volume
    assert np.allclose(after.bounds, before.bounds, atol=1e-6)


def test_hole_volume_matches_cylinder():
    # circle rim is max thickness (3 mm): the removed plug is ~ pi r^2 * 3
    before = mesh(build(shape="circle", border_mm=12))
    after = mesh(build(shape="circle", border_mm=12, hang="top", hole_d=4.0))
    assert before.volume - after.volume == pytest.approx(np.pi * 4 * 3.0, rel=0.05)


def test_hole_diameter_from_cross_section():
    t = mesh(build(hang="top", hole_d=6.0))
    sec = t.section(plane_origin=[0, 0, 1.5], plane_normal=[0, 0, 1])
    p2, _ = sec.to_planar()
    want = np.pi * 3.0 ** 2
    small = [p for p in p2.polygons_closed if p.area == pytest.approx(want, rel=0.1)]
    assert len(small) == 1                                          # the hole, not the outline/lakes
    assert small[0].bounds[2] - small[0].bounds[0] == pytest.approx(6.0, abs=0.2)


def test_circle_shape_gets_a_hole():
    t = mesh(build(shape="circle", hang="top"))
    assert t.is_watertight and t.euler_number == 0


def test_square_shape_gets_a_hole():
    t = mesh(build(shape="square", hang="top"))
    assert t.is_watertight and t.euler_number == 0


def test_star_rejected_pointed_top():
    # a 5-point star's top is a point: no material for a centred hole -> clear error
    with pytest.raises(ValueError, match="does not fit"):
        build(shape="star", hang="top")


@pytest.mark.parametrize("shape", ["globe", "nightlight", "cup"])
@pytest.mark.parametrize("extra", [dict(hang="top"), dict(stand=True)])
def test_curved_shapes_refused(shape, extra):
    with pytest.raises(ValueError, match="flat"):
        build(shape=shape, diameter_mm=40, height_mm=60, **extra)


def test_heart_rejected_with_guidance():
    # the heart's top notch leaves no material for a centred hole: a clear error, not a broken mesh
    with pytest.raises(ValueError, match="does not fit"):
        build(shape="heart", hang="top")


def test_border_widened_to_fit_hole():
    # default border 3 mm is too thin for a 6 mm hole at 6 mm inset: the rim grows to 8 mm.
    # The outside width stays 100 mm; the extra rim eats into the picture area instead.
    a, b = build(), build(hang="top")
    ta, tb = mesh(a), mesh(b)
    assert ta.bounds[1][0] == pytest.approx(tb.bounds[1][0], abs=1e-6)      # width unchanged
    assert b.info["border_cells"] > a.info["border_cells"]                   # rim grew
    actual = (b.info["border_cells"] - 1) * b.info["pitch_mm"]   # last padded row is a transition cell
    assert actual >= b.info["inset_mm"] + b.info["hole_d"] / 2 + litho_hang.WALL_MM
    # the rect rim loop guarantees the REAL full-thickness band reaches the requested width
    wide = build(border_mm=12, hang="top")
    assert (wide.info["border_cells"] - 1) * wide.info["pitch_mm"] >= 12


def test_default_build_unchanged():
    # no hang options: byte-identical geometry to the pre-hang code path
    a, b = build(), build(hang="", stand=False)
    assert np.array_equal(a.solid()[0], b.solid()[0]) and len(b.bodies) == 1


def test_default_matches_pre_hang_pipeline():
    # replicate the old rect pipeline inline (pre-attachment code) and compare exactly
    from app.core import geometry as G
    small = G._resize(img(), 40)
    g = G._tone(G._luma(np.asarray(small, np.float64)), False, 1.0, 0)
    thick = 3.0 - (3.0 - 0.8) * g
    ny, nx = thick.shape
    pad = max(1, int(round(3.0 / (100.0 / (nx - 1)))))
    thick = np.pad(thick, pad, constant_values=3.0)
    pitch = 100.0 / (nx - 1 + 2 * pad)
    v, f = G.heightfield_solid(thick, pitch)
    m = build()
    assert np.array_equal(m.solid()[0], v) and np.array_equal(m.solid()[1], f)


def test_rim_solid_around_hole_on_white_image():
    # worst case: a blank white photo is the thinnest lithophane; the material in a
    # printable wall around the hole must still be full max thickness so it hangs safely.
    # Sampled by ray casting (the thickness ramp dips BETWEEN grid vertices, so a
    # vertex-only check would miss it).
    m = geometry.build(Image.new("RGB", (160, 120), (255, 255, 255)), "lithophane",
                       dict(shape="rect", width_mm=100, resolution=40, hang="top",
                            auto_contrast=False, smooth=0))
    t = trimesh.Trimesh(m.bodies[0].vertices, m.bodies[0].faces)
    ymax = t.bounds[1][1]
    cx, cy = 50.0, ymax - 6.0
    ang = np.linspace(0, 2 * np.pi, 24)[:-1]
    pts = np.stack([cx + (2.0 + 0.5) * np.cos(ang), cy + (2.0 + 0.5) * np.sin(ang)], -1)
    origins = np.column_stack([pts, np.full(len(pts), 10.0)])
    locs, idx_ray, _ = t.ray.intersects_location(origins, np.tile([0, 0, -1], (len(pts), 1)))
    top = np.full(len(pts), -np.inf)
    for loc, ir in zip(locs, idx_ray):                             # a ray can hit several triangles
        top[ir] = max(top[ir], loc[2])
    assert np.all(top > -np.inf)                                  # every sample hit the plate
    assert top.min() >= 3.0 - 0.05                               # full thickness all around the hole


def test_actual_rim_covers_hole():
    # the real full-thickness band ((cells - 1) * pitch; the last padded row transitions)
    # must cover the hole plus its printable wall
    m = build(hang="top")
    actual = (m.info["border_cells"] - 1) * m.info["pitch_mm"]
    assert actual >= m.info["inset_mm"] + m.info["hole_d"] / 2 + litho_hang.WALL_MM


# ------------------------------------------------------------------ API chain
def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def _png():
    buf = io.BytesIO(); img().save(buf, "PNG"); return buf.getvalue()


def test_api_hang_build_export_reload():
    c = _client()
    r = c.post("/api/generate", files={"file": ("p.png", _png(), "image/png")}, data={
        "mode": "lithophane", "shape": "rect", "width_mm": "100", "resolution": "40",
        "photo_ack": "true", "hang": "top"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["stats"]["watertight"] and j["mode"] == "lithophane"
    stl = c.get(j["downloads"]["stl"])
    assert stl.status_code == 200
    t = trimesh.load(io.BytesIO(stl.content), file_type="stl")
    assert t.is_watertight and t.euler_number == 0                # hole survived export+reload
    # the saved params rebuild the same geometry (history reload path)
    m = geometry.build(img(), "lithophane", {**j["params"], "resolution": 40})
    assert trimesh.Trimesh(m.bodies[0].vertices, m.bodies[0].faces).euler_number == 0


@pytest.mark.parametrize("bad", [
    {"hang": "middle"}, {"hang": "top", "hole_d": "9"}, {"hang": "top", "inset_mm": "2"},
    {"shape": "heart", "hang": "top"}, {"shape": "nightlight", "hang": "top"},
    {"shape": "nightlight", "stand": "true", "diameter_mm": "40", "height_mm": "60"},
])
def test_api_rejects_bad_hang_options(bad):
    c = _client()
    form = {"mode": "lithophane", "width_mm": "100", "resolution": "40", "photo_ack": "true"}
    form.update(bad)
    r = c.post("/api/generate", files={"file": ("p.png", _png(), "image/png")}, data=form)
    assert r.status_code == 400, (r.status_code, r.text)


def test_api_default_still_works():
    c = _client()
    r = c.post("/api/generate", files={"file": ("p.png", _png(), "image/png")}, data={
        "mode": "lithophane", "shape": "rect", "width_mm": "100", "resolution": "40", "photo_ack": "true"})
    assert r.status_code == 200 and r.json()["stats"]["watertight"]


def test_api_beginner_autotune_keeps_attachments():
    c = _client()
    r = c.post("/api/generate", files={"file": ("p.png", _png(), "image/png")}, data={
        "mode": "lithophane", "shape": "rect", "width_mm": "100", "resolution": "40",
        "beginner": "true", "photo_ack": "true", "hang": "two", "stand": "true"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert len(j["stats"]["bodies"]) == 2 and j["stats"]["watertight"]
    # the attachments must survive the beginner autotune: two real holes in the rebuilt panel
    m = geometry.build(img(), "lithophane", {**j["params"], "resolution": 40})
    t = trimesh.Trimesh(m.bodies[0].vertices, m.bodies[0].faces)
    assert t.euler_number == -2 and t.is_watertight


def test_api_preview_rebuild_keeps_attachments():
    # saved above the preview resolution: GET /builds/{bid} rebuilds at PREVIEW_RES with
    # the hang params; the download stays full-detail and watertight
    c = _client()
    r = c.post("/api/generate", files={"file": ("p.png", _png(), "image/png")}, data={
        "mode": "lithophane", "shape": "rect", "width_mm": "100", "resolution": "300",
        "photo_ack": "true", "hang": "top", "stand": "true"})
    assert r.status_code == 200
    j = r.json()
    assert j["params"]["resolution"] > 220                       # really above PREVIEW_RES
    b = c.get(f"/api/builds/{j['id']}")
    assert b.status_code == 200 and b.json()["stats"]["watertight"]
    t = trimesh.load(io.BytesIO(c.get(j["downloads"]["stl"]).content), file_type="stl")
    parts = t.split(only_watertight=False)
    assert {p.euler_number for p in parts} == {0, 2}          # holed panel + stand shell


def test_api_saved_build_rebuilds_after_cache_clear():
    # /download serves the persisted file; the rebuild path is load_model (used by the
    # build/preview endpoints). Clear the cache and force it, then check the geometry.
    from app.api import builds as builds_api
    from app.services.history import store
    c = _client()
    r = c.post("/api/generate", files={"file": ("p.png", _png(), "image/png")}, data={
        "mode": "lithophane", "shape": "rect", "width_mm": "100", "resolution": "40",
        "photo_ack": "true", "hang": "top", "stand": "true"})
    j = r.json()
    bid = j["id"]
    store.cache.pop(bid, None)                                    # force the rebuild-from-params path
    m = builds_api.load_model(bid)
    tp = trimesh.Trimesh(m.bodies[0].vertices, m.bodies[0].faces)
    assert tp.is_watertight and tp.euler_number == 0              # hole is back
    assert len(m.bodies) == 2                                     # stand is back
    t = trimesh.load(io.BytesIO(c.get(j["downloads"]["stl"]).content), file_type="stl")
    parts = t.split(only_watertight=False)
    assert {p.euler_number for p in parts} == {0, 2}             # both parts, hole intact
