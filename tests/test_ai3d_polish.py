"""Photo prep, mesh cleanup, flat cooldown, and hand-off for the existing TripoSR path."""
import base64
import importlib.util
import io
import re
import time
from pathlib import Path

import numpy as np
import pytest
import trimesh
from PIL import Image

from app import config
from app.core import ai3d_mesh
from app.core.ai3d_prep import prepare_image
from app.services import ai3d
from tests.b1 import ADULT, client

ROOT = Path(__file__).resolve().parents[1]


def _png(arr) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(np.asarray(arr, np.uint8), "RGB").save(buf, "PNG")
    return buf.getvalue()


def _open(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    ai3d.reset()
    monkeypatch.setenv("ZEIM_2D3D_ENABLED", "1")
    monkeypatch.setattr(config, "TESTING_MODE", False)
    monkeypatch.setattr(config, "AI3D_FAKE", True)
    monkeypatch.setattr(config, "AI3D_PRO_ONLY", False)
    monkeypatch.setattr(config, "AI3D_DAILY_CAP", 5)
    monkeypatch.setattr(config, "AI3D_COOLDOWN_MIN", 5)
    monkeypatch.setattr(config, "AI3D_COOLDOWN_STEP_MIN", 0)
    yield
    ai3d.reset()


def _start(c, png, mode="figure", **extra):
    form = {"mode": mode, "photo_ack": "true", "title": "Tango", **extra}
    return c.post("/api/ai3d/jobs", files={"file": ("s.png", png, "image/png")}, data=form)


def _wait(c, jid):
    for _ in range(200):
        j = c.get(f"/api/ai3d/jobs/{jid}").json()
        if j["state"] != "running":
            return j
        time.sleep(0.05)
    raise AssertionError("job never finished")


def _subject():
    im = np.full((300, 400, 3), 230, np.uint8)
    im[40:160, 20:120] = 30
    return im


def test_prep_centres_subject_on_grey_and_can_be_turned_off():
    png, notes = prepare_image(_png(_subject()), "figure", crop=True, tone=False, grey=True)
    out = _open(png)
    dark = np.argwhere(out.mean(axis=2) < 80)
    cy, cx = dark.mean(axis=0)
    h, w = out.shape[:2]
    assert abs(cy - (h - 1) / 2) < 0.2 * h and abs(cx - (w - 1) / 2) < 0.2 * w
    assert abs(int(out[0, 0, 0]) - 128) < 3
    text = " ".join(notes)
    assert "Centred the subject" in text and "grey" in text.lower()

    kept, kept_notes = prepare_image(_png(_subject()), "figure", crop=False, tone=False, grey=False)
    raw = _open(kept)
    assert raw[2, 2].tolist() == [230, 230, 230]
    assert "Background left as in the photo." in kept_notes
    assert "Centred the subject" not in " ".join(kept_notes)


def test_prep_brightens_a_dark_photo_without_clipping_and_tone_off_leaves_it():
    dark = np.full((64, 64, 3), 12, np.uint8)
    png, notes = prepare_image(_png(dark), "figure", crop=False, tone=True, grey=False)
    out = _open(png)
    assert "Brightened a dark photo" in " ".join(notes)
    assert 25 < float(out.mean()) < 80
    assert int(out.max()) < 255
    same, notes_off = prepare_image(_png(dark), "figure", crop=False, tone=False, grey=False)
    assert "Brightened" not in " ".join(notes_off)
    assert float(_open(same).mean()) < 20


def test_prep_bust_keeps_the_top_of_the_subject():
    tall = np.full((400, 200, 3), 240, np.uint8)
    tall[20:360, 40:160] = 40
    tall[20:80, 40:160] = (0, 0, 180)
    tall[300:360, 40:160] = (180, 0, 0)
    png, notes = prepare_image(_png(tall), "bust", crop=True, tone=False, grey=True)
    out = _open(png)
    assert any("head and shoulders" in n for n in notes)
    assert int((out[:, :, 2] > 150).sum()) > 0
    assert int((out[:, :, 0] > 150).sum()) == 0


def test_light_smooth_keeps_a_spike_and_quiets_grain():
    rng = np.random.default_rng(0)
    noisy = trimesh.creation.icosphere(3, radius=30)
    noisy.vertices += rng.normal(0, 0.25, noisy.vertices.shape)
    smoothed, note = ai3d_mesh.light_smooth(noisy, 80)
    assert "Light smoothing" in note
    assert np.linalg.norm(smoothed.vertices - noisy.vertices, axis=1).mean() > 0.01
    assert np.abs(smoothed.extents - noisy.extents).max() < 2.4

    spiky = trimesh.creation.icosphere(3, radius=20)
    v = spiky.vertices.copy()
    v[int(np.argmax(v[:, 2])), 2] += 15
    spiky.vertices = v
    peak = float(v[:, 2].max())
    kept, skipped = ai3d_mesh.light_smooth(spiky, 40)
    assert "skipped" in skipped.lower()
    assert float(kept.vertices[:, 2].max()) == pytest.approx(peak)


def test_decimate_gate_reduces_a_dense_mesh_and_keeps_it_closed():
    sphere = trimesh.creation.icosphere(4, radius=30)
    out, note = ai3d_mesh.decimate_for_print(sphere, over=5000, target=2000)
    assert "Triangle count" in note
    assert len(out.faces) < len(sphere.faces)
    assert out.is_watertight
    assert abs(out.volume - sphere.volume) / abs(sphere.volume) < 0.05


def test_finish_fills_holes_and_uses_the_decimate_gate(monkeypatch):
    monkeypatch.setattr(ai3d_mesh, "DECIMATE_OVER", 1000)
    monkeypatch.setattr(ai3d_mesh, "DECIMATE_TARGET", 400)
    raw = trimesh.creation.icosphere(3)
    raw.faces = raw.faces[:-20]
    model, rep = ai3d_mesh.finish(raw, "figure", 80)
    v, f = model.solid()
    mesh = trimesh.Trimesh(v, f, process=False)
    assert mesh.is_watertight
    assert abs(rep["height_mm"] - 80) < 1
    text = " ".join(rep["notes"])
    assert "Filled holes" in text
    assert "Triangle count" in text
    assert len(f) < 1280


def test_preview_matches_the_exported_mesh_and_edit_does_not_restart_cooldown():
    c = client(ADULT)
    r = _start(c, _png(_subject()))
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job"])
    assert job["state"] == "done", job
    res = job["result"]
    assert any("Centred the subject" in n or "grey" in n.lower() for n in res["report"]["notes"])
    idx = np.frombuffer(base64.b64decode(res["preview"]["bodies"][0]["indices"]), dtype="<u4")
    info = c.get(f"/api/export/{res['id']}").json()
    stl = c.get(info["downloads"]["stl"])
    assert stl.status_code == 200
    exported = trimesh.load(trimesh.util.wrap_as_stream(stl.content), file_type="stl", force="mesh")
    assert len(exported.faces) == len(idx) // 3
    plan = c.get("/api/ai3d/status").json()["plan"]
    assert plan["reason"] == "cooldown" and plan["cooldown_min"] == 5
    time.sleep(1.2)
    edit = c.post("/api/edit/new", data={"from_build": res["id"], "beginner": "true"})
    assert edit.status_code == 200, edit.text
    body = c.get(f"/api/edit/{edit.json()['id']}")
    assert body.status_code == 200, body.text
    assert body.json()["analysis"]["triangles"] == len(exported.faces)
    again = c.get("/api/ai3d/status").json()["plan"]
    assert again["reason"] == "cooldown"
    assert plan["wait_s"] - again["wait_s"] >= 1
    blocked = _start(c, _png(_subject()))
    assert blocked.status_code == 429 and blocked.json()["detail"]["code"] == "cooldown"


def test_prep_preview_does_not_start_a_cooldown_or_a_mesh():
    c = client(ADULT)
    r = c.post("/api/ai3d/prep", files={"file": ("s.png", _png(_subject()), "image/png")},
               data={"mode": "figure", "photo_ack": "true", "prep_tone": "false"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["png_b64"] and any("Centred" in n for n in body["notes"])
    plan = c.get("/api/ai3d/status").json()["plan"]
    assert plan["allowed"] is True and plan["wait_s"] == 0 and plan["used_today"] == 0
    assert c.get("/api/builds").json()["builds"] == [] or all(
        b.get("mode") != "ai3d" for b in c.get("/api/builds").json().get("builds", []))


def test_prep_is_refused_when_2d3d_is_off(monkeypatch):
    monkeypatch.setenv("ZEIM_2D3D_ENABLED", "0")
    c = client(ADULT)
    r = c.post("/api/ai3d/prep", files={"file": ("s.png", _png(_subject()), "image/png")},
               data={"mode": "figure", "photo_ack": "true"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "unavailable"


def test_failed_conversion_does_not_start_the_cooldown(monkeypatch):
    def boom(*_a, **_k):
        raise ai3d.EngineError("The engine could not make a model from this photo.")

    monkeypatch.setattr(ai3d, "engine_call", boom)
    c = client(ADULT)
    r = _start(c, _png(_subject()))
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job"])
    assert job["state"] == "error"
    plan = c.get("/api/ai3d/status").json()["plan"]
    assert plan["allowed"] is True and plan["wait_s"] == 0 and plan.get("used_today", 0) == 0


def test_pro_cooldown_stays_a_flat_five_minutes(monkeypatch):
    monkeypatch.setattr(config, "AI3D_PRO_ONLY", True)
    monkeypatch.setattr(config, "AI3D_COOLDOWN_STEP_MIN", 0)

    class A:
        sid = "pro-flat"
        user = {"plan": "pro"}

    assert ai3d.plan(A)["allowed"] is True
    ai3d.mark_done(A)
    ai3d.mark_done(A)
    plan = ai3d.plan(A)
    assert plan["cooldown_min"] == 5
    assert 290 <= plan["wait_s"] <= 300


def test_testing_mode_lifts_the_pause(monkeypatch):
    monkeypatch.setattr(config, "TESTING_MODE", True)

    class A:
        sid = "tester"
        user = {}

    ai3d.mark_done(A)
    plan = ai3d.plan(A)
    assert plan["testing_mode"] is True and plan["allowed"] is True and plan["wait_s"] == 0


def test_worker_prepared_photo_is_only_resized():
    path = ROOT / "workers" / "ai3d" / "server.py"
    spec = importlib.util.spec_from_file_location("zeim_ai3d_server_prep", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    im, notes = mod.prepare(_png(_subject()), "figure", prepared=True)
    assert im.size == (512, 512)
    assert notes == []
    src = path.read_text()
    assert 'self.path == "/prepare"' in src and 'X-Prepared' in src


def test_tab_copy_is_photo_to_mesh_and_phone_exit_stays_clear():
    html = (ROOT / "static" / "index.html").read_text()
    sec = html[html.index('id="viewAi3d"'):]
    sec = sec[:sec.index("</main>")]
    js = (ROOT / "static" / "ai3d.js").read_text()
    hand = (ROOT / "static" / "handoff.js").read_text()
    css = (ROOT / "static" / "style.css").read_text()
    for text in (sec, js):
        assert not re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", text)
        assert not re.search(r"\b(kids?|child(ren)?|family|school|best|fastest|better than)\b", text, re.I)
        assert "AI figure" not in text
    assert "TripoSR" in sec and "Photo prep" in sec and "private" in sec.lower()
    assert "a3Cool" not in html
    assert "photo to mesh" in js.lower()
    assert 'fd.append("height_mm"' in js
    assert "ai3d" in hand and "Make a mesh first" in hand
    assert ".saveind{bottom:calc(var(--tabbar-h,64px) + 10px + env(safe-area-inset-bottom));left:auto;right:8px}" in css
    assert "a3handoff" in css
