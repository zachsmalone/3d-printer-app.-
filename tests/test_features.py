"""Edit workspace, privacy, likes/trending, classrooms, language filter. Run with the rest: python -m pytest -q tests"""
import io, os, shutil, tempfile, zipfile
_tmp = tempfile.mkdtemp()
os.environ.setdefault("PHOTO3D_OUT", _tmp + "/out"); os.environ.setdefault("PHOTO3D_DATA", _tmp + "/data")
os.environ.setdefault("PHOTO3D_ADMIN_TOKEN", "t0k")
import sys; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import numpy as np, pytest, trimesh
from fastapi.testclient import TestClient
from app.main import app
from app.community import safety
from app.community.catalog import trending_score
from tests.make_sample import make

SAMPLE = make(_tmp + "/s2.png")
ADULT = {"display_name": "Ada Adult", "dob": "1985-05-05"}
TEEN = {"display_name": "Tess Teen", "dob": "2011-01-01"}


def client(user=None):
    c = TestClient(app)
    if user:
        assert c.post("/api/me/signup", json=user).status_code == 200
    return c


def stl(m): return m.export(file_type="stl")
def sphere(r=15): return stl(trimesh.creation.icosphere(3, r))
def box(x=20, y=20, z=10): return stl(trimesh.creation.box([x, y, z]))


def clear(c):
    for b in c.get("/api/builds").json()["builds"]:
        c.delete("/api/builds/" + b["id"])


def new_edit(c, data=None, name="part.stl", **form):
    r = c.post("/api/edit/new", files={"file": (name, data or box(), "application/octet-stream")}, data=form)
    assert r.status_code == 200, r.text
    return r.json()


def op(c, bid, name, **params):
    return c.post(f"/api/edit/{bid}/op", json={"op": name, "params": params})


def photo_build(c, **extra):
    r = c.post("/api/generate", files={"file": ("s.png", open(SAMPLE, "rb"), "image/png")},
               data={"mode": "relief", "width_mm": "50", "resolution": "40", **extra})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ===================================================================== EDIT WORKSPACE
def test_edit_upload_formats_and_original_kept():
    c = client(); clear(c)
    m = trimesh.creation.box([20, 30, 10])
    obj = m.export(file_type="obj").encode() if isinstance(m.export(file_type="obj"), str) else m.export(file_type="obj")
    t3 = m.export(file_type="3mf")
    for name, data in (("a.stl", stl(m)), ("b.obj", obj), ("c.3mf", t3)):
        clear(c)
        j = new_edit(c, data, name)
        assert j["kind"] == "edit" and j["analysis"]["watertight"]
        assert np.allclose(sorted(j["analysis"]["size_mm"]), [10, 20, 30], atol=0.01), (name, j["analysis"]["size_mm"])
        assert c.get(j["original"]).content == data                      # byte-identical original
        op(c, j["id"], "scale", factor=2)
        assert c.get(j["original"]).content == data                      # still untouched after edits


def test_edit_validation_and_limits(monkeypatch):
    c = client(); clear(c)
    f = lambda n, d: c.post("/api/edit/new", files={"file": (n, d)})
    assert f("x.exe", b"MZ....").status_code == 415
    assert f("x.stl", b"this is not an stl at all" * 10).status_code == 415            # right ext, wrong bytes
    assert f("x.3mf", b"PK-not-really-a-zip").status_code == 415
    assert f("x.obj", bytes(range(256)) * 4).status_code == 415
    assert f("empty.stl", b"").status_code == 400
    assert c.post("/api/edit/new").status_code == 400
    from app.services import editproj
    monkeypatch.setattr(editproj, "MAX_UPLOAD_EDIT", 2000)
    assert f("big.stl", sphere()).status_code == 413
    assert c.get("/api/edit/capabilities").json()["max_upload_mb"] >= 0
    assert len(c.get("/api/builds").json()["builds"]) == 0                           # failures create nothing


def test_edit_units_import():
    c = client(); clear(c)
    j = new_edit(c, box(1, 2, 1), "inch.stl", units="in")
    assert np.allclose(sorted(j["analysis"]["size_mm"]), [25.4, 25.4, 50.8], atol=0.05)
    assert j["ops"][0]["label"].startswith("Units")


def test_edit_transform_ops_and_undo_redo():
    c = client(); clear(c)
    j = new_edit(c, box(40, 20, 10)); bid = j["id"]
    j = op(c, bid, "scale", sx=2, sy=1, sz=3).json()
    assert np.allclose(j["analysis"]["size_mm"], [80, 20, 30], atol=0.01)
    j = op(c, bid, "rotate", rz=90).json(); assert np.allclose(j["analysis"]["size_mm"], [20, 80, 30], atol=0.01)
    j = op(c, bid, "translate", dx=5, dy=0, dz=100).json(); assert abs(j["analysis"]["min_mm"][2] - 95) < 0.01
    j = op(c, bid, "place", drop=True, center_xy=True).json()
    assert abs(j["analysis"]["min_mm"][2]) < 1e-6 and abs(j["analysis"]["center_mm"][0]) < 1e-6
    j = op(c, bid, "mirror", axis="x").json(); assert j["analysis"]["watertight"] and j["analysis"]["volume_mm3"] > 0
    assert len(j["ops"]) == 5 and j["head"] == 5
    # undo / redo / goto
    j = c.post(f"/api/edit/{bid}/undo").json(); assert j["head"] == 4 and j["can_redo"]
    j = c.post(f"/api/edit/{bid}/goto", json={"head": 0}).json()
    assert np.allclose(sorted(j["analysis"]["size_mm"]), [10, 20, 40], atol=0.01) and not j["can_undo"]
    j = c.post(f"/api/edit/{bid}/redo").json(); assert j["head"] == 1
    j = op(c, bid, "translate", dx=1).json()                  # new op discards the redo tail
    assert len(j["ops"]) == 2 and not j["can_redo"]
    assert c.post(f"/api/edit/{bid}/undo").status_code == 200 and c.post(f"/api/edit/{bid}/undo").status_code == 200
    assert c.post(f"/api/edit/{bid}/undo").status_code == 422
    assert op(c, bid, "scale", factor=-1).status_code == 422 and op(c, bid, "bogus").status_code == 400
    assert op(c, bid, "scale", factor="abc").status_code == 422


def test_edit_exports_roundtrip_and_replay_after_restart():
    c = client(); clear(c)
    bid = new_edit(c, sphere())["id"]; op(c, bid, "scale", factor=2)
    for ext in ("stl", "obj", "3mf"):
        d = c.get(f"/api/download/{bid}/{ext}"); assert d.status_code == 200
        m = trimesh.load(io.BytesIO(d.content), file_type=ext, force="mesh")
        assert np.allclose(m.extents, 60, atol=1.0), (ext, m.extents)
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/download/{bid}/3mf").content)); assert "3D/3dmodel.model" in z.namelist()
    from app.services import editproj
    editproj._STATES.clear(); editproj._BASES.clear()          # simulate server restart: replay from original + ops
    assert np.allclose(c.get(f"/api/edit/{bid}").json()["analysis"]["size_mm"], 60, atol=1.0)
    op(c, bid, "translate", dz=10)                              # export regenerates (stale files not served)
    m = trimesh.load(io.BytesIO(c.get(f"/files/{bid}/model.stl").content), file_type="stl")
    assert abs(m.bounds[0][2] - (-15 + 10)) < 1.0


def test_edit_cut_hollow_base_boolean_text():
    c = client(); clear(c)
    bid = new_edit(c, sphere(20))["id"]
    v0 = c.get(f"/api/edit/{bid}").json()["analysis"]["volume_mm3"]
    j = op(c, bid, "cut", axis="z", position=0, keep="above").json()
    assert j["analysis"]["watertight"] and 0.45 * v0 < j["analysis"]["volume_mm3"] < 0.55 * v0
    c.post(f"/api/edit/{bid}/goto", json={"head": 0})
    j = op(c, bid, "cut", axis="z", position=0, keep="both", gap=5).json()
    assert j["analysis"]["components"] == 2 and abs(j["analysis"]["volume_mm3"] - v0) / v0 < 0.02
    c.post(f"/api/edit/{bid}/goto", json={"head": 0})
    j = op(c, bid, "hollow", wall=2, drain_diameter=4).json()
    assert j["analysis"]["watertight"] and j["analysis"]["volume_mm3"] < 0.5 * v0
    assert op(c, bid, "hollow", wall=30).status_code == 422                       # too thick → clear error
    c.post(f"/api/edit/{bid}/goto", json={"head": 0})
    j = op(c, bid, "base", style="outline", margin=3, thickness=2).json()
    assert j["analysis"]["watertight"] and j["analysis"]["size_mm"][2] > 41.9 and abs(j["analysis"]["min_mm"][2]) < 1e-6
    c.post(f"/api/edit/{bid}/goto", json={"head": 0})
    j = op(c, bid, "boolean", kind="difference", primitive={"type": "cylinder", "diameter": 10, "height": 80, "position": [0, 0, 0]}).json()
    assert j["analysis"]["watertight"] and j["analysis"]["volume_mm3"] < v0 - 3000
    j = op(c, bid, "boolean", kind="union", primitive={"type": "box", "size": [60, 8, 8], "position": [0, 0, 0]}).json()
    assert j["analysis"]["size_mm"][0] >= 59.9
    j = op(c, bid, "boolean", kind="union", primitive={"type": "sphere", "diameter": 10, "position": [0, 0, 30]}).json()
    assert j["analysis"]["watertight"]
    assert op(c, bid, "boolean", kind="xor", primitive={"type": "box"}).status_code == 422
    c.post(f"/api/edit/{bid}/goto", json={"head": 0})
    j = op(c, bid, "text", text="ZEIM", height=6, depth=1.5, mode="emboss", face="top").json()
    assert j["analysis"]["watertight"] and j["analysis"]["max_mm"][2] > 20 + 1.0
    v1 = j["analysis"]["volume_mm3"]
    j = op(c, bid, "text", text="Hi", height=5, depth=1, mode="deboss", face="front").json()
    assert j["analysis"]["volume_mm3"] < v1 and j["analysis"]["watertight"]
    assert op(c, bid, "text", text="").status_code == 422


def test_edit_repair_and_simplify():
    c = client(); clear(c)
    s = trimesh.creation.icosphere(3, 20)
    broken = trimesh.Trimesh(s.vertices, np.delete(s.faces, range(0, 1000, 9), axis=0), process=False)
    j = new_edit(c, stl(broken)); bid = j["id"]
    assert j["analysis"]["watertight"] is False and j["analysis"]["boundary_edges"] > 0
    j = op(c, bid, "repair").json()
    assert j["analysis"]["watertight"] and j["report"]["after"]["watertight"] and j["report"]["steps"]
    n = j["analysis"]["triangles"]
    j = op(c, bid, "simplify", keep_ratio=0.25).json()
    assert j["analysis"]["triangles"] < 0.4 * n and j["analysis"]["watertight"]
    # inverted normals are fixed
    inv = trimesh.creation.box([10, 10, 10]); inv.invert()
    j = new_edit(c, stl(inv), "inv.stl"); j = op(c, j["id"], "repair").json()
    assert j["analysis"]["volume_mm3"] > 0 and not j["analysis"]["inverted"]


def test_edit_from_build_photo_and_history_cap():
    c = client(); clear(c)
    b = photo_build(c)
    j = c.post("/api/edit/new", data={"from_build": b, "title": "from photo"}).json()
    assert j["base"]["type"] == "build" and j["analysis"]["watertight"] and len(c.get("/api/builds").json()["builds"]) == 2
    # a photo straight into the editor (lithophane base) and then edit it
    r = c.post("/api/edit/new", files={"file": ("p.png", open(SAMPLE, "rb"), "image/png")},
               data={"photo_mode": "lithophane", "width_mm": "60", "auto_delete_oldest": "true"})
    assert r.status_code == 200 and r.json()["base"]["type"] == "photo"
    pid = r.json()["id"]; assert op(c, pid, "base", style="rect", margin=2, thickness=2).status_code == 200
    # edit projects count toward the cap (oldest un-starred rolls off; all starred -> 409)
    from app.services.history import store as _st
    old = _st.limit; _st.limit = 5
    try:
        clear(c)
        for _ in range(5): new_edit(c)
        assert c.post("/api/edit/new", files={"file": ("a.stl", box())}).status_code == 200
        assert len(c.get("/api/builds").json()["builds"]) == 5
        for b in c.get("/api/builds").json()["builds"]: c.post(f"/api/builds/{b['id']}/favorite", json={"favorite": True})
        r = c.post("/api/edit/new", files={"file": ("a.stl", box())}); assert r.status_code == 409 and r.json()["code"] == "history_full"
        c.delete("/api/builds/" + c.get("/api/builds").json()["builds"][0]["id"])
        assert c.post("/api/edit/new", files={"file": ("a.stl", box())}).status_code == 200
    finally:
        _st.limit = old
    assert len(c.get("/api/builds").json()["builds"]) == 5
    assert c.get("/api/builds").json()["builds"][0]["kind"] in ("edit", "photo")


def test_edit_slice_print_and_listing():
    c = client(); clear(c)
    bid = new_edit(c, sphere())["id"]; op(c, bid, "base", style="round", margin=2, thickness=2)
    links = c.get(f"/api/print/{bid}/links").json()
    assert links["slicers"][0]["url"].startswith("prusaslicer://open?file=http") and "/f/" in links["slicers"][0]["file_url"]
    anon = TestClient(app)
    assert anon.get(links["slicers"][0]["file_url"].replace("http://testserver", "")).status_code == 200   # signed link works without cookie
    r = c.post(f"/api/slice/{bid}").json()
    if r["available"]:
        assert r["ok"], r
    assert c.get("/api/builds").json()["builds"][0]["id"] == bid
    assert c.get(f"/api/builds/{bid}").json()["kind"] == "edit"


# ===================================================================== PRIVACY
def test_builds_private_by_default_and_visibility_changes_apply_immediately():
    a, other = client(ADULT), client()
    clear(a); bid = photo_build(a)
    assert a.get("/api/builds").json()["builds"][0]["visibility"] == "private"
    for url in (f"/files/{bid}/model.stl", f"/api/download/{bid}/stl", f"/api/builds/{bid}", f"/files/{bid}/thumb.png"):
        assert other.get(url).status_code == 404 and a.get(url).status_code == 200, url
    assert other.delete(f"/api/builds/{bid}").status_code == 404
    assert other.post(f"/api/slice/{bid}").status_code == 404 and other.get(f"/api/print/{bid}/links").status_code == 404
    assert other.get("/api/builds").json()["builds"] == []
    # signed token link only for that build, tampering fails
    tok = a.get(f"/api/print/{bid}/links").json()["slicers"][0]["file_url"].replace("http://testserver", "")
    assert other.get(tok).status_code == 200
    assert other.get(tok.replace(bid, "000000000000")).status_code == 404 and other.get(tok[:-8] + "x/model.3mf").status_code == 404
    # public → immediately visible; back to private → immediately gone
    assert a.put(f"/api/builds/{bid}/visibility", json={"visibility": "public"}).status_code == 200
    assert other.get(f"/files/{bid}/model.stl").status_code == 200
    assert a.put(f"/api/builds/{bid}/visibility", json={"visibility": "private"}).status_code == 200
    assert other.get(f"/files/{bid}/model.stl").status_code == 404
    # anonymous visitor cannot go beyond private
    anon = client(); ab = photo_build(anon)
    assert anon.put(f"/api/builds/{ab}/visibility", json={"visibility": "public"}).status_code == 403
    assert a.put(f"/api/builds/{bid}/visibility", json={"visibility": "bogus"}).status_code == 400
    assert other.put(f"/api/builds/{bid}/visibility", json={"visibility": "public"}).status_code == 404
    # edit projects too
    e = new_edit(a)["id"]
    assert other.get(f"/api/edit/{e}").status_code == 404 and other.post(f"/api/edit/{e}/op", json={"op": "place"}).status_code == 404
    assert other.get(f"/api/edit/{e}/original").status_code == 404


def test_followers_only_and_social_opt_out():
    a, b, c3 = client(ADULT), client({"display_name": "Bob", "dob": "1990-01-01"}), client({"display_name": "Cy", "dob": "1991-01-01"})
    aid = a.get("/api/me").json()["id"]; clear(a)
    bid = photo_build(a)
    assert a.put(f"/api/builds/{bid}/visibility", json={"visibility": "followers"}).status_code == 200
    assert b.get(f"/files/{bid}/model.stl").status_code == 404                       # not following yet
    assert b.post(f"/api/follow/{aid}").status_code == 200
    assert b.get(f"/files/{bid}/model.stl").status_code == 200 and c3.get(f"/files/{bid}/model.stl").status_code == 404
    assert a.get("/api/me/followers").json()["followers"][0]["display_name"].startswith("@")   # @username, never the display name
    assert b.delete(f"/api/follow/{aid}").status_code == 200
    assert b.get(f"/files/{bid}/model.stl").status_code == 404                       # unfollow → immediate
    b.post(f"/api/follow/{aid}")
    # owner opts out of social: followers removed, followers-only collapses to private, can't be followed
    assert a.put("/api/me/privacy", json={"social": "off"}).status_code == 200
    assert b.get(f"/files/{bid}/model.stl").status_code == 404
    assert a.get("/api/me/followers").json() == {"enabled": False, "followers": []}
    assert b.post(f"/api/follow/{aid}").status_code == 404
    prof = b.get(f"/api/users/{aid}").json(); assert prof["followers"] is None and prof["can_follow"] is False
    assert a.put(f"/api/builds/{bid}/visibility", json={"visibility": "followers"}).status_code == 403
    assert a.post(f"/api/follow/{c3.get('/api/me').json()['id']}").status_code == 403    # opted-out user can't follow either
    assert a.get("/api/me").json()["following"] == []
    a.put("/api/me/privacy", json={"social": "on"})
    # private profile: 404 for others (API + page), visible to owner; follow refused
    a.put("/api/me/privacy", json={"profile": "private"})
    assert c3.get(f"/api/users/{aid}").status_code == 404 and c3.get(f"/u/{aid}").status_code == 404
    assert a.get(f"/api/users/{aid}").status_code == 200 and c3.post(f"/api/follow/{aid}").status_code == 404
    a.put("/api/me/privacy", json={"profile": "public"})
    assert c3.get(f"/api/users/{aid}").status_code == 200


def test_teen_defaults_private():
    t = client(TEEN)
    me = t.get("/api/me").json()
    assert me["privacy"]["profile"] == "private" and me["privacy"]["default_visibility"] == "private"
    assert t.put("/api/me/privacy", json={"default_visibility": "public"}).status_code == 403
    assert client().get(f"/api/users/{me['id']}").status_code == 404
    tb = photo_build(t); assert t.get("/api/builds").json()["builds"][-1]["visibility"] == "private"


def publish(c, build, vis=None, title="Moon lamp", **kw):
    body = {"build_id": build, "title": title, "tags": ["lamp"], "accept_guidelines": True, **kw}
    if vis: body["visibility"] = vis
    return c.post("/api/showcase", json=body)


def test_showcase_visibility_everywhere():
    o, other = client(ADULT), client({"display_name": "Visitor", "dob": "1990-01-01"})
    clear(o); b = photo_build(o)
    assert client().post("/api/showcase", json={"build_id": b, "title": "x", "accept_guidelines": True}).status_code in (401, 403, 422)
    assert other.post("/api/showcase", json={"build_id": b, "title": "steal", "accept_guidelines": True}).status_code == 422   # not their build
    p = publish(o, b, title="Zebra moonlamp").json()
    assert p["visibility"] == "private"                                              # default private
    pid, fname = p["id"], p["files"][0]["name"]
    def seen_by(cl):
        return {"api": cl.get(f"/api/showcase/{pid}").status_code, "page": cl.get(f"/p/{pid}").status_code,
                "thumb": cl.get(f"/api/showcase/{pid}/thumb").status_code,
                "file": cl.get(f"/api/showcase/{pid}/files/{fname}").status_code,
                "like": cl.post(f"/api/showcase/{pid}/like", json={}).status_code,
                "report": cl.post(f"/api/showcase/{pid}/report", json={"reason": "other"}).status_code}
    assert set(seen_by(other).values()) == {404}
    for tab in ("trending", "free", "foryou"):
        other.get("/api/showcase?tab=trending&q=lamp")
        assert pid not in [i["id"] for i in other.get(f"/api/showcase?tab={tab}&q=zebra").json()["items"]]
        assert pid not in [i["id"] for i in other.get(f"/api/showcase?tab={tab}").json()["items"]]
    assert pid not in [i["id"] for i in other.get(f"/api/users/{p['creator_id']}").json()["projects"]]
    assert pid in [i["id"] for i in o.get("/api/me/projects").json()["projects"]]
    assert o.get(f"/api/showcase/{pid}").status_code == 200
    # public → immediate everywhere
    assert o.put(f"/api/showcase/{pid}/visibility", json={"visibility": "public"}).status_code == 200
    assert pid in [i["id"] for i in other.get("/api/showcase?tab=free&q=zebra").json()["items"]]
    assert other.get(f"/p/{pid}").status_code == 200 and other.get(f"/api/showcase/{pid}/files/{fname}").status_code == 200
    # followers-only: only followers
    o.put(f"/api/showcase/{pid}/visibility", json={"visibility": "followers"})
    assert other.get(f"/api/showcase/{pid}").status_code == 404
    other.post(f"/api/follow/{p['creator_id']}")
    assert other.get(f"/api/showcase/{pid}").status_code == 200 and other.get(f"/p/{pid}").status_code == 200
    assert pid not in [i["id"] for i in other.get("/api/showcase?tab=trending").json()["items"]]   # Trending = public only
    o.put(f"/api/showcase/{pid}/visibility", json={"visibility": "private"})
    assert other.get(f"/api/showcase/{pid}").status_code == 404
    assert other.put(f"/api/showcase/{pid}/visibility", json={"visibility": "public"}).status_code == 404   # not owner


def test_lesson_pages_leak_no_user_data():
    s = client(ADULT); s.post("/api/learn/lessons/lithophanes/steps/0", json={"done": True})
    html = client().get("/l/lithophanes").text
    assert "Ada Adult" not in html and "steps_done" not in html and "Teacher notes" not in html


# ===================================================================== LIKES / DOWNLOADS / TRENDING
def test_likes_downloads_trending():
    o = client(ADULT); clear(o)
    b1, b2 = photo_build(o), photo_build(o)
    p1 = publish(o, b1, "public", title="Alpha lamp").json(); p2 = publish(o, b2, "public", title="Beta lamp").json()
    pr = publish(o, photo_build(o), "private", title="Hidden lamp").json()
    v1, v2, v3 = (client({"display_name": f"Liker{n}", "dob": "1990-01-01"}) for n in (1, 2, 3))      # nozzles need an account
    r = v1.post(f"/api/showcase/{p1['id']}/like", json={}).json(); assert r == {"liked": True, "likes": r["likes"]}
    base = r["likes"]
    assert v1.post(f"/api/showcase/{p1['id']}/like", json={}).json()["liked"] is False        # toggle off
    v1.post(f"/api/showcase/{p1['id']}/like", json={"liked": True}); v1.post(f"/api/showcase/{p1['id']}/like", json={"liked": True})
    assert v1.get(f"/api/showcase/{p1['id']}").json()["likes"] == base and v1.get(f"/api/showcase/{p1['id']}").json()["liked"]   # one per visitor
    v2.post(f"/api/showcase/{p1['id']}/like", json={}); assert v3.get(f"/api/showcase/{p1['id']}").json()["likes"] == base + 1
    assert o.post(f"/api/showcase/{p1['id']}/like", json={}).status_code == 403              # not your own
    for bad in ("dislike", "unlike", "downvote"):
        assert v1.post(f"/api/showcase/{p1['id']}/{bad}", json={}).status_code in (404, 405)
    assert "dislikes" not in v1.get(f"/api/showcase/{p1['id']}").json()
    assert v1.post(f"/api/showcase/{pr['id']}/like", json={}).status_code == 404            # private: no likes
    # downloads count once per visitor, not for private, not for the owner
    fn = lambda p: f"/api/showcase/{p['id']}/files/{p['files'][0]['name']}"
    d0 = v1.get(f"/api/showcase/{p2['id']}").json()["downloads"]
    for _ in range(3): v1.get(fn(p2))
    o.get(fn(p2)); v2.get(fn(p2))
    assert v3.get(f"/api/showcase/{p2['id']}").json()["downloads"] == d0 + 2
    o.get(fn(pr)); assert o.get(f"/api/showcase/{pr['id']}").json()["likes"] is None and o.get(f"/api/showcase/{pr['id']}").json()["downloads"] is None
    # ranking: likes + downloads drive Trending
    for v in (v1, v2, v3): v.post(f"/api/showcase/{p2['id']}/like", json={"liked": True})
    v2.get(fn(p2)); v3.get(fn(p2))
    ids = [i["id"] for i in v1.get("/api/showcase?tab=trending").json()["items"]]
    assert pr["id"] not in ids and ids.index(p2["id"]) < ids.index(p1["id"])
    # changing to private drops it from counts/lists at once
    o.put(f"/api/showcase/{p2['id']}/visibility", json={"visibility": "private"})
    assert p2["id"] not in [i["id"] for i in v1.get("/api/showcase?tab=trending").json()["items"]]


def test_trending_score_formula():
    mk = lambda likes, dl, day: {"_likes": likes, "_downloads": dl, "created": f"2026-09-{day:02d}T00:00:00+00:00"}
    from datetime import datetime, timezone
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert trending_score(mk(10, 0, 30), now) > trending_score(mk(0, 10, 30), now)         # a like outweighs a download
    assert trending_score(mk(5, 5, 30), now) > trending_score(mk(5, 5, 1), now)            # recency decay
    assert trending_score(mk(0, 0, 30), now) == 0 and trending_score(mk(50, 50, 1), now) > trending_score(mk(1, 0, 30), now)




# ===================================================================== LANGUAGE FILTER (no strikes / bans)
BLOCKED = ["fuck you", "you are a b1tch", "sh!t", "a55hole", "f u c k", "f.u.c.k", "fuuuuck", "fuckyou", "what the fucking", "cocksucker",
           "Scheiße", "arschloch", "puta madre", "hijo de puta", "merde", "putain", "cazzo", "vaffanculo", "kurwa", "kill yourself", "send nudes",
           "dickhead", "assholes", "shitty", "you are a retard", "kys", "FUCK", "fück", "porn", "n1gger", "scheisse", "hoer", "mierda"]
FINE = ["class", "assemble the cockpit", "Scunthorpe", "print the benchy on the Prusa", "ball bearings", "nuts and bolts", "my assistant", "glass",
        "hello world", "a classic analysis", "cucumber", "great lithophane!", "hot end at 210", "stopcock valve", "cockatoo", "pass the compass",
        "Essex", "Sussex", "Penistone", "Mississippi", "document", "Dickinson", "raccoon", "pass hole", "this hit", "title: Dragon Egg", "I am 12",
        "Hancock", "bass guitar", "mass", "button", "Shiitake", "fan duct", "bite size", "Let's print 3d things", "thread pitch 1.5", "assessment"]


@pytest.mark.parametrize("t", BLOCKED)
def test_language_blocked(t): assert safety.scan(t), t


@pytest.mark.parametrize("t", FINE)
def test_language_false_positives(t): assert safety.scan(t) is None, t


def test_contact_info_blocked_and_message_text():
    for t in ("mail me bob@example.com", "call 555-123-4567", "visit www.example.com", "my insta: cool_maker99"):
        assert safety.scan(t) == "contact_info", t
    assert safety.BLOCK_MESSAGE == "Chat doesn't allow that language. Please use appropriate language."


def test_wordlist_files_are_editable_and_attributed(tmp_path, monkeypatch):
    wl = tmp_path / "wl"; shutil.copytree(safety.WL, wl)
    monkeypatch.setattr(safety, "WL", wl); safety._L.sig = None
    assert safety.scan("flibbertigibbet") is None
    with open(wl / "extra.txt", "a") as f: f.write("\nflibbertigibbet\n")
    assert safety.scan("flibbertigibbet") == "language"                      # picked up with no restart
    with open(wl / "allow_words.txt", "a") as f: f.write("\nflibbertigibbet\n")
    assert safety.scan("flibbertigibbet") is None                            # allowlist wins
    monkeypatch.undo(); safety._L.sig = None
    real = safety.WL
    assert (real / "ATTRIBUTION.md").exists() and "CC BY 4.0" in (real / "ATTRIBUTION.md").read_text()
    assert (real / "LICENSE-CC-BY-4.0.txt").exists()
    langs = {p.stem for p in real.glob("??.txt")}
    assert {"en", "es", "fr", "de", "it", "pt", "nl"} <= langs


def test_blocked_language_is_refused_everywhere_no_strikes():
    msg = "Chat doesn't allow that language. Please use appropriate language."
    t = client(ADULT)
    for _ in range(5):                                       # repeated blocks never escalate: no strikes, no bans
        r = t.put("/api/me/links", json={"instagram": "sh1t"})
        assert r.status_code == 422 and r.json()["message"] == msg and r.json()["code"] == "language_blocked"   # one error shape for refused text
    assert t.get("/api/me/safety").status_code == 404 and not hasattr(safety, "record_strike")
    assert client().post("/api/me/signup", json={"display_name": "shithead", "dob": "1990-01-01"}).status_code == 422
    o = client(ADULT); clear(o); b = photo_build(o)
    r = publish(o, b, title="fuck lamp"); assert r.status_code == 422 and r.json()["message"] == msg
    r = publish(o, b, description="visit www.spam.com"); assert r.status_code == 422
    assert publish(o, b, title="Lovely lamp").status_code == 200
