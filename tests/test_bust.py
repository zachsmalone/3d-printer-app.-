"""Bust mode: photo → volumetric head/shoulders on a clean pedestal + auto mask."""
from __future__ import annotations

import base64
import io

import numpy as np
import pytest
import trimesh
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from app.core import geometry, autotune, bust_detect
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


def _skin_portrait(w=160, h=200):
    """Synthetic portrait with a skin-tone head so heuristic detect has something to find."""
    im = Image.new("RGB", (w, h), (40, 90, 50))  # greenish backdrop (not skin)
    d = ImageDraw.Draw(im)
    # head
    d.ellipse((w * 0.28, h * 0.08, w * 0.72, h * 0.48), fill=(210, 170, 140))
    # neck + shoulders
    d.polygon([
        (w * 0.42, h * 0.42), (w * 0.58, h * 0.42),
        (w * 0.78, h * 0.78), (w * 0.22, h * 0.78),
    ], fill=(200, 160, 130))
    d.rectangle((w * 0.15, h * 0.72, w * 0.85, h * 0.95), fill=(30, 30, 80))  # shirt
    return im


def test_bust_builds_watertight_with_pedestal():
    m = geometry.build(_photo(), "bust", {"width_mm": 60, "resolution": 60, "base_mm": 10, "relief_mm": 5,
                                           "base_style": "round", "base_margin": 4, "back_mm": 12})
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
    assert m.info.get("volumetric") is True
    assert m.info.get("back_mm", 0) >= 10
    assert m.info.get("core_mm", 0) >= 2


@pytest.mark.parametrize("style", ["rect", "outline"])
def test_bust_rect_and_outline_styles(style):
    m = geometry.build(_photo(), "bust", {"width_mm": 50, "resolution": 48, "base_mm": 8, "relief_mm": 4,
                                           "base_style": style, "base_margin": 3, "back_mm": 10})
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
    cut = geometry.build(im, "bust", {"width_mm": 50, "resolution": 48, "base_mm": 8, "relief_mm": 4,
                                      "back_mm": 10, "select": sel})
    assert cut.info.get("select")
    vc, _ = cut.solid()
    assert len(vc) > 50


def test_bust_without_select_adds_tip_warning():
    m = geometry.build(_photo(), "bust", {"width_mm": 40, "resolution": 40, "base_mm": 8, "relief_mm": 4})
    warns = m.info.get("warnings") or []
    assert any("auto" in w.lower() or "head and shoulders" in w.lower() or "trace" in w.lower() for w in warns)


def test_bust_volumetric_thicker_than_flat_back():
    """Rounded back should add real depth vs a flat-back (back_mm=0) plaque."""
    flat = geometry.build(_photo(), "bust", {"width_mm": 50, "resolution": 48, "base_mm": 8, "relief_mm": 4,
                                              "back_mm": 0, "core_mm": 3})
    full = geometry.build(_photo(), "bust", {"width_mm": 50, "resolution": 48, "base_mm": 8, "relief_mm": 4,
                                              "back_mm": 16, "core_mm": 5})
    z_flat = float(np.ptp(flat.bodies[0].vertices[:, 2]))
    z_full = float(np.ptp(full.bodies[0].vertices[:, 2]))
    assert z_full > z_flat + 8, (z_flat, z_full)
    tf = trimesh.Trimesh(*full.solid(), process=False)
    assert tf.is_watertight and tf.volume > 0


def test_autotune_bust():
    P, notes = autotune.autotune(_photo(), "bust", 80, "standard")
    assert P["base_mm"] == 12.0
    assert P["base_style"] == "round"
    assert P["relief_mm"] > 0
    assert P["back_mm"] == 14.0
    assert any(n["label"] == "Pedestal" for n in notes)
    assert any(n["label"] == "Rounded back" for n in notes)


def test_detect_head_shoulders_returns_mask_and_path():
    sel = bust_detect.auto_select(_skin_portrait())
    assert sel["v"] == 1
    assert sel["auto"] is True
    assert sel["method"] in ("face", "skin", "prior")
    assert "starting mask" in sel["tip"].lower()
    assert sel["paths"] and len(sel["paths"][0]["pts"]) >= 3
    from app.core.selectmask import decode_mask
    a = decode_mask(sel["mask"])
    assert a.shape[0] >= 4 and a.shape[1] >= 4
    assert 0.05 <= float((a >= 0.5).mean()) <= 0.85


def test_detect_prior_always_produces_usable_mask():
    # Uniform noise-ish image with no face: still returns a classical prior silhouette
    im = Image.new("RGB", (100, 140), (90, 90, 90))
    mask, method = bust_detect.head_shoulders_mask(im)
    assert method in ("face", "skin", "prior")
    assert 0.05 <= mask.mean() <= 0.7


def test_generate_bust_api():
    buf = io.BytesIO(); _photo().save(buf, format="PNG")
    c = TestClient(app)
    r = c.post("/api/generate", files={"file": ("bust.png", buf.getvalue(), "image/png")},
               data={"mode": "bust", "width_mm": "50", "resolution": "48", "base_mm": "10",
                     "relief_mm": "5", "base_style": "round", "base_margin": "4", "back_mm": "12",
                     "photo_ack": "true"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mode"] == "bust"
    assert j["stats"]["watertight"]
    assert j.get("info", {}).get("volumetric") is True or j.get("info", {}).get("back_mm", 0) >= 0


def test_auto_mask_api():
    buf = io.BytesIO(); _skin_portrait().save(buf, format="PNG")
    c = TestClient(app)
    r = c.post("/api/bust/auto-mask", files={"file": ("p.png", buf.getvalue(), "image/png")},
               data={"photo_ack": "true"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert "starting mask" in j["tip"].lower()
    assert j["select"]["paths"]
    assert j["method"] in ("face", "skin", "prior")
    # Apply the returned select through a bust build
    m = geometry.build(_skin_portrait(), "bust", {
        "width_mm": 50, "resolution": 40, "base_mm": 8, "relief_mm": 4, "back_mm": 12,
        "select": j["select"],
    })
    assert m.info.get("select")
    assert trimesh.Trimesh(*m.solid(), process=False).is_watertight
