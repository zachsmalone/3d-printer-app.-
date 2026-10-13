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
    if shape == "nightlight":
        c = np.array([0, 0, 0.0]); dist = lambda p: np.hypot(p[:, 0], p[:, 1])
    else:
        c = np.array([0, 0, inner[:, 2].mean()]); dist = lambda p: np.linalg.norm(p - c, axis=1)
    t = dist(outer) - dist(inner)
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


def test_globe_band_keeps_overhang_under_45_degrees():
    m = make("globe")
    assert m.info["band_deg"] <= 40


def test_unknown_shape_and_color_mode_are_refused():
    with pytest.raises(ValueError):
        make("hexagon")
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
