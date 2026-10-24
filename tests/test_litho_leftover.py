"""Leftover lithophane extras: collage, decorative shapes, frame styles, stand end caps.

CMYK / multi-colour layers are intentionally out of scope for this pass.
"""
import io

import numpy as np
import pytest
import trimesh
from PIL import Image

from app.core import geometry, litho_collage, litho_frame, litho_shapes, litho_socket


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def img(w=120, h=90, v=180):
    a = np.full((h, w, 3), v, np.uint8)
    a[:, : w // 3] = 40
    a[h // 4 : 3 * h // 4, w // 2 :] = 220
    return Image.fromarray(a)


def build(**extra):
    p = dict(shape="rect", width_mm=80, min_thickness=0.8, max_thickness=3.0,
             border_mm=5, resolution=40, auto_contrast=False, smooth=0)
    p.update(extra)
    return geometry.build(img(), "lithophane", p)


# ------------------------------------------------------------------ collage
def test_collage_layouts_compose():
    ims = [img(60, 40, 50 + 40 * i) for i in range(4)]
    for layout in litho_collage.LAYOUTS:
        c = litho_collage.compose(ims, layout)
        assert c.mode == "RGB" and c.width >= 32 and c.height >= 32
        info = litho_collage.info(len(ims), layout)
        assert info["collage"] and info["layout"] == layout and info["photos"] == 4


@pytest.mark.parametrize("n", [1, 7])
def test_collage_count_bounds(n):
    with pytest.raises(ValueError, match="2..6"):
        litho_collage.check_count(n)


def test_collage_then_lithophane_watertight():
    c = litho_collage.compose([img(), img(80, 60, 90), img(50, 70, 140)], "grid")
    m = geometry.build(c, "lithophane", dict(shape="rect", width_mm=90, resolution=48,
                                             border_mm=3, auto_contrast=False, smooth=0))
    t = trimesh.Trimesh(m.bodies[0].vertices, m.bodies[0].faces)
    assert t.is_watertight and t.volume > 0


# ------------------------------------------------------------------ shapes
@pytest.mark.parametrize("shape", ["oval", "triangle", "scallop"])
def test_new_flat_shapes_watertight(shape):
    m = build(shape=shape, width_mm=70, resolution=48, border_mm=4)
    assert m.info["shape"] == shape
    t = trimesh.Trimesh(m.bodies[0].vertices, m.bodies[0].faces)
    assert t.is_watertight and t.euler_number == 2
    assert m.bodies[0].vertices[:, 2].min() == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("shape", ["oval", "triangle", "scallop"])
def test_outline_in_unit_box(shape):
    poly = litho_shapes.outline(shape, 512)
    assert poly.shape == (512, 2)
    assert np.abs(poly).max() <= 1.0 + 1e-6


# ------------------------------------------------------------------ frames
@pytest.mark.parametrize("style", ["plain", "double", "ledge"])
def test_frame_styles_rect(style):
    m = build(frame_style=style, border_mm=6, resolution=50)
    assert (m.info.get("frame_style") == style) or style == "plain"
    t = trimesh.Trimesh(m.bodies[0].vertices, m.bodies[0].faces)
    assert t.is_watertight


def test_frame_double_changes_rim_vs_plain():
    a = build(frame_style="plain", border_mm=8, resolution=60)
    b = build(frame_style="double", border_mm=8, resolution=60)
    va = a.bodies[0].vertices[:, 2]
    vb = b.bodies[0].vertices[:, 2]
    # double rim introduces a thinner channel band — z histogram should differ
    assert not np.allclose(np.sort(va), np.sort(vb))


@pytest.mark.parametrize("shape", ["circle", "oval", "heart"])
def test_frame_on_flat_shapes(shape):
    m = build(shape=shape, frame_style="ledge", border_mm=6, resolution=48)
    assert m.info.get("frame_style") == "ledge"
    t = trimesh.Trimesh(m.bodies[0].vertices, m.bodies[0].faces)
    assert t.is_watertight


def test_bad_frame_style():
    with pytest.raises(ValueError, match="frame_style"):
        litho_frame.check("ornate")


# ------------------------------------------------------------------ stand caps (mechanical sockets)
def test_end_caps_watertight_and_fit():
    caps = litho_socket.end_caps(100, 3.0)
    assert len(caps) == 2
    for v, f, name, info in caps:
        t = trimesh.Trimesh(v, f)
        assert t.is_watertight and name.startswith("stand_cap_")
        assert info["kind"] == "stand_end_cap"
        assert t.bounds[0, 2] == pytest.approx(0.0, abs=1e-6)


def test_stand_caps_on_model():
    m = build(stand=True, stand_caps=True, width_mm=100, max_thickness=3.0)
    names = [b.name for b in m.bodies]
    assert names == ["lithophane", "stand", "stand_cap_a", "stand_cap_b"]
    assert m.info["stand_caps"]["kind"] == "stand_end_cap"
    # parts must not overlap in XY footprint (parked side by side)
    boxes = [trimesh.Trimesh(b.vertices, b.faces).bounds for b in m.bodies]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            # allow tiny float noise; require a gap in x or y
            ai, aj = boxes[i], boxes[j]
            gap_x = aj[0, 0] - ai[1, 0] > 0.5 or ai[0, 0] - aj[1, 0] > 0.5
            gap_y = aj[0, 1] - ai[1, 1] > 0.5 or ai[0, 1] - aj[1, 1] > 0.5
            assert gap_x or gap_y


def test_stand_caps_require_stand():
    with pytest.raises(ValueError, match="stand"):
        build(stand_caps=True)


# ------------------------------------------------------------------ API
def _png():
    buf = io.BytesIO()
    img().save(buf, format="PNG")
    return buf.getvalue()


def test_api_frame_and_caps_and_parts(client):
    data = {"mode": "lithophane", "beginner": "false", "shape": "rect", "width_mm": "80",
            "resolution": "40", "border_mm": "5", "stand": "true", "stand_caps": "true",
            "frame_style": "double", "photo_ack": "true", "min_thickness": "0.8", "max_thickness": "3.0"}
    r = client.post("/api/generate", data=data, files={"file": ("t.png", _png(), "image/png")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["params"]["frame_style"] == "double" and j["params"]["stand_caps"] is True
    assert j["info"].get("frame_style") == "double"
    assert j["info"]["stand_caps"]["kind"] == "stand_end_cap"
    meta = client.get(f"/api/export/{j['id']}")
    assert meta.status_code == 200
    ids = [p["id"] for p in meta.json().get("parts", [])]
    assert "stand_cap_a" in ids and "stand_cap_b" in ids and "stand" in ids
    labels = {p["id"]: p["label"] for p in meta.json()["parts"]}
    assert "end cap" in labels["stand_cap_a"].lower()
    cap = client.get(f"/api/export/{j['id']}/download?format=stl&part=stand_cap_a")
    assert cap.status_code == 200
    assert len(cap.content) > 80


def test_api_collage(client):
    files = [
        ("file", ("a.png", _png(), "image/png")),
        ("extra", ("b.png", _png(), "image/png")),
        ("extra", ("c.png", _png(), "image/png")),
    ]
    data = {"mode": "lithophane", "beginner": "false", "shape": "rect", "width_mm": "90",
            "resolution": "40", "collage_layout": "hstrip", "photo_ack": "true",
            "min_thickness": "0.8", "max_thickness": "3.0", "border_mm": "3"}
    r = client.post("/api/generate", data=data, files=files)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["info"]["collage"] is True and j["info"]["photos"] == 3
    assert j["info"]["layout"] == "hstrip"
    assert j["params"]["collage_layout"] == "hstrip"


def test_api_new_shape(client):
    data = {"mode": "lithophane", "beginner": "false", "shape": "scallop", "width_mm": "70",
            "resolution": "40", "photo_ack": "true", "min_thickness": "0.8", "max_thickness": "3.0",
            "border_mm": "4", "frame_style": "ledge"}
    r = client.post("/api/generate", data=data, files={"file": ("t.png", _png(), "image/png")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["info"]["shape"] == "scallop" and j["info"]["frame_style"] == "ledge"
