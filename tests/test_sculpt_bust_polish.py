"""Live Sculpt tells the truth about a stroke, and Bust mode names what a photo actually builds."""
from __future__ import annotations

import numpy as np
import pytest
import trimesh
from PIL import Image

from app.core import bust_detect, geometry, sculptws
from app.core.meshedit import OpError


def _plate():
    # Front at z=1, back at z=0. Same corners the brush preview uses.
    v = np.array([
        [0, 0, 1], [3, 0, 1], [0, 3, 1],
        [0, 0, 0], [3, 0, 0], [0, 3, 0],
    ], float)
    f = np.array([[0, 1, 2], [3, 5, 4]], np.int64)
    return trimesh.Trimesh(v, f, process=False)


def test_draw_matches_the_preview_falloff_and_leaves_the_back():
    m = _plate()
    out, rep = sculptws.op_sculpt_stroke(m, {
        "brush": "draw", "points": [[0, 0, 1]], "normal": [0, 0, 1], "radius": 4, "strength": 1,
    })
    i = int(np.linalg.norm(out.vertices - [0, 0, 1.6], axis=1).argmin())
    assert abs(out.vertices[i, 2] - 1.6) < 1e-6
    back = out.vertices[:, 2] < 0.2
    assert np.allclose(out.vertices[back, 2], 0)
    assert "back of a thin wall" in rep["message"]


def test_strength_zero_does_not_claim_the_brush_hit_the_back():
    with pytest.raises(OpError, match="Strength is 0"):
        sculptws.op_sculpt_stroke(_plate(), {
            "brush": "draw", "points": [[0, 0, 1]], "normal": [0, 0, 1], "radius": 4, "strength": 0,
        })


def test_a_back_only_dab_names_the_back_and_leaves_the_mesh():
    m = _plate()
    before = m.vertices.copy()
    with pytest.raises(OpError, match="back of a thin wall"):
        sculptws.op_sculpt_stroke(m, {
            "brush": "draw", "points": [[0, 0, 0]], "normal": [0, 0, 1], "radius": 0.5, "strength": 1,
        })
    assert np.allclose(m.vertices, before)


def test_mirror_label_names_the_centre_not_world_x():
    lab = sculptws.label("sculpt_stroke", {"brush": "draw", "radius": 5, "symmetry_x": True})
    assert lab.endswith("· mirror")
    assert "X sym" not in lab
    m = trimesh.creation.icosphere(subdivisions=2, radius=10)
    out, rep = sculptws.op_sculpt_stroke(m, {
        "brush": "draw", "points": [[10, 0, 0]], "normal": [1, 0, 0], "radius": 4, "strength": 1, "symmetry_x": True,
    })
    assert "mirror across the centre" in rep["message"]
    assert out.vertices[:, 0].min() < -10


def test_bust_without_a_face_says_the_outline_is_a_starting_shape():
    sel = bust_detect.auto_select(Image.new("RGB", (100, 140), (90, 90, 90)))
    assert "starting mask" in sel["tip"].lower()
    if sel["method"] == "prior":
        assert "No face was found" in sel["tip"]
    elif sel["method"] == "skin":
        assert "not a found face" in sel["tip"]
    else:
        assert sel["method"] == "face"


def test_a_skipped_pedestal_is_a_warning(monkeypatch):
    def boom(mesh, params):
        raise RuntimeError("nope")

    monkeypatch.setattr("app.core.meshedit.op_base", boom)
    m = geometry.build(Image.new("RGB", (40, 50), (180, 140, 120)), "bust", {
        "width_mm": 40, "resolution": 24, "base_mm": 8, "relief_mm": 4, "back_mm": 8,
    })
    assert m.info["pedestal"].get("skipped")
    assert any("Pedestal could not be added" in w for w in m.info["warnings"])
    assert any("photo bust" in w.lower() for w in m.info["warnings"])


def test_sculpt_and_bust_copy_is_honest_in_source():
    cad = open("static/cad.js", encoding="utf-8").read()
    assert "brushes · subdivide" in cad
    assert "brushes · remesh" not in cad
    assert "Mirror left and right" in cad
    assert "X = 0" not in cad
    assert "this is the stroke that will be saved" in cad
    assert "eventOnChrome" in cad
    assert "Subdivide evenly" in cad
    brush = open("static/sculptbrush.js", encoding="utf-8").read()
    assert "0.15" in brush and "0.4" in brush
    sel = open("static/selectmode.js", encoding="utf-8").read()
    assert "Head and shoulders" in sel
    assert "not a cut-out head" in sel
    css = open("static/style.css", encoding="utf-8").read().replace(" ", "")
    assert ".wsbar{position:relative;z-index:40;" in css
    assert "left:auto;right:8px" in css
    app = open("static/app.js", encoding="utf-8").read()
    assert "bustNote" in app and "not an AI figure" in app
