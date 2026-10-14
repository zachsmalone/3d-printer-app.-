"""'Logo & Drawing to 3D' (trace2d): holes kept, watertight in every mode, cutter wall in range, colour layers separate,
thin-line warning + auto-thicken, size respected, SVG used as vectors, same upload checks as photos."""
import io
import json
import zipfile

import numpy as np
import pytest
import trimesh
from PIL import Image, ImageDraw

from app.core import trace2d as T


def png(im):
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()


def ring_o():
    """A letter-O-like ring: one piece with one hole."""
    im = Image.new("RGB", (300, 300), "white"); d = ImageDraw.Draw(im)
    d.ellipse((20, 20, 280, 280), fill="black"); d.ellipse((90, 90, 210, 210), fill="white")
    return im


def two_colours():
    im = Image.new("RGB", (400, 200), "white"); d = ImageDraw.Draw(im)
    d.rectangle((20, 20, 190, 180), fill=(220, 30, 30)); d.ellipse((220, 20, 380, 180), fill=(30, 60, 220))
    return im


def thin_line():
    im = Image.new("RGB", (400, 200), "white"); d = ImageDraw.Draw(im)
    d.rectangle((20, 20, 120, 180), fill="black"); d.line((120, 100, 380, 100), fill="black", width=2)
    return im


def mesh(m):
    v, f = m.solid(); return trimesh.Trimesh(v, f, process=False)


def test_trace_keeps_holes():
    im = ring_o()
    t = T.trace(png(im), im, {"width_mm": 50})
    assert t["pieces"] == 1 and t["holes"] == 1
    g = t["ink"].geoms[0]
    assert not g.contains(g.centroid)                        # the middle of the O stays open
    m = T.build(png(im), im, {"width_mm": 50, "height_mm": 3})
    tm = mesh(m)
    # a ray down through the hole hits nothing
    loc, _, _ = tm.ray.intersects_location([[25, 25, 10]], [[0, 0, -1]])
    assert len(loc) == 0


@pytest.mark.parametrize("opts", [
    {"out": "extrude"}, {"out": "extrude", "base": "rect"}, {"out": "extrude", "base": "rounded", "keyring": True},
    {"out": "extrude", "base": "outline"}, {"out": "extrude", "keyring": True},
    {"out": "cutter"}, {"out": "stamp"}, {"out": "stamp", "stamp_style": "recessed"}, {"out": "layers", "layers": 2},
])
def test_all_modes_watertight(opts):
    im = two_colours() if opts["out"] == "layers" else ring_o()
    m = T.build(png(im), im, {"width_mm": 60, **opts})
    tm = mesh(m)
    assert tm.is_watertight and tm.is_winding_consistent and tm.volume > 0
    for b in m.bodies:
        bt = trimesh.Trimesh(b.vertices, b.faces, process=False)
        assert bt.is_watertight and bt.volume > 0, b.name


@pytest.mark.parametrize("wall", [0.8, 1.0, 1.2])
def test_cookie_cutter_wall_in_range(wall):
    im = ring_o()
    m = T.build(png(im), im, {"out": "cutter", "width_mm": 60, "wall_mm": wall, "cutter_mm": 14, "flange_mm": 5})
    tm = mesh(m)
    assert 12 <= tm.extents[2] <= 15
    sec = tm.section(plane_origin=[0, 0, 8], plane_normal=[0, 0, 1])     # above the flange: just the wall
    poly = sec.to_2D()[0].polygons_full
    ring = max(poly, key=lambda p: p.area)
    width = ring.area / (ring.exterior.length + sum(i.length for i in ring.interiors)) * 2
    assert 0.7 <= width <= 1.3 and abs(width - wall) < 0.15
    low = tm.section(plane_origin=[0, 0, 1], plane_normal=[0, 0, 1]).to_2D()[0]
    assert sum(p.area for p in low.polygons_full) > 3 * ring.area     # wider grip flange at the bed


def test_colour_layers_separate():
    im = two_colours()
    m = T.build(png(im), im, {"out": "layers", "layers": 2, "width_mm": 80, "base_mm": 1.6, "layer_mm": 1.0})
    names = [b.name for b in m.bodies]
    assert names[0] == "Base" and len(m.bodies) == 3
    cols = {b.color for b in m.bodies}
    assert len(cols) == 3
    tops = sorted(round(b.vertices[:, 2].max(), 2) for b in m.bodies[1:])
    assert tops == [2.6, 3.6]                                 # different heights for colour swaps
    a, b = (trimesh.Trimesh(x.vertices, x.faces) for x in m.bodies[1:])
    assert a.intersection(b, engine="manifold").volume < 1e-3     # no colour overlaps another
    z = zipfile.ZipFile(io.BytesIO(__import__("app.core.exporters", fromlist=["x"]).to_3mf(m)))
    xml = z.read("3D/3dmodel.model").decode()
    assert xml.count("<object ") == 3 and xml.count("displaycolor") == 3


def test_thin_feature_warning_and_thicken():
    im = thin_line()
    m = T.build(png(im), im, {"width_mm": 60, "smooth": 0, "despeckle": 0})
    assert any("thinner than 0.8" in w for w in m.info["warnings"])
    t = T.trace(png(im), im, {"width_mm": 60, "smooth": 0, "despeckle": 0, "thicken": True})
    assert not t["warnings"] and t["notes"]
    assert T.thin_parts(t["ink"], 0.8).area < T.thin_parts(T.trace(png(im), im, {"width_mm": 60, "smooth": 0, "despeckle": 0})["ink"], 0.8).area


@pytest.mark.parametrize("w", [25, 80, 150])
def test_size_respected(w):
    im = ring_o().resize((300, 150))                          # proportions 2:1 kept
    m = T.build(png(im), im, {"width_mm": w, "height_mm": 3})
    ext = mesh(m).extents
    assert abs(ext[0] - w) < 0.02 * w
    assert abs(ext[1] / ext[0] - 0.5) < 0.03
    assert abs(ext[2] - 3) < 1e-6


def test_despeckle_removes_specks():
    im = ring_o(); d = ImageDraw.Draw(im)
    for x in range(5, 295, 40):
        d.rectangle((x, 3, x + 3, 6), fill="black")
    assert T.trace(png(im), im, {"despeckle": 30})["pieces"] == 1
    assert T.trace(png(im), im, {"despeckle": 0, "smooth": 0})["pieces"] > 1


SVG = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50">
<path d="M10 10 H40 V40 H10 Z M20 20 V30 H30 V20 Z"/><circle cx="75" cy="25" r="15"/></svg>'''


def test_svg_used_as_vectors_with_holes():
    t = T.trace(SVG, None, {"width_mm": 90})
    assert t["svg"] and t["pieces"] == 2 and t["holes"] == 1
    m = T.build(SVG, None, {"width_mm": 90})
    assert abs(mesh(m).extents[0] - 90) < 0.5 and mesh(m).is_watertight


def test_svg_unsafe_refused():
    xxe = b'<?xml version="1.0"?><!DOCTYPE s [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg xmlns="http://www.w3.org/2000/svg"><text>&x;</text></svg>'
    with pytest.raises(T.TraceError):
        T.svg_to_geom(xxe)
    with pytest.raises(T.TraceError):
        T.svg_to_geom(b'<svg xmlns="http://www.w3.org/2000/svg"><image href="x.png"/></svg>')


# ---------------- API: same upload safety path, result is a normal build ----------------
@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_api_requires_photo_permission(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "PHOTO_ACK_REQUIRED", True)
    r = client.post("/api/generate", data={"mode": "trace2d", "trace": json.dumps({"out": "extrude"})},
                    files={"file": ("o.png", png(ring_o()), "image/png")})
    assert r.status_code == 400
    r = client.post("/api/trace2d/preview", data={"trace": "{}"}, files={"file": ("o.png", png(ring_o()), "image/png")})
    assert r.status_code == 400


def test_api_build_and_preview(client):
    f = {"file": ("o.png", png(ring_o()), "image/png")}
    r = client.post("/api/trace2d/preview", data={"photo_ack": "true", "width_mm": "40", "trace": "{}"}, files=f)
    assert r.status_code == 200, r.text
    assert r.json()["holes"] == 1 and r.json()["svg"].startswith("<svg")
    r = client.post("/api/generate", data={"mode": "trace2d", "photo_ack": "true", "width_mm": "40",
                                           "trace": json.dumps({"out": "cutter"})}, files={"file": ("o.png", png(ring_o()), "image/png")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mode"] == "trace2d" and j["stats"]["watertight"] and j["info"]["bed_fit"]["ok"]
    assert client.get(j["downloads"]["stl"]).status_code == 200
    from app.api.builds import load_model
    from app.services.history import store
    store.cache.pop(j["id"], None)
    assert load_model(j["id"]).mode == "trace2d"             # rebuilt from the stored source after a restart
    client.delete(f"/api/builds/{j['id']}")
