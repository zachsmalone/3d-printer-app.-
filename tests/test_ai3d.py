"""2D->3D tab: engine-missing state, fake engine end-to-end, modes, AI label, cap/cooldown/testing mode, repair + export."""
import re, time, pathlib
import pytest, trimesh
from app import config
from app.services import ai3d
from app.core import ai3d_mesh
from tests.b1 import client, ADULT, SAMPLE

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    ai3d.reset()
    monkeypatch.setattr(config, "TESTING_MODE", False)
    monkeypatch.setattr(config, "AI3D_FAKE", True)
    monkeypatch.setattr(config, "AI3D_PRO_ONLY", False)
    monkeypatch.setattr(config, "AI3D_DAILY_CAP", 5)
    monkeypatch.setattr(config, "AI3D_COOLDOWN_MIN", 5)
    monkeypatch.setattr(config, "AI3D_COOLDOWN_STEP_MIN", 5)
    yield
    ai3d.reset()


def start(c, mode="figure", **extra):
    form = {"mode": mode, "photo_ack": "true", "title": "Tango", **extra}
    return c.post("/api/ai3d/jobs", files={"file": ("s.png", open(SAMPLE, "rb").read(), "image/png")}, data=form)


def wait(c, jid):
    for _ in range(200):
        j = c.get(f"/api/ai3d/jobs/{jid}").json()
        if j["state"] != "running":
            return j
        time.sleep(0.1)
    raise AssertionError("job never finished")


def make(c, mode="figure"):
    r = start(c, mode); assert r.status_code == 200, r.text
    j = wait(c, r.json()["job"]); assert j["state"] == "done", j
    return j["result"]


def test_engine_missing(monkeypatch):
    monkeypatch.setattr(config, "AI3D_FAKE", False); monkeypatch.setattr(config, "AI3D_URL", "")
    c = client(ADULT)
    s = c.get("/api/ai3d/status").json()
    assert s["engine"]["installed"] is False and s["engine"]["licence"].startswith("MIT")
    r = start(c); assert r.status_code == 503 and r.json()["detail"]["code"] == "engine_missing"


def test_engine_unreachable_reports_not_ready(monkeypatch):
    monkeypatch.setattr(config, "AI3D_FAKE", False); monkeypatch.setattr(config, "AI3D_URL", "http://127.0.0.1:9")
    s = client(ADULT).get("/api/ai3d/status").json()["engine"]
    assert s["installed"] is True and s["ready"] is False


@pytest.mark.parametrize("mode,h", [("figure", 80), ("bust", 60)])
def test_fake_end_to_end_label_private_watertight(mode, h):
    c = client(ADULT)
    res = make(c, mode)
    assert res["ai"] is True and res["ai_label"] == "AI-made"
    assert res["report"]["watertight"] is True and abs(res["report"]["height_mm"] - h) < 1
    bid = res["id"]
    hist = c.get("/api/builds").json()
    items = hist["builds"] if isinstance(hist, dict) else hist
    b = [x for x in items if x["id"] == bid][0]
    assert b["ai"] is True
    info = c.get(f"/api/export/{bid}").json()
    assert info["default_name"].startswith("Tango") and "K1" in info["default_name"] and "0.2mm" in info["default_name"]
    stl = c.get(info["downloads"]["stl"]); assert stl.status_code == 200
    m = trimesh.load(trimesh.util.wrap_as_stream(stl.content), file_type="stl")
    assert m.is_watertight
    # private: another account cannot see it
    assert client({"display_name": "Bo Other", "dob": "1980-01-01"}).get(f"/api/export/{bid}").status_code in (403, 404)


def test_bad_mode():
    assert start(client(ADULT), mode="statue").status_code == 400


def test_job_owner_only():
    r = start(client(ADULT)); jid = r.json()["job"]
    assert client({"display_name": "Bo Other", "dob": "1980-01-01"}).get(f"/api/ai3d/jobs/{jid}").status_code == 404


def test_cooldown_then_testing_mode_lifts(monkeypatch):
    c = client(ADULT); make(c)
    p = c.get("/api/ai3d/status").json()["plan"]
    assert p["allowed"] is False and p["reason"] == "cooldown" and 290 <= p["wait_s"] <= 300
    r = start(c); assert r.status_code == 429 and r.json()["detail"]["code"] == "cooldown"
    monkeypatch.setattr(config, "TESTING_MODE", True)
    assert c.get("/api/ai3d/status").json()["plan"]["testing_mode"] is True
    make(c); make(c)


def test_daily_cap(monkeypatch):
    monkeypatch.setattr(config, "AI3D_COOLDOWN_MIN", 0); monkeypatch.setattr(config, "AI3D_DAILY_CAP", 2)
    c = client(ADULT); make(c); make(c)
    r = start(c); assert r.status_code == 429 and r.json()["detail"]["code"] == "cap"


def test_default_cooldown_is_flat_5_min():
    import importlib, os
    assert os.environ.get("ZEIM_AI3D_COOLDOWN_STEP_MIN") is None
    src = (ROOT / "app/config.py").read_text()
    assert '_int("ZEIM_AI3D_COOLDOWN_STEP_MIN", 0)' in src and '_int("ZEIM_AI3D_COOLDOWN_MIN", 5)' in src


def test_title_field_wins_over_sample_name():
    c = client(ADULT)
    r = c.post("/api/ai3d/jobs", files={"file": ("sample.jpg", (ROOT / "static/sample.jpg").read_bytes(), "image/jpeg")},
               data={"mode": "bust", "photo_ack": "true", "title": "Tango"})
    assert r.status_code == 200, r.text
    assert wait(c, r.json()["job"])["result"]["title"] == "Tango"


def test_pro_only_and_paid_step(monkeypatch):
    monkeypatch.setattr(config, "AI3D_PRO_ONLY", True)
    c = client(ADULT)
    r = start(c); assert r.status_code == 403 and r.json()["detail"]["code"] == "pro"
    class A:  # a Pro account: 5 min, then +5 per paid model
        sid = "pro-sid"; user = {"plan": "pro"}
    assert ai3d.plan(A)["allowed"]
    ai3d.mark_done(A); assert ai3d.plan(A)["cooldown_min"] == 10
    ai3d.mark_done(A); assert ai3d.plan(A)["cooldown_min"] == 15


def test_mesh_finish_repairs_open_mesh():
    raw = trimesh.creation.icosphere(3); raw.faces = raw.faces[:-30]   # holes
    model, rep = ai3d_mesh.finish(raw, "figure")
    v, f = model.solid(); assert trimesh.Trimesh(v, f).is_watertight and model.info["ai"] is True


def test_static_tab_and_copy():
    html = (ROOT / "static/index.html").read_text()
    assert 'data-view="ai3d"' in html and 'id="viewAi3d"' in html and 'data-zt="ai3d"' in html
    sec = html[html.index('id="viewAi3d"'):]; sec = sec[:sec.index("</main>")]
    js = (ROOT / "static/ai3d.js").read_text()
    for text in (sec, js):
        assert not re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", text), "no emoji"
        assert not re.search(r"\b(kids?|child(ren)?|family|school|best|fastest|better than)\b", text, re.I)
    assert "private" in sec.lower()


def test_ui_tab_in_a_real_browser():
    import os, subprocess, sys
    from tests.test_b1_ui import _spawn
    fake = {"ZEIM_AI3D_FAKE": "1", "ZEIM_TESTING_MODE": "0"}
    p1, u1 = _spawn("local", fake); p3, u3 = _spawn("local", fake); p2, u2 = _spawn("local", {"ZEIM_AI3D_URL": "", "ZEIM_AI3D_FAKE": "0"})
    try:
        shots = os.environ.get("ZEIM_SHOTS", "")
        r = subprocess.run([sys.executable, str(ROOT / "tests/ui_ai3d.py"), u1, u3, u2, shots], cwd=ROOT, capture_output=True, text=True, timeout=500)
        assert r.returncode == 0 and "FAIL" not in r.stdout and "PASS chrome" in r.stdout, r.stdout + r.stderr
    finally:
        for p in (p1, p2, p3):
            p.terminate(); p.wait(10)
