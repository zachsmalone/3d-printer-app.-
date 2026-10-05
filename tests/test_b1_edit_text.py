"""Safety (HIGH): free text in Edit's emboss/deboss step goes through length cap + language/contact filter on create,
later edits and replays; project titles never reach exported files."""
import io, json, os, sys, time, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest, trimesh
from app import config
from app.community import safety
from app.services import editproj
from app.services.history import store
from tests.b1 import *


def new_edit(c, title="My part"):
    r = c.post("/api/edit/new", files={"file": ("b.stl", box_stl(), "application/octet-stream")}, data={"title": title}); assert r.status_code == 200, r.text
    return r.json()["id"]


def text_op(c, bid, text, **kw):
    return c.post(f"/api/edit/{bid}/op", json={"op": "text", "params": {"text": text, "height": 5, "depth": 1, "mode": "emboss", "face": "top", **kw}})


BAD = ["sh1t", "call me 312 555 0199", "mail me@example.com", "visit www.example.org", "http://x.example/a"]


@pytest.mark.parametrize("txt", BAD)
def test_blocked_text_is_refused_and_never_stored(txt):
    c = client(); bid = new_edit(c)
    r = text_op(c, bid, txt)
    assert r.status_code == 422 and r.json()["code"] in ("language_blocked", "contact_blocked") and "message" in r.json(), (txt, r.text)
    meta = store.get(bid)
    assert meta["ops"] == [] and meta["head"] == 0 and txt not in json.dumps(meta)
    assert txt not in c.get(f"/api/builds/{bid}").text


def test_good_text_works_and_long_or_odd_text_is_capped():
    c = client(); bid = new_edit(c)
    assert text_op(c, bid, "ZEIM 3D").status_code == 200
    assert store.get(bid)["ops"][0]["params"]["text"] == "ZEIM 3D"
    t0 = time.time()
    for bad in ("x" * 61, "y" * 200_000, "ab\x00cd"):
        r = text_op(c, bid, bad); assert r.status_code in (400, 413, 422), bad[:10]
    assert time.time() - t0 < 2
    assert c.post(f"/api/edit/{bid}/op", json={"op": "text", "params": {"text": {"a": 1}}}).status_code in (400, 422)
    assert c.post(f"/api/edit/{bid}/op", json={"op": "text", "params": {"text": "ok", "font": "f" * 500}}).status_code == 400
    assert len(store.get(bid)["ops"]) == 1


def test_text_added_to_an_existing_project_and_from_a_studio_build_is_checked_too():
    c = client()
    b = photo_build(c)
    e = c.post("/api/edit/new", data={"from_build": b}); assert e.status_code == 200, e.text
    bid = e.json()["id"]
    assert text_op(c, bid, "sh1t").status_code == 422
    r = text_op(c, bid, "Hello"); assert r.status_code == 422 and "float free" in r.text        # top of a relief is bumpy: raised text touches nothing there, so it is refused (QA-6) - not a filter problem
    assert text_op(c, bid, "Hello", face="bottom").status_code == 200                          # the flat underside takes it
    # later edit of the same project: undo, then a second bad step is still refused, history intact
    c.post(f"/api/edit/{bid}/undo")
    assert text_op(c, bid, "me@example.com").status_code == 422
    assert store.get(bid)["head"] == 0


def test_replay_skips_a_stored_text_step_that_no_longer_passes():
    c = client(); bid = new_edit(c)
    assert text_op(c, bid, "Hello").status_code == 200
    meta = store.get(bid); meta["ops"][0]["params"]["text"] = "sh1t"; store.save(meta)       # simulates data stored before the filter existed
    editproj._STATES.pop(bid, None); store.cache.pop(bid, None)
    m_plain = editproj.mesh_at(bid, store.get(bid), head=0)
    m_replayed = editproj.mesh_at(bid, store.get(bid))
    assert len(m_replayed.faces) == len(m_plain.faces)                 # the bad text step was skipped, not rendered
    assert c.get(f"/api/edit/{bid}").status_code in (200, 404)         # route still works


def test_project_title_is_gated_and_not_written_into_exports():
    c = client()
    assert c.post("/api/edit/new", files={"file": ("b.stl", box_stl(), "application/octet-stream")}, data={"title": "sh1t"}).status_code == 422
    bid = new_edit(c, title="Zoe Private Title")
    for ext in ("3mf", "obj", "stl"):
        data = c.get(f"/api/download/{bid}/{ext}").content
        if ext == "3mf":
            data = b"".join(zipfile.ZipFile(io.BytesIO(data)).read(n) for n in zipfile.ZipFile(io.BytesIO(data)).namelist())
        assert b"Zoe Private Title" not in data and b"Zoe" not in data
    assert b'name="model"' in zipfile.ZipFile(io.BytesIO(c.get(f"/api/download/{bid}/3mf").content)).read("3D/3dmodel.model")


def test_studio_build_titles_are_gated():
    c = client()
    assert gen(c, title="sh1t").status_code == 422
    assert gen(c, title="Nice lamp").status_code == 200


def test_obfuscated_email_in_text_step_is_blocked():
    c = client(); bid = new_edit(c)
    assert text_op(c, bid, "name at gmail dot com").status_code == 422
