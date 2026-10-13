"""Community batch (Oct 2026): search history, favorites, follow feed + counts, real Trending, remix chains,
'I printed this' photos, multi-file upload and smart orient."""
import io, json, os, time
import numpy as np
import trimesh
from app import config
from app.community import social
from app.community.store import ACTIVITY, PREFS, PRINTS
from app.core import orient
from tests.b1 import client, photo_build, jpeg_with_gps, box_stl, ADULT, ADMIN

import pytest


@pytest.fixture(autouse=True)
def _fresh_activity():
    """Activity written here must not skew Trending in other test files that share the data dir."""
    yield
    ACTIVITY.write([])


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def U(n="Maker", dob="1990-01-01"):
    return client({"display_name": n, "dob": dob})


def publish(c, title="Pub", **extra):
    r = c.post("/api/showcase", json={"build_id": photo_build(c), "title": title, "description": "d", "tags": ["lamp"],
                                      "accept_guidelines": True, "visibility": "public", **extra})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- 1) search history ----------------
def test_search_history_is_per_user_removable_and_clear_really_deletes():
    a, b = U("Sa"), U("Sb")
    a.get("/api/showcase?q=lamp"); a.get("/api/showcase?q=gear"); b.get("/api/showcase?q=fish")
    assert a.get("/api/me/searches").json()["searches"] == ["gear", "lamp"]
    assert b.get("/api/me/searches").json()["searches"] == ["fish"]
    assert a.post("/api/me/searches/remove", json={"q": "gear"}).json()["searches"] == ["lamp"]
    assert a.delete("/api/me/searches").json()["searches"] == []
    raw = json.dumps(PREFS.read())
    assert "lamp" not in raw and "gear" not in raw and "fish" in raw          # gone from disk, the other user's history kept


def test_search_history_ui_has_clear_and_per_item_remove():
    js = open(os.path.join(ROOT, "static", "community.js"), encoding="utf-8").read()
    assert "Clear history" in js and "/api/me/searches/remove" in js and 'id="shRecent"' in open(os.path.join(ROOT, "static", "index.html")).read()


# ---------------- 2) favorites ----------------
def test_favorites_toggle_list_and_privacy():
    owner = U("Fo"); item = publish(owner); v = U("Fv")
    assert client().post(f"/api/showcase/{item['id']}/favorite", json={"favorite": True}).status_code == 401
    assert v.post(f"/api/showcase/{item['id']}/favorite", json={"favorite": True}).json()["favorite"] is True
    assert v.get(f"/api/showcase/{item['id']}").json()["favorited"] is True
    assert [i["id"] for i in v.get("/api/me/favorites").json()["items"]] == [item["id"]]
    assert owner.get("/api/me/favorites").json()["items"] == []
    owner.put(f"/api/showcase/{item['id']}/visibility", json={"visibility": "private"})
    assert v.get("/api/me/favorites").json()["items"] == []                         # private now: not leaked through favorites
    assert v.post("/api/showcase/zo-gear-demo/favorite", json={}).json()["favorite"] is True    # no body toggles
    assert v.post("/api/showcase/zo-gear-demo/favorite", json={}).json()["favorite"] is False


def test_heart_is_an_svg_not_a_heart_character():
    js = open(os.path.join(ROOT, "static", "community.js"), encoding="utf-8").read()
    assert "data-fav=" in js and "Save to Favorites" in js and "♥" not in js and "❤" not in js


# ---------------- 3) follows ----------------
def test_follow_counts_and_following_feed():
    maker = U("Fm"); fan = U("Ff"); item = publish(maker, "Follow me")
    uid = maker.get("/api/me").json()["id"]
    assert fan.get("/api/showcase?tab=following").json()["items"] == []
    assert fan.post(f"/api/follow/{uid}").json()["following"] is True
    feed = fan.get("/api/showcase?tab=following").json()["items"]
    assert [i["id"] for i in feed] == [item["id"]]
    prof = fan.get(f"/api/users/{uid}").json()
    assert prof["followers"] == 1 and prof["following"] == 0 and prof["following_creator"] is True
    fan_id = fan.get("/api/me").json()["id"]
    assert fan.get(f"/api/users/{fan_id}/counts").json()["following"] == 1
    fan.delete(f"/api/follow/{uid}")
    assert fan.get("/api/showcase?tab=following").json()["items"] == []
    assert "following" in client().get("/api/config").json()["showcase_tabs"]
    assert client().get("/api/showcase?tab=following").json()["empty"]["text"]


def test_no_direct_messages_exist():
    paths = [getattr(r, "path", "") for r in __import__("app.main", fromlist=["app"]).app.routes]
    assert not [p for p in paths if "message" in p or "/dm" in p or "chat" in p.split("/")[-1]]


# ---------------- 4) trending ----------------
def test_trending_ranks_recent_activity_over_newest_with_decay():
    a = U("Ta"); old = publish(a, "Old but loved"); new = publish(a, "Brand new")
    now = time.time()
    for n in range(4):
        social.record("fav", old["id"], f"s{n}", now=now)
        social.record("printed", old["id"], f"p{n}", now=now)
    ids = [i["id"] for i in client().get("/api/showcase?tab=trending").json()["items"]]
    assert ids.index(old["id"]) < ids.index(new["id"])
    # the same activity long ago is worth far less than today's
    assert social.heat(now + 10 * 86400).get(old["id"], 0) < social.heat(now)[old["id"]] / 5
    # one person tapping favorite on/off/on cannot farm it
    v = U("Tv")
    for _ in range(3):
        v.post(f"/api/showcase/{new['id']}/favorite", json={"favorite": True}); v.post(f"/api/showcase/{new['id']}/favorite", json={"favorite": False})
    v.post(f"/api/showcase/{new['id']}/favorite", json={"favorite": True})
    assert sum(1 for e in ACTIVITY.read() if e["i"] == new["id"] and e["k"] == "fav") == 1
    ACTIVITY.update(lambda l: l.__setitem__(slice(None), [e for e in l if e["i"] not in (old["id"], new["id"])]))   # don't skew other tests' Trending


def test_downloads_count_toward_trending_once_per_person():
    a = U("Da"); it = publish(a, "Dl"); v = U("Dv")
    f = it["files"][0]["url"]
    v.get(f); v.get(f)
    assert sum(1 for e in ACTIVITY.read() if e["i"] == it["id"] and e["k"] == "download") == 1


# ---------------- 5) remix chain ----------------
def test_remix_chain_links_back_through_every_step():
    a, b, c = U("Ra"), U("Rb"), U("Rc")
    first = publish(a, "First")
    second = publish(b, "Second", remix_of=first["share_url"])
    third = publish(c, "Third", remix_of=second["id"])
    ch = client().get(f"/api/showcase/{third['id']}").json()["remix_chain"]
    assert [x["title"] for x in ch] == ["Second", "First"] and ch[0]["url"] == f"/p/{second['id']}" and ch[1]["creator"].startswith("@")
    assert c.post("/api/showcase", json={"build_id": photo_build(c), "title": "x", "accept_guidelines": True, "visibility": "public",
                                         "remix_of": "nope99"}).status_code == 422
    a.put(f"/api/showcase/{first['id']}/visibility", json={"visibility": "private"})
    ch = client().get(f"/api/showcase/{third['id']}").json()["remix_chain"]
    assert ch[-1]["id"] is None and "First" not in json.dumps(ch)                      # a private parent is never revealed
    assert "Remixed from" in open(os.path.join(ROOT, "static", "community.js")).read()


# ---------------- 6) I printed this ----------------
def test_printed_photo_goes_through_photo_safety_and_moderation():
    a = U("Pa"); it = publish(a, "Printable"); v = U("Pv")
    url = f"/api/showcase/{it['id']}/prints"
    assert client().post(url, files={"photo": ("p.jpg", jpeg_with_gps(), "image/jpeg")}).status_code == 401
    assert v.post(url, files={"photo": ("p.jpg", b"not an image", "image/jpeg")}).status_code == 415
    r = v.post(url, files={"photo": ("p.jpg", jpeg_with_gps(), "image/jpeg")}, data={"caption": "Came out great", "photo_ack": "true"})
    assert r.status_code == 200, r.text
    p = r.json()
    img = v.get(p["url"]).content
    assert b"SecretCam" not in img and b"GPS" not in img                               # EXIF / GPS stripped
    # held for review: only the uploader sees it (as pending), nothing counts for Trending yet
    assert client().get(url).json()["prints"] == [] and client().get(p["url"]).status_code == 404
    mine = v.get(url).json()["prints"]; assert mine[0]["pending"] and mine[0]["status"] == "pending"
    assert not [e for e in ACTIVITY.read() if e["k"] == "printed" and e["i"] == it["id"]]
    pend = client().get("/api/moderation/queue", headers=ADMIN).json()["pending_prints"]
    assert p["id"] in [x["id"] for x in pend]
    assert client().post(f"/api/moderation/prints/{p['id']}/approve").status_code == 403          # admin token required
    assert client().post(f"/api/moderation/prints/{p['id']}/approve", headers=ADMIN).json()["status"] == "approved"
    assert [e for e in ACTIVITY.read() if e["k"] == "printed" and e["i"] == it["id"]]
    g = client().get(url).json()["prints"]
    assert [x["id"] for x in g] == [p["id"]] and g[0]["caption"] == "Came out great"
    assert client().get(f"/api/showcase/{it['id']}").json()["prints_count"] == 1
    # report -> minor_safety hides it immediately, it shows up in the queue with a preview, restore brings it back
    rep = U("Pr").post(f"/api/prints/{p['id']}/report", json={"reason": "minor_safety", "details": ""}).json()
    assert rep["auto_hidden"] and client().get(url).json()["prints"] == [] and client().get(p["url"]).status_code == 404
    q = client().get("/api/moderation/queue", headers=ADMIN).json()["reports"]
    row = next(x for x in q if x["item_id"] == "print:" + p["id"])
    assert row["preview"]["kind"] == "print photo"
    assert client().get(row["preview"]["thumb"], headers=ADMIN).status_code == 200
    client().post(f"/api/moderation/{row['id']}/resolve", json={"action": "restore"}, headers=ADMIN)
    assert len(client().get(url).json()["prints"]) == 1
    assert U("Px").delete(f"/api/prints/{p['id']}").status_code == 404                  # only the uploader can delete
    assert v.delete(f"/api/prints/{p['id']}").json()["ok"] and client().get(url).json()["prints"] == []


def test_printed_photo_caption_uses_chat_filter_and_ack_is_required_when_on(monkeypatch):
    a = U("Ca"); it = publish(a, "Cap"); v = U("Cv")
    url = f"/api/showcase/{it['id']}/prints"
    r = v.post(url, files={"photo": ("p.jpg", jpeg_with_gps(), "image/jpeg")}, data={"caption": "email me at kid@example.com"})
    assert r.status_code >= 400
    monkeypatch.setattr(config, "PHOTO_ACK_REQUIRED", True)
    assert v.post(url, files={"photo": ("p.jpg", jpeg_with_gps(), "image/jpeg")}).status_code == 415


# ---------------- 7) multi-file upload ----------------
def _cube(s):
    return trimesh.creation.box([s, s, s]).export(file_type="stl")


def test_multi_upload_parts_of_one_print_are_spaced_on_one_plate():
    c = U("Ma")
    files = [("files", (f"p{n}.stl", _cube(20), "model/stl")) for n in range(3)]
    r = c.post("/api/edit/multi", files=files, data={"mode": "plate"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mode"] == "plate" and len(j["projects"]) == 1 and j["plate"]["fits"] and j["plate"]["parts"] == 3
    xs = sorted(p[0] for p in j["plate"]["positions"])
    assert all(b - a >= 20 + 5 - 1e-6 for a, b in zip(xs, xs[1:]))                     # no overlap, 5 mm gap


def test_multi_upload_bed_fit_check_and_separate_prints():
    c = U("Mb")
    big = [("files", (f"b{n}.stl", _cube(150), "model/stl")) for n in range(2)]
    j = c.post("/api/edit/multi", files=big, data={"mode": "plate", "bed_x": "220", "bed_y": "220"}).json()
    assert j["plate"]["fits"] is False and "don't fit" in json.dumps(j["project"])
    obj = trimesh.creation.box([10, 10, 10]).export(file_type="obj")
    j = c.post("/api/edit/multi", files=[("files", ("a.stl", _cube(10), "model/stl")), ("files", ("b.obj", obj, "text/plain"))],
               data={"mode": "separate"}).json()
    assert j["mode"] == "separate" and len(j["projects"]) == 2
    assert c.post("/api/edit/multi", files=[("files", ("x.stl", b"hello", "model/stl"))], data={"mode": "plate"}).status_code in (415, 422)
    assert c.post("/api/edit/multi", files=[("files", ("x.stl", _cube(5), "model/stl"))], data={"mode": "zzz"}).status_code == 400


def test_arrange_wraps_rows_inside_the_bed():
    meshes = [trimesh.creation.box([60, 40, 10]) for _ in range(6)]
    m, rep = orient.arrange(meshes, (220, 220), 5)
    assert rep["fits"] and rep["footprint_mm"][0] <= 220 and m.bounds[0][2] == 0


# ---------------- 8) smart orient ----------------
def _wedge():
    """A tall thin slab standing on its edge: the big flat face is vertical until laid flat."""
    return trimesh.creation.box([2, 40, 30])


def test_lay_flat_puts_the_largest_flat_face_down():
    m = _wedge()
    m.apply_transform(trimesh.transformations.rotation_matrix(0.6, [1, 1, 0]))
    out, rep = orient.lay_flat(m)
    assert abs(out.bounds[0][2]) < 1e-6 and out.extents[2] < 2.5 and rep["face_mm2"] >= 1199


def test_best_position_reduces_overhang():
    # a "T": a top bar on a thin post has big overhangs upright, none when flipped onto the bar
    post = trimesh.creation.box([4, 4, 30]); post.apply_translation([0, 0, 15])
    bar = trimesh.creation.box([40, 10, 4]); bar.apply_translation([0, 0, 32])
    t = trimesh.util.concatenate([post, bar])
    before = orient.overhang(t)["overhang_mm2"]
    out, rep = orient.best_position(t)
    assert rep["overhang_mm2"] < before and rep["before"]["overhang_mm2"] == round(before, 1)


def test_orient_ops_in_the_editor_and_ui():
    c = U("Oa")
    r = c.post("/api/edit/new", files={"file": ("m.stl", box_stl(), "model/stl")}, data={"units": "mm"})
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    for op in ("lay_flat", "best_orient"):
        assert c.post(f"/api/edit/{bid}/op", json={"op": op, "params": {}}).status_code == 200
    assert c.post(f"/api/edit/{bid}/op", json={"op": "rotate", "params": {"rx": 90}}).status_code == 200      # manual rotate still there
    js = open(os.path.join(ROOT, "static", "edit.js"), encoding="utf-8").read()
    assert "lay_flat" in js and "best_orient" in js and "Lay flat" in js and "Best position" in js
    assert "#slicer/orient" in open(os.path.join(ROOT, "static", "index.html")).read()


def test_rejected_print_photo_is_deleted_with_its_file_and_old_photos_become_pending():
    a = U("Ja"); it = publish(a, "Rej"); v = U("Jv")
    p = v.post(f"/api/showcase/{it['id']}/prints", files={"photo": ("p.jpg", jpeg_with_gps(), "image/jpeg")}).json()
    f = social.print_path(social.get_print(p["id"])); assert f.exists()
    assert client().post(f"/api/moderation/prints/{p['id']}/reject", headers=ADMIN).json()["status"] == "deleted"
    assert social.get_print(p["id"]) is None and not f.exists() and v.get(f"/api/showcase/{it['id']}/prints").json()["prints"] == []
    assert client().post(f"/api/moderation/prints/{p['id']}/approve", headers=ADMIN).status_code == 404
    # migration: a photo stored before review existed (no status) is pending, hidden from others
    q = v.post(f"/api/showcase/{it['id']}/prints", files={"photo": ("p.jpg", jpeg_with_gps(), "image/jpeg")}).json()
    PRINTS.update(lambda l: [r.pop("status", None) for r in l if r["id"] == q["id"]])
    assert social.mark_existing_pending() >= 1 and social.get_print(q["id"])["status"] == "pending"
    assert client().get(f"/api/showcase/{it['id']}/prints").json()["prints"] == []
    assert "Waiting for review" in open(os.path.join(ROOT, "static", "community.js")).read()
    assert "/api/moderation/prints/" in open(os.path.join(ROOT, "static", "moderation.js")).read()
