"""Send to Slicer and Send to CAD for a generated lithophane.

The slicer handoff is an edit project (preview may be decimated; the mesh is the full one).
The CAD handoff is that same project: over the workspace face cap it opens a display-only
lighter mesh, and downloads stay at the generated triangle count.
"""
import base64
import io
from pathlib import Path

import numpy as np
import trimesh
from fastapi.testclient import TestClient
from PIL import Image

from app.api.cad import MAX_SCENE_EDGE_SEGS, MAX_SCENE_FACES
from app.main import app
from app.services.editproj import MAX_PREVIEW_FACES

ROOT = Path(__file__).resolve().parent.parent
c = TestClient(app)


def _png(w, h):
    im = Image.fromarray(np.linspace(0, 255, w * h, dtype=np.uint8).reshape(h, w), "L").convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _faces(b64):
    raw = np.frombuffer(base64.b64decode(b64), dtype="<u4")
    assert raw.size % 3 == 0 and raw.size
    return raw.reshape(-1, 3)


def _send(bid):
    e = c.post("/api/edit/new", data={"from_build": bid, "beginner": "true"})
    assert e.status_code == 200, e.text
    return e.json()["id"]


def test_handoff_ui_keeps_both_sends_reachable():
    css = (ROOT / "static" / "style.css").read_text().replace(" ", "")
    assert "zws-body>.result{width:100%" in css
    assert "width:420px" not in css.split("zws-body>.result")[1][:80]
    edit = (ROOT / "static" / "edit.js").read_text()
    cad = (ROOT / "static" / "cad.js").read_text()
    hand = (ROOT / "static" / "handoff.js").read_text()
    assert "editLoadGen" in edit and "zeim:open-edit" in edit
    assert "displayLite" in cad and "display_simplified" in cad
    assert 'slicer.onclick' in hand and "/api/edit/new" in hand
    assert "design-cad" in (ROOT / "static/project-flow.js").read_text(encoding="utf-8")


def test_small_lithophane_reaches_slicer_and_cad_at_full_detail():
    g = c.post("/api/generate", files={"file": ("s.png", _png(48, 64), "image/png")},
               data={"mode": "lithophane", "shape": "rect", "width_mm": "80", "resolution": "40",
                     "beginner": "false", "photo_ack": "true", "title": "Small lithophane"})
    assert g.status_code == 200, g.text
    assert g.json()["origin"] == "lithophane"
    full = g.json()["stats"]["triangles"]
    assert 0 < full < MAX_SCENE_FACES
    eid = _send(g.json()["id"])
    edit = c.get(f"/api/edit/{eid}")
    assert edit.status_code == 200, edit.text
    body = edit.json()
    assert body["analysis"]["triangles"] == full
    assert body["origin"] == "lithophane"
    assert body["base"]["origin"] == "lithophane"
    assert body["base"]["from_build"] == g.json()["id"]
    assert body["base"]["from_mode"] == "lithophane"
    prev = body["preview"]["bodies"][0]
    faces = _faces(prev["indices"])
    verts = np.frombuffer(base64.b64decode(prev["positions"]), dtype="<f4").reshape(-1, 3)
    assert len(faces) <= MAX_PREVIEW_FACES and int(faces.max()) < len(verts)
    scene = c.get(f"/api/cad/{eid}/scene")
    assert scene.status_code == 200, scene.text
    s = scene.json()
    assert s["display_simplified"] is False and s["triangles"] == full and s["bodies"]
    assert len(_faces(s["bodies"][0]["indices"])) == s["display_triangles"]
    assert all(o.get("op") != "simplify" for o in s["ops"])


def test_beginner_lithophane_over_cad_limit_opens_without_replacing_the_mesh():
    # Portrait and wide enough that beginner autotune (0.35 mm pitch at 100 mm) stays over the CAD cap.
    g = c.post("/api/generate", files={"file": ("p.png", _png(220, 300), "image/png")},
               data={"mode": "lithophane", "shape": "rect", "width_mm": "100", "beginner": "true",
                     "photo_ack": "true", "title": "Beginner lithophane"})
    assert g.status_code == 200, g.text
    gj = g.json()
    full = gj["stats"]["triangles"]
    assert full > MAX_SCENE_FACES, full
    eid = _send(gj["id"])
    edit = c.get(f"/api/edit/{eid}")
    assert edit.status_code == 200, edit.text
    body = edit.json()
    assert body["analysis"]["triangles"] == full and body["preview"]["decimated"] is True
    assert len(_faces(body["preview"]["bodies"][0]["indices"])) <= MAX_PREVIEW_FACES
    scene = c.get(f"/api/cad/{eid}/scene")
    assert scene.status_code == 200, scene.text
    s = scene.json()
    assert s["display_simplified"] is True and s["triangles"] == full
    assert 0 < s["display_triangles"] <= MAX_SCENE_FACES
    assert sum(len(_faces(b["indices"])) for b in s["bodies"]) == s["display_triangles"]
    for b in s["bodies"]:
        segs = np.frombuffer(base64.b64decode(b["edges"]), dtype="<f4")
        assert segs.size % 6 == 0 and segs.size // 6 <= MAX_SCENE_EDGE_SEGS
    assert all(o.get("op") != "simplify" for o in body["ops"])
    stl = c.get(s["downloads"]["stl"])
    assert stl.status_code == 200, stl.text[:200]
    mesh = trimesh.load(io.BytesIO(stl.content), file_type="stl", force="mesh")
    assert len(mesh.faces) == full
