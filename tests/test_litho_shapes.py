"""Lithophane shapes: one watertight mesh per shape, inside the K1 bed, thickness within min/max, white thinner than black."""
import io, zipfile
import numpy as np
import pytest
import trimesh
from PIL import Image

from app.core import exporters, geometry, litho_shapes
from app.services import willprint

TMIN, TMAX = 0.8, 3.0


def half_image():
    a = np.zeros((200, 200, 3), np.uint8)
    a[:, :100] = 255                       # left half white, right half black
    return Image.fromarray(a)


def make(shape, **kw):
    p = dict(shape=shape, width_mm=90, min_thickness=TMIN, max_thickness=TMAX, border_mm=2,
             resolution=120, diameter_mm=50, height_mm=50, auto_contrast=False, smooth=0, **kw)
    return geometry.build(half_image(), "lithophane", p)


def white_black_thickness(shape, v):
    if shape in litho_shapes.FLAT_SHAPES:
        top = v[v[:, 2] > 1e-6]
        cx, cy = top[:, 0].mean(), top[:, 1].mean()
        mid = np.abs(top[:, 1] - cy) < 10
        w = top[mid & (top[:, 0] < cx - 8) & (top[:, 0] > cx - 25), 2]
        b = top[mid & (top[:, 0] > cx + 8) & (top[:, 0] < cx + 25), 2]
        return w, b, top[:, 2]
    n = len(v) // 2
    outer, inner = v[:n], v[n:]
    if shape in ("nightlight", "cup"):
        c = np.array([0, 0, 0.0]); dist = lambda p: np.hypot(p[:, 0], p[:, 1])
    else:
        c = np.array([0, 0, inner[:, 2].max() - 25.0]); dist = lambda p: np.linalg.norm(p - c, axis=1)
    t = dist(outer) - dist(inner)
    zmid0 = np.abs(outer[:, 2] - outer[:, 2].mean()) < 0.25 * np.ptp(outer[:, 2])
    if shape in ("globe", "cup"):                   # poles / floor / foot are solid by design: check the picture wall
        t = np.where(zmid0, t, (TMIN + TMAX) / 2)
    zmid = np.abs(outer[:, 2] - outer[:, 2].mean()) < 0.25 * np.ptp(outer[:, 2])
    r = dist(inner).mean()
    w = t[zmid & (outer[:, 1] < -0.5 * r)]
    b = t[zmid & (outer[:, 1] > 0.5 * r)]
    return w, b, t


@pytest.mark.parametrize("shape", litho_shapes.FLAT_SHAPES + litho_shapes.CURVED_SHAPES)
def test_shape_is_printable(shape):
    m = make(shape)
    v, f = m.solid()
    tm = trimesh.Trimesh(v, f, process=False)
    assert tm.is_watertight and tm.is_winding_consistent and tm.volume > 0
    assert len(m.bodies) == 1 and m.info["shape"] == shape
    assert willprint.bed_fit(tuple(float(x) for x in tm.extents), "creality_k1")["ok"]
    assert v[:, 2].min() >= -1e-9                                   # sits on the bed
    w, b, t = white_black_thickness(shape, v)
    assert len(w) and len(b)
    assert t.min() >= TMIN - 1e-6 and t.max() <= TMAX + 1e-6
    assert w.mean() < b.mean() - 1.0                               # white pixel -> thinner than black
    for ext in ("stl", "3mf"):
        data = exporters.WRITERS[ext](m)
        if ext == "3mf":
            assert zipfile.is_zipfile(io.BytesIO(data))
        back = trimesh.load(io.BytesIO(data), file_type=ext, force="mesh")
        assert back.is_watertight


def test_night_light_inside_fits_the_light():
    m = make("nightlight", )
    assert m.info["inner_diameter_mm"] == pytest.approx(50 + litho_shapes.CLEARANCE_MM)


def test_globe_is_a_full_hollow_sphere_open_at_the_bottom_on_a_flat_foot():
    m = make("globe")
    v, f = m.solid()
    n = len(v) // 2
    inner = v[n:]
    top = inner[:, 2].max(); c = np.array([0, 0, top - 25.0])
    inner = inner[:-1]
    r = np.linalg.norm(inner - c, axis=1)
    sphere = inner[np.abs(r - 25) < 1e-6]
    assert np.degrees(np.arcsin((sphere[:, 2] - c[2]) / 25)).max() > 85     # reaches the pole: full sphere
    assert m.info["mapping"] == "equirectangular"
    assert 0 < m.info["opening_diameter_mm"] < 50                          # light goes in at the bottom
    foot = v[v[:, 2] < 1e-6]
    assert len(foot) >= 2 * 64 and np.ptp(foot[:, 2]) == 0                  # flat ring on the bed
    tm = trimesh.Trimesh(v, f, process=False)
    assert tm.volume < 4 / 3 * np.pi * 28 ** 3 * 0.5                         # hollow
    assert tm.extents[0] == pytest.approx(50 + 2 * TMAX, abs=0.5)


def test_big_globe_reports_bed_fit_warning():
    from app.services import willprint
    m = geometry.build(half_image(), "lithophane", dict(shape="globe", diameter_mm=240, resolution=40,
                                                        min_thickness=TMIN, max_thickness=TMAX))
    assert not willprint.bed_fit(tuple(float(x) for x in trimesh.Trimesh(*m.solid()).extents), "creality_k1")["ok"]


def test_cup_has_solid_bottom_and_open_top():
    m = make("cup")
    v, f = m.solid()
    tm = trimesh.Trimesh(v, f, process=False)
    assert tm.is_watertight and m.info["bottom_mm"] == pytest.approx(2.0)
    # a ray straight down the middle hits the floor at z=2 (solid bottom) and nothing above it (open top)
    hits = tm.ray.intersects_location([[0, 0, 100]], [[0, 0, -1]])[0]
    assert sorted(np.round(hits[:, 2], 3)) == [0.0, 2.0]
    assert tm.extents[2] == pytest.approx(50)


@pytest.mark.parametrize("shape", litho_shapes.FLAT_SHAPES)
def test_flat_outline_is_smooth_vector_curve(shape):
    m = make(shape)
    v, _ = m.solid()
    half = 45.0
    bottom = v[v[:, 2] == 0] - [half, half, 0]
    rr = np.hypot(bottom[:, 0], bottom[:, 1]); ang = np.arctan2(bottom[:, 1], bottom[:, 0])
    ideal = litho_shapes.outline_radius(shape, ang) * half
    edge = np.abs(rr - ideal) < 1e-6 * half + 1e-6                         # wall vertices sit ON the ideal curve
    assert edge.sum() >= 256
    pts = bottom[edge][np.argsort(ang[edge])][:, :2]
    # every edge vertex agrees with an independent dense curve within 0.05 mm
    dense = litho_shapes.outline(shape, 20000) * half
    from scipy.spatial import cKDTree
    assert cKDTree(dense).query(pts)[0].max() < 0.05
    seg = np.diff(np.vstack([pts, pts[:1]]), axis=0)
    axis = (np.abs(seg[:, 0]) < 1e-9) | (np.abs(seg[:, 1]) < 1e-9)
    if shape == "square":
        assert axis.all()                                                 # straight sides, no steps either
    else:
        if shape == "hexagon":                                            # pointy-top hexagon: its two flat sides ARE vertical,
            mid = (pts + np.roll(pts, -1, axis=0)) / 2                    # so axis-aligned segments may only lie on those sides
            on_side = np.abs(np.abs(mid[:, 0]) - np.cos(np.pi / 6) * half) < 1e-6 * half + 1e-6
            assert (axis <= on_side).all() and on_side.any()
            axis = axis & ~on_side
        assert axis.mean() < 0.02                                         # no axis-aligned stair steps
        # and no zig-zag: the direction changes gently between neighbours (corners of the star excepted)
        d = np.arctan2(seg[:, 1], seg[:, 0]); turn = np.abs((np.diff(np.append(d, d[0])) + np.pi) % (2 * np.pi) - np.pi)
        assert np.mean(turn > np.radians(20)) < 0.03


def test_unknown_shape_and_color_mode_are_refused():
    with pytest.raises(ValueError):
        make("octagon")                    # hexagon is a real shape since eec555d; octagon is not
    with pytest.raises(ValueError):
        make("heart", color_mode="cmyk")


def test_api_accepts_shape_and_reports_bed_fit():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    buf = io.BytesIO(); half_image().save(buf, "PNG")
    r = c.post("/api/generate", files={"file": ("h.png", buf.getvalue(), "image/png")},
               data={"mode": "lithophane", "shape": "heart", "width_mm": "60", "resolution": "80"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["info"]["shape"] == "heart" and j["info"]["bed_fit"]["ok"] and j["stats"]["watertight"]
    r = c.post("/api/generate", files={"file": ("h.png", buf.getvalue(), "image/png")},
               data={"mode": "lithophane", "shape": "nightlight", "diameter_mm": "40", "height_mm": "50", "beginner": "true"})
    assert r.status_code == 200, r.text
    assert r.json()["params"]["shape"] == "nightlight"
    r = c.post("/api/generate", files={"file": ("h.png", buf.getvalue(), "image/png")},
               data={"mode": "lithophane", "shape": "blob"})
    assert r.status_code == 400
