"""Showcase posts and saved builds stay separate. Challenges take Showcase posts only."""
import pytest

from app.community import challenges
from app.community.store import CHALLENGE_ENTRIES, CHALLENGES, LISTINGS
from tests.b1 import client, photo_build


@pytest.fixture(autouse=True)
def _fresh():
    snap = {s: s.read() for s in (LISTINGS, CHALLENGES, CHALLENGE_ENTRIES)}
    yield
    for s, was in snap.items():
        s.write(was)


def U(n):
    return client({"display_name": n, "dob": "1990-01-01"})


def publish(c, title, build=None, **extra):
    bid = build or photo_build(c)
    body = {"build_id": bid, "title": title, "description": "d", "tags": ["lamp"],
            "accept_guidelines": True, "nsfw": False, "visibility": "public", "license_id": "cc-by-4.0"}
    body.update(extra)
    r = c.post("/api/showcase", json=body)
    assert r.status_code == 200, r.text
    return r.json(), bid


def test_deleting_a_saved_build_leaves_the_showcase_post():
    maker = U("KeepPost")
    item, bid = publish(maker, "Posted lamp")
    name = item["files"][0]["name"]
    assert maker.delete(f"/api/builds/{bid}").status_code == 200
    assert maker.get(f"/api/builds/{bid}").status_code == 404
    still = maker.get(f"/api/showcase/{item['id']}")
    assert still.status_code == 200, still.text
    assert still.json()["title"] == "Posted lamp"
    downloaded = maker.get(f"/api/showcase/{item['id']}/files/{name}")
    assert downloaded.status_code == 200 and downloaded.content
    row = next(i for i in LISTINGS.read() if i["id"] == item["id"])
    assert row.get("source_build_id") == bid
    assert not row.get("removed_by_creator")


def test_removing_a_showcase_post_leaves_the_saved_file_and_drops_challenge_entries():
    origin, maker, child = U("OrigAcct"), U("PostAcct"), U("RemixAcct")
    src, _ = publish(origin, "Root lamp")
    item, bid = publish(maker, "Middle lamp", remix_of=src["id"])
    kid, _ = publish(child, "Child lamp", remix_of=item["id"])
    assert maker.post(f"/api/challenges/{challenges.XMAS_ID}/enter", json={"item_id": item["id"]}).status_code == 200
    gone = maker.delete(f"/api/showcase/{item['id']}")
    assert gone.status_code == 200, gone.text
    assert maker.get(f"/api/builds/{bid}").status_code == 200
    assert maker.get(f"/files/{bid}/model.stl").status_code == 200
    assert maker.get(f"/api/showcase/{item['id']}").status_code == 404
    detail = maker.get(f"/api/challenges/{challenges.XMAS_ID}").json()
    assert all(e["id"] != item["id"] for e in detail["entries"])
    assert not any(e.get("item_id") == item["id"] for e in CHALLENGE_ENTRIES.read())
    seen = child.get(f"/api/showcase/{kid['id']}")
    assert seen.status_code == 200, seen.text
    assert seen.json()["files"]
    chain = seen.json()["remix_chain"]
    un = maker.get("/api/me").json()["username"]
    assert chain[0]["removed"] is True
    assert chain[0]["id"] is None
    assert chain[0]["creator_username"] == un
    assert chain[0]["creator"] == "@" + un
    assert chain[0]["creator_id"]
    assert chain[1]["id"] == src["id"]
    blob = str(chain).lower()
    assert "original removed" not in blob
    assert "anonymous" not in blob


def test_challenge_picker_lists_every_open_challenge():
    CHALLENGES.update(lambda rows: rows.append({
        "id": "ch_shapes", "slug": "shapes", "title": "Shape challenge", "theme": "shapes",
        "blurb": "Share a shape. Prize-free: no cash, no prizes, no ranking rewards.",
        "rules": ["Prize-free: ZEIM offers no cash or prizes for this challenge."],
        "prize_free": True, "status": "open", "created": 2,
    }))
    origin, maker = U("ListOrig"), U("ListMaker")
    src, _ = publish(origin, "Open source")
    item, _ = publish(maker, "Open remix", remix_of=src["id"])
    assert maker.post(f"/api/challenges/{challenges.XMAS_ID}/enter", json={"item_id": item["id"]}).status_code == 200
    assert maker.post("/api/challenges/ch_shapes/enter", json={"build_id": "aaaaaaaaaaaa"}).status_code == 400
    ok = maker.post("/api/challenges/ch_shapes/enter", json={"item_id": item["id"]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["prize_free"] is True
    rows = {c["id"]: c for c in maker.get("/api/challenges").json()["challenges"] if c["status"] == "open"}
    assert challenges.XMAS_ID in rows and "ch_shapes" in rows
    assert rows[challenges.XMAS_ID]["entered"] is True
    assert rows["ch_shapes"]["entered"] is True
    assert rows[challenges.XMAS_ID]["prize_free"] is True and rows["ch_shapes"]["prize_free"] is True
    stranger = U("ListNew")
    fresh = {c["id"]: c for c in stranger.get("/api/challenges").json()["challenges"] if c["status"] == "open"}
    assert fresh[challenges.XMAS_ID]["entered"] is False and fresh["ch_shapes"]["entered"] is False
