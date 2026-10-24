"""Bust mode: photo → relief face on a clean pedestal."""
from __future__ import annotations

import base64
import io

import pytest
import trimesh
from PIL import Image
from fastapi.testclient import TestClient

from app.core import geometry, autotune
from app.main import app


def _photo(w=120, h=160):
    im = Image.new("RGB", (w, h), (180, 140, 120))
    px = im.load()
    for y in range(h):
        for x in range(w):
            cx, cy = w / 2, h * 0.35
            if (x - cx) ** 2 / (w * 0.22) ** 2 + (y - cy) ** 2 / (h * 0.22) ** 2 < 1:
                px[x, y] = (220, 190, 160)
            elif y > h * 0.45 and abs(x - w / 2) < w * 0.35:
                px[x, y] = (200, 160, 140)
    return im


def test_bust_builds_watertight_with_pedestal():
    m = geometry.build(_photo(), "bust", {"width_mm": 60, "resolution": 60, "base_mm": 10, "relief_mm": 5,
                                           "base_style": "round", "base_margin": 4})
    assert m.mode == "bust"
    assert m.bodies and m.bodies[0].name == "bust"
    v, f = m.solid()
    assert len(v) > 100 and len(f) > 100
    t = trimesh.Trimesh(v, f, process=False)
    assert t.is_watertight
    ped = m.info.get("pedestal") or {}
    assert ped.get("style") == "round"
    assert ped.get("thickness_mm") == 10
    assert not ped.get("skipped"), ped


@pytest.mark.parametrize("style", ["rect", "outline"])
def test_bust_rect_and_outline_styles(style):
    m = geometry.build(_photo(), "bust", {"width_mm": 50, "resolution": 48, "base_mm": 8, "relief_mm": 4,
                                           "base_style": style, "base_margin": 3})
    assert m.info["pedestal"]["style"] == style
    v, f = m.solid()
    assert trimesh.Trimesh(v, f, process=False).is_watertight


def test_bust_with_select_crops_to_region():
    im = _photo(100, 120)
    mask = Image.new("L", (64, 64), 0)
    for y in range(10, 54):
        for x in range(16, 48):
            mask.putpixel((x, y), 255)
    buf = io.BytesIO(); mask.save(buf, format="PNG")
    sel = {"v": 1, "mask": base64.b64encode(buf.getvalue()).decode(), "soft": 0, "paths": [
        {"op": "new", "pts": [[0.25, 0.15], [0.75, 0.15], [0.75, 0.85], [0.25, 0.85]]}
    ]}
    cut = geometry.build(im, "bust", {"width_mm": 50, "resolution": 48, "base_mm": 8, "relief_mm": 4, "select": sel})
    assert cut.info.get("select")
    vc, _ = cut.solid()
    assert len(vc) > 50


def test_bust_without_select_adds_tip_warning():
    m = geometry.build(_photo(), "bust", {"width_mm": 40, "resolution": 40, "base_mm": 8, "relief_mm": 4})
    warns = m.info.get("warnings") or []
    assert any("head and shoulders" in w.lower() or "trace" in w.lower() for w in warns)


def test_autotune_bust():
    P, notes = autotune.autotune(_photo(), "bust", 80, "standard")
    assert P["base_mm"] == 12.0
    assert P["base_style"] == "round"
    assert P["relief_mm"] > 0
    assert any(n["label"] == "Pedestal" for n in notes)


def test_generate_bust_api():
    buf = io.BytesIO(); _photo().save(buf, format="PNG")
    c = TestClient(app)
    r = c.post("/api/generate", files={"file": ("bust.png", buf.getvalue(), "image/png")},
               data={"mode": "bust", "width_mm": "50", "resolution": "48", "base_mm": "10",
                     "relief_mm": "5", "base_style": "round", "base_margin": "4", "photo_ack": "true"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mode"] == "bust"
    assert j["stats"]["watertight"]
