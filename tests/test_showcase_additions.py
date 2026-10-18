"""Showcase additions (Oct 2026): licence picker with server-side ND enforcement, sort
options, and related items (docs/specs/showcase-gaps.md items 1, 4, 5 — app/community/licensing.py,
app/community/discovery.py, wiring in catalog/community/showcase_extras)."""
import json
import os

import pytest

from app.community import discovery, licensing
from app.community.store import LISTINGS, MODERATION, PRINTS
from tests.b1 import client, photo_build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def U(n="Maker", dob="1990-01-01"):
    return client({"display_name": n, "dob": dob})


@pytest.fixture(autouse=True)
def _fresh_stores():
    """Everything this file touches (listings, likes, prints, personalization) is restored, so
    other test files sharing the data dir see the store exactly as it was — e.g. published
    'lamp'-tagged items would otherwise turn 'lamp' into a known tag and skew later files."""
    from app.community.store import ENGAGEMENT, PREFS, MODERATION
    snap = {s: s.read() for s in (LISTINGS, ENGAGEMENT, PREFS, PRINTS, MODERATION)}
    yield
    for s, was in snap.items():
        s.write(was)


def _print(item_id, sid="psid", n=0):
    """A well-formed approved print-photo record (the shape POST /showcase/{iid}/prints writes)."""
    return {"id": f"pr{n}", "item_id": item_id, "owner_sid": sid, "status": "approved",
            "created": 1700000000 + n, "caption": ""}


def publish(c, title="Pub", **extra):
    r = c.post("/api/showcase", json={"build_id": photo_build(c), "title": title, "description": "d",
                                      "tags": ["lamp"], "accept_guidelines": True, "nsfw": False,
                                      "visibility": "public", **extra})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- licence menu ----------------
def test_licence_menu_endpoint():
    c = U("Lm")
    r = c.get("/api/showcase/licenses")
    assert r.status_code == 200
    j = r.json()
    ids = [x["id"] for x in j["licenses"]]
    assert len(ids) == 8 and j["default"] == "private-use"
    assert [x for x in j["licenses"] if x["default"]][0]["id"] == "private-use"
    assert all("url" in x and "blurb" in x and "derivatives" in x for x in j["licenses"])
    nd = next(x for x in j["licenses"] if x["id"] == "cc-by-nd-4.0")
    assert nd["derivatives"] is False and "creativecommons.org" in nd["url"]


def test_licence_validation_unit():
    assert licensing.check(None) == "private-use" and licensing.check("") == "private-use"
    assert licensing.check("cc-by-4.0") == "cc-by-4.0"
    with pytest.raises(ValueError, match="unknown licence"):
        licensing.check("gpl-3.0")
    with pytest.raises(ValueError, match="unknown licence"):
        licensing.check(123)
    # permission is never inferred from an absent or unknown licence
    assert licensing.may_remix(None) is False
    assert licensing.may_remix("") is False
    assert licensing.may_remix("made-up") is False
    assert licensing.may_remix("cc-by-nd-4.0") is False
    assert licensing.may_remix("cc-by-nc-nd-4.0") is False
    assert licensing.may_remix("private-use") is False
    assert licensing.may_remix("cc-by-4.0") and licensing.may_remix("cc0-1.0")
    assert licensing.may_remix("cc-by-nc-sa-4.0") and licensing.may_remix("cc-by-sa-4.0")
    assert licensing.describe("cc0-1.0")["name"] == "CC0 1.0"
    assert licensing.describe("legacy-or-unknown") is None and licensing.describe(None) is None


def test_new_projects_default_to_private_use():
    c = U("Ld")
    item = publish(c, "Default licence")
    assert item["license_id"] == "private-use"


@pytest.mark.parametrize("lid", ["cc0-1.0", "cc-by-4.0", "cc-by-sa-4.0", "cc-by-nd-4.0",
                                 "cc-by-nc-4.0", "cc-by-nc-sa-4.0", "cc-by-nc-nd-4.0", "private-use"])
def test_every_menu_licence_is_accepted(lid):
    c = U("Lv")
    assert publish(c, f"Lic {lid}", license_id=lid)["license_id"] == lid


def test_unknown_licence_is_refused():
    c = U("Lu")
    r = c.post("/api/showcase", json={"build_id": photo_build(c), "title": "Bad licence", "description": "d",
                                     "tags": ["lamp"], "accept_guidelines": True, "nsfw": False,
                                     "visibility": "public", "license_id": "wtf-1.0"})
    assert r.status_code == 400 and "unknown licence" in r.json()["detail"]


def test_nd_licence_blocks_remixes_server_side():
    maker, remixer = U("Ln"), U("Lr")
    nd = publish(maker, "ND project", license_id="cc-by-nd-4.0")
    r = remixer.post("/api/showcase", json={"build_id": photo_build(remixer), "title": "Remix",
                                            "description": "d", "tags": ["lamp"], "accept_guidelines": True,
                                            "nsfw": False, "visibility": "public", "remix_of": nd["id"]})
    assert r.status_code == 422 and "doesn't allow publishing remixes" in r.json()["detail"]


def test_private_use_default_blocks_remixes():
    maker, remixer = U("Lp"), U("Lq")
    prv = publish(maker, "Private default")            # no licence passed -> private-use
    r = remixer.post("/api/showcase", json={"build_id": photo_build(remixer), "title": "Remix",
                                            "description": "d", "tags": ["lamp"], "accept_guidelines": True,
                                            "nsfw": False, "visibility": "public", "remix_of": prv["id"]})
    assert r.status_code == 422 and "licence" in r.json()["detail"]


def test_remixable_licence_still_allows_remixes():
    maker, remixer = U("Lx"), U("Ly")
    src = publish(maker, "Remixable", license_id="cc-by-4.0")
    ok = publish(remixer, "Remix", remix_of=src["id"])
    assert ok["license_id"] == "private-use"
    ch = remixer.get(f"/api/showcase/{ok['id']}").json()["remix_chain"]
    assert src["id"] in [x["id"] for x in ch if x.get("id")]                # the remix links back


def test_legacy_unspecified_licence_is_not_remixable():
    # a record with no licence (pre-picker legacy): permission is never inferred
    c = U("Lz")
    item = publish(c, "Legacy", license_id="cc-by-4.0")
    LISTINGS.update(lambda l: next(i for i in l if i["id"] == item["id"]).pop("license_id"))
    remixer = U("Lw")
    r = remixer.post("/api/showcase", json={"build_id": photo_build(remixer), "title": "Remix",
                                           "description": "d", "tags": ["lamp"], "accept_guidelines": True,
                                           "nsfw": False, "visibility": "public", "remix_of": item["id"]})
    assert r.status_code == 422


# ---------------- sort ----------------
def test_check_sort():
    assert discovery.check_sort("") == ""
    for s in discovery.SORTS:
        assert discovery.check_sort(s) == s
    with pytest.raises(ValueError, match="sort must be"):
        discovery.check_sort("popular")


def test_apply_sort_unit():
    items = [{"id": "a", "created": "2026-01-01", "_likers": ["x"]},
             {"id": "b", "created": "2026-02-01", "_likers": ["x", "y", "z"]},
             {"id": "c", "created": "2026-03-01", "_likers": []}]
    assert [i["id"] for i in discovery.apply_sort(items, "newest")] == ["c", "b", "a"]
    assert [i["id"] for i in discovery.apply_sort(items, "likes")] == ["b", "a", "c"]   # ties -> newest
    assert [i["id"] for i in discovery.apply_sort(items, "")] == ["a", "b", "c"]      # untouched
    # printed reads the PRINTS store: give 'a' two prints, 'c' one
    PRINTS.write([_print("a", n=1), _print("a", n=2), _print("c", n=3)])
    assert [i["id"] for i in discovery.apply_sort(items, "printed")] == ["a", "c", "b"]
    PRINTS.write([])


def test_sort_on_the_showcase_api():
    a, b, v = U("Sa"), U("Sb"), U("Sv")
    first = publish(a, "First")
    second = publish(a, "Second")
    third = publish(b, "Third")
    v.post(f"/api/showcase/{third['id']}/like", json={"liked": True})
    v.post(f"/api/showcase/{first['id']}/like", json={"liked": True})
    v.post(f"/api/showcase/{first['id']}/like", json={"liked": True})   # second user like
    PRINTS.write([_print(third["id"], n=1), _print(second["id"], n=2), _print(second["id"], n=3)])
    items = lambda sort="": [i["id"] for i in v.get(f"/api/showcase?tab=free&sort={sort}").json()["items"]]
    mine = {first["id"], second["id"], third["id"]}
    only = lambda ids: [i for i in ids if i in mine]        # the data dir is shared across the session
    assert only(items("newest")) == [third["id"], second["id"], first["id"]]
    assert only(items("likes")) == [third["id"], first["id"], second["id"]]
    assert only(items("printed")) == [second["id"], third["id"], first["id"]]
    assert only(items()) == [third["id"], second["id"], first["id"]]  # tab default unchanged (newest)
    PRINTS.write([])


def test_invalid_sort_is_a_400():
    c = U("Si")
    assert c.get("/api/showcase?tab=free&sort=hottest").status_code == 400
    assert c.get("/api/showcase?tab=free&sort=newest").status_code == 200


# ---------------- related items ----------------
def test_related_same_maker_then_same_tag():
    maker, other, viewer = U("Rm"), U("Ro"), U("Rv")
    m1 = publish(maker, "M1", tags=["relx"])
    m2 = publish(maker, "M2", tags=["relx"])
    m3 = publish(maker, "M3", tags=["relx"])
    o1 = publish(other, "O1", tags=["relx", "shared"])
    o2 = publish(other, "O2", tags=["relx", "other"])
    j = viewer.get(f"/api/showcase/{m1['id']}").json()
    rel = j["related"]
    assert len(rel) <= 6
    assert [x["id"] for x in rel if x["why"] == "maker"] == [m3["id"], m2["id"]]     # same maker, newest first
    assert o1["id"] in [x["id"] for x in rel] and o2["id"] in [x["id"] for x in rel]  # then the shared tag
    assert all(x["id"] != m1["id"] for x in rel)
    assert all(set(x) == {"id", "title", "creator_id", "why", "license_id", "photo", "url"} for x in rel)


def test_related_tag_bucket_fills_all_remaining_slots():
    # no same-maker matches: the tag bucket supplies all 6 (fill rule, not a hard 3+3 split)
    stranger, viewer = U("Rt"), U("Ru")
    mine = publish(stranger, "SoloMain", tags=["relw"])
    for n in range(7):
        publish(U(f"Tw{n}"), f"Tw{n}", tags=["relw"])
    rel = viewer.get(f"/api/showcase/{mine['id']}").json()["related"]
    assert len(rel) == 6 and all(x["why"] == "tag" for x in rel)


def test_related_follows_actor_visibility_follower_case():
    # a follower CAN see the maker's follower-only items, so they can be related;
    # a stranger cannot see them, so they never are
    maker, follower, stranger = U("Rf"), U("Rg"), U("Rh2")
    pub = publish(maker, "PubF", tags=["relf"])
    fo = publish(maker, "FollowerOnlyF", visibility="followers", tags=["relf"])
    follower.post(f"/api/follow/{pub['creator_id']}")
    assert any(x["id"] == fo["id"] for x in follower.get(f"/api/showcase/{pub['id']}").json()["related"])
    assert not any(x["id"] == fo["id"] for x in stranger.get(f"/api/showcase/{pub['id']}").json()["related"])


def test_related_excludes_open_reports_without_hiding_item():
    # spec: "hidden or reported projects never appear" — an open report (here: copyright,
    # which does NOT auto-hide) keeps the item out of related lists while it stays
    # visible in the showcase itself
    maker, viewer = U("Rp"), U("Rq")
    m1 = publish(maker, "RepMain", tags=["relr"])
    m2 = publish(maker, "RepTarget", tags=["relr"])
    r = viewer.post(f"/api/showcase/{m2['id']}/report",
                   json={"reason": "copyright", "details": "not mine"})
    assert r.status_code == 200 and r.json().get("status") == "open"
    rel = viewer.get(f"/api/showcase/{m1['id']}").json()["related"]
    assert not any(x["id"] == m2["id"] for x in rel)
    shown = [x["id"] for x in viewer.get("/api/showcase?tab=free").json()["items"]]
    assert m2["id"] in shown                      # reported, not hidden: still visible in the tab


def test_related_excludes_hidden_and_private():
    maker, other, viewer = U("Rh"), U("Ri"), U("Rj")
    m1 = publish(maker, "H1")
    m2 = publish(maker, "H2")
    p1 = publish(other, "P1")                          # private by default visibility is public here; make it private
    viewer_hidden = publish(maker, "H3")
    MODERATION.update(lambda m: m["hidden"].append(m2["id"]))      # how moderation actually hides an item
    other.put(f"/api/showcase/{p1['id']}/visibility", json={"visibility": "private"})
    rel = viewer.get(f"/api/showcase/{m1['id']}").json()["related"]
    ids = [x["id"] for x in rel]
    assert m2["id"] not in ids and p1["id"] not in ids                                 # hidden/private never related
    assert m1["id"] not in ids


def test_related_caps_at_six():
    maker, viewer = U("Rk"), U("Rl")
    for n in range(8):
        publish(maker, f"C{n}")
    items = viewer.get("/api/showcase?tab=free").json()["items"]
    j = viewer.get(f"/api/showcase/{items[0]['id']}").json()
    assert len(j["related"]) <= 6


def test_related_is_compact_no_engagement_counts():
    maker, viewer = U("Rm2"), U("Rn")
    m1 = publish(maker, "X1")
    m2 = publish(maker, "X2")
    rel = viewer.get(f"/api/showcase/{m1['id']}").json()["related"]
    assert all("likes" not in x and "prints_count" not in x and "files" not in x for x in rel)
