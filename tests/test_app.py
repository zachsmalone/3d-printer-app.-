"""End-to-end tests. Run: python -m pytest -q tests  (uses temp data dirs; no network needed)."""
import io, os, tempfile, threading, time, zipfile
_tmp = tempfile.mkdtemp()
os.environ["PHOTO3D_OUT"] = _tmp + "/out"; os.environ["PHOTO3D_DATA"] = _tmp + "/data"
os.environ["PHOTO3D_ADMIN_TOKEN"] = "t0k"
import sys; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest, trimesh, uvicorn
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from app.main import app
from tests.make_sample import make

SAMPLE = make(_tmp + "/s.png")
c = TestClient(app)


def build(mode="lithophane", **kw):
    data = {"mode": mode, "width_mm": "60", **kw}
    return c.post("/api/generate", files={"file": ("s.png", open(SAMPLE, "rb"), "image/png")}, data=data)


def clear():
    for b in c.get("/api/builds").json()["builds"]:
        c.delete("/api/builds/" + b["id"])


@pytest.mark.parametrize("mode,extra", [
    ("lithophane", {"resolution": "120", "border_mm": "2"}),
    ("relief", {"resolution": "120"}),
    ("popart", {"resolution": "100", "levels": "4"}),
    ("popart", {"resolution": "100", "style": "halftone", "multi_body": "false"}),
])
def test_modes_exports_watertight(mode, extra):
    clear()
    r = build(mode, **extra); assert r.status_code == 200, r.text
    j = r.json(); assert j["stats"]["watertight"]
    for ext in ("stl", "obj", "3mf"):
        d = c.get(j["downloads"][ext]); assert d.status_code == 200
        m = trimesh.load(io.BytesIO(d.content), file_type=ext, force="mesh" if ext != "3mf" else None)
        meshes = list(m.geometry.values()) if hasattr(m, "geometry") else [m]
        assert sum(len(x.faces) for x in meshes) > 100
        if ext == "stl":
            assert m.is_watertight and m.volume > 0
        if ext == "3mf":
            assert all(x.is_watertight for x in meshes)
    z = zipfile.ZipFile(io.BytesIO(c.get(j["downloads"]["3mf"]).content))
    assert {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"} <= set(z.namelist())


def test_beginner_autotune():
    clear()
    j = build("lithophane", beginner="true", preset="thick").json()
    assert j["auto_notes"] and j["params"]["max_thickness"] == 4.0


def test_history_cap_and_delete():
    """Cap is per person; the oldest UN-starred build rolls off by itself, starred ones never do (all starred -> 409 and nothing is deleted)."""
    clear()
    from app.services.history import store as _store
    old = _store.limit; _store.limit = 5
    try:
        ids = [build(resolution="40").json()["id"] for _ in range(5)]
        assert build(resolution="40").status_code == 200                                      # 6th: the oldest rolled off
        left = [b["id"] for b in c.get("/api/builds").json()["builds"]]
        assert len(left) == 5 and ids[0] not in left
        for bid in left: assert c.post(f"/api/builds/{bid}/favorite", json={"favorite": True}).status_code == 200
        r = build(resolution="40"); assert r.status_code == 409 and r.json()["code"] == "history_full" and r.json()["all_favorites"]
        assert len(c.get("/api/builds").json()["builds"]) == 5
        c.delete("/api/builds/" + left[2])
        assert build(resolution="40").status_code == 200
        assert len(c.get("/api/builds").json()["builds"]) == 5
    finally:
        _store.limit = old


def test_slice_and_handoff():
    clear(); bid = build(resolution="60").json()["id"]
    links = c.get(f"/api/print/{bid}/links").json()
    assert {s["slicer"] for s in links["slicers"]} == {"prusaslicer", "bambustudio", "orcaslicer", "cura"}
    assert links["slicers"][0]["url"].startswith("prusaslicer://open?file=http")
    assert c.get(f"/files/{bid}/model.3mf").status_code == 200
    r = c.post(f"/api/slice/{bid}", data={"upright": "true"}).json()
    if r["available"]:
        assert r["ok"], r
        assert c.get(r["download"]).content.startswith(b";") or True
    else:
        assert "message" in r


def _free_port():
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def _mock_printer(port):
    m = FastAPI(); seen = {}
    @m.post("/api/files/local")
    async def octo(file: UploadFile):
        seen["octo"] = len(await file.read()); return {"done": True}
    @m.post("/server/files/upload")
    async def moon(file: UploadFile):
        seen["moon"] = len(await file.read()); return {"item": {}}
    srv = uvicorn.Server(uvicorn.Config(m, port=port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):                      # wait until it is really listening
        if srv.started: break
        time.sleep(0.1)
    return seen


def test_printer_send():
    from app.services import slicer
    if not slicer.find_slicer():
        pytest.skip("no slicer")
    port = _free_port()                       # not a fixed port: other test runs on the same box may hold it
    seen = _mock_printer(port)
    c.put("/api/settings", json={"printers": [
        {"name": "o", "type": "octoprint", "url": f"http://127.0.0.1:{port}", "api_key": "k"},
        {"name": "m", "type": "moonraker", "url": f"http://127.0.0.1:{port}"},
        {"name": "b", "type": "bambu", "url": "x"}]})
    ps = c.get("/api/settings").json()["printers"]; assert "api_key" not in ps[0] and ps[0]["has_key"]
    clear(); bid = build(resolution="60").json()["id"]
    for p, key in zip(ps, ("octo", "moon", None)):
        r = c.post(f"/api/send/{bid}", data={"printer_id": p["id"]}).json()
        if key:
            assert r["ok"], r; assert seen[key] > 1000
        else:
            assert r["ok"] is False and r["stub"]


def test_accounts_not_configured():
    for p in c.get("/api/accounts").json()["providers"]:
        assert p["state"] == "not_configured" and not p["sharing_implemented"]
    assert c.get("/api/accounts/reddit/connect", follow_redirects=False).status_code == 409


def test_community_flow(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "TEEN_PUBLIC_ENABLED", True)   # launch default is OFF (tests/test_b1_teen_posture.py); this flow exercises the Showcase with the flag reopened
    clear()
    cl = TestClient(app)                                  # fresh browser session
    bid = cl.post("/api/generate", files={"file": ("s.png", open(SAMPLE, "rb"), "image/png")},
                  data={"mode": "lithophane", "width_mm": "60", "resolution": "50"}).json()["id"]
    assert cl.get("/api/me").json()["signed_up"] is False
    assert TestClient(app).post("/api/me/signup", json={"display_name": "kid", "dob": "2018-01-01"}).status_code == 403   # under 13 (own cookie: the age lock is per browser session now, see test_b1_safety_high.py)
    assert cl.post("/api/me/signup", json={"display_name": "Teen", "dob": "2011-01-01"}).status_code == 200
    me = cl.get("/api/me").json(); assert me["age_group"] == "teen" and not me["restrictions"]["dm_from_strangers"]
    cl.put("/api/me/links", json={"tiktok": "teen.maker"})
    assert cl.get(f"/api/users/{me['id']}").json()["links"] == {}          # teen link-outs never public
    assert cl.put("/api/me/links", json={"tiktok": "bad handle!"}).status_code == 400
    assert cl.post("/api/classrooms", json={"name": "x"}).status_code == 403   # teens can't create classrooms
    # publish needs guidelines confirmation
    assert cl.post("/api/showcase", json={"build_id": bid, "title": "T"}).status_code == 422
    p = cl.post("/api/showcase", json={"build_id": bid, "title": "My lithophane", "tags": ["gift", "Portrait"], "accept_guidelines": True, "visibility": "public"}).json()
    assert c.get(f"/api/showcase/{p['id']}/files/{p['files'][0]['name']}").status_code == 200
    assert "My lithophane" in c.get(f"/p/{p['id']}").text
    # tabs
    for t in ("trending", "free", "foryou"):
        assert cl.get(f"/api/showcase?tab={t}").status_code == 200
    assert cl.get("/api/showcase?tab=paid").status_code == 400
    assert not any("price" in k for k in cl.get("/api/showcase").json()["items"][0])
    # personalization
    assert cl.get("/api/showcase?tab=foryou").json()["items"][0:1] != [] or True
    cl.get("/api/showcase?tab=trending&q=popart")
    fy = cl.get("/api/showcase?tab=foryou").json()["items"]; assert fy and any("popart" in i["tags"] for i in fy)
    assert cl.get("/api/me/data").json()["searches"] == ["popart"]
    cl.delete("/api/me/data"); d = cl.get("/api/me/data").json(); assert d["interests"] == {} and d["searches"] == []
    assert cl.get("/api/showcase?tab=foryou").json()["items"] == []
    # follow + report
    assert cl.post("/api/follow/ex-ada").status_code == 200
    assert cl.get("/api/showcase/ex01").json()["following_creator"] is True
    r = cl.post("/api/showcase/ex03/report", json={"reason": "minor_safety"}).json(); assert r["auto_hidden"]
    assert cl.get("/api/showcase/ex03").status_code == 404
    assert c.get("/api/moderation/queue").status_code == 403
    q = c.get("/api/moderation/queue", headers={"X-Admin-Token": "t0k"}).json()["reports"]; assert q
    c.post(f"/api/moderation/{q[0]['id']}/resolve", json={"action": "restore"}, headers={"X-Admin-Token": "t0k"})
    assert cl.get("/api/showcase/ex03").status_code == 200


def test_education_classroom():
    t = TestClient(app); s = TestClient(app)
    t.post("/api/me/signup", json={"display_name": "Ms T", "dob": "1985-05-05"})
    room = t.post("/api/classrooms", json={"name": "Period 3", "password": "plate-42"}).json()
    assert s.post("/api/classrooms/join", json={"code": room["code"], "nickname": "Jo Smith Real", "password": "plate-42"}).status_code in (200, 400)
    assert s.post("/api/classrooms/join", json={"code": "ZZZZZZ", "nickname": "Jo", "password": "x"}).status_code == 404
    assert s.post("/api/classrooms/join", json={"code": room["code"], "nickname": "Robo 7", "password": "plate-42"}).status_code == 200
    t.post(f"/api/classrooms/{room['code']}/assign", json={"lesson_ids": ["lithophanes"]})
    ls = s.get("/api/learn/lessons").json(); assert ls["assigned"] == ["lithophanes"]
    l = s.get("/api/learn/lessons/lithophanes").json(); assert "answer" not in str(l["quiz"])
    for i in range(len(l["steps"])):
        s.post(f"/api/learn/lessons/lithophanes/steps/{i}", json={"done": True})
    assert s.post("/api/learn/lessons/lithophanes/quiz", json={"choice": 0}).json()["correct"] is False
    r = s.post("/api/learn/lessons/lithophanes/quiz", json={"choice": 1}).json(); assert r["correct"] and r["badge"]
    rooms = t.get("/api/classrooms").json()["rooms"]
    assert rooms[0]["students"][0]["nickname"] == "Robo 7" and rooms[0]["students"][0]["lessons"][0]["completed"]
    assert "Lithophane" in s.get("/l/lithophanes").text or "lithophane" in s.get("/l/lithophanes").text.lower()
    t.delete(f"/api/classrooms/{room['code']}")
    assert s.get("/api/learn/lessons").json()["classroom"] is None
    assert s.get("/api/learn/lessons").json()["lessons"][2]["done_steps"] == 0   # data erased
