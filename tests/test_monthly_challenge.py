"""Monthly theme: close date, top 3, and the earlier-entry tiebreak."""
from datetime import datetime, timezone

from app.community import challenges
from app.community.store import CHALLENGE_ENTRIES, CHALLENGES, ENGAGEMENT, LISTINGS
from tests.b1 import client, photo_build


def _fresh():
    for store in (LISTINGS, CHALLENGES, CHALLENGE_ENTRIES, ENGAGEMENT):
        store.write(store.read() and [] if store is not ENGAGEMENT else {"likes": {}, "downloads": {}})


def U(n):
    return client({"display_name": n, "dob": "1990-01-01"})


def publish(c, title):
    r = c.post("/api/showcase", json={
        "build_id": photo_build(c), "title": title, "description": "d", "tags": ["lamp"],
        "accept_guidelines": True, "nsfw": False, "visibility": "public", "license_id": "cc-by-4.0",
    })
    assert r.status_code == 200, r.text
    return r.json()


def like(who, item_id):
    r = who.post(f"/api/showcase/{item_id}/like", json={"liked": True})
    assert r.status_code == 200, r.text


def test_close_picks_top_3_and_earlier_entry_wins_ties(monkeypatch):
    saved = {s: s.read() for s in (LISTINGS, CHALLENGES, CHALLENGE_ENTRIES, ENGAGEMENT)}
    for store, empty in ((LISTINGS, []), (CHALLENGES, []), (CHALLENGE_ENTRIES, []), (ENGAGEMENT, {"likes": {}, "downloads": {}})):
        store.write(empty)
    challenges.current_time.override = datetime(2026, 12, 1, tzinfo=timezone.utc)
    try:
        makers = [U(f"Place{n}") for n in range(4)]
        items = [publish(m, f"Tree {n}") for n, m in enumerate(makers)]
        cid = challenges.XMAS_ID
        entered = []
        for m, item in zip(makers, items):
            r = m.post(f"/api/challenges/{cid}/enter", json={"item_id": item["id"]})
            assert r.status_code == 200, r.text
            entered.append(r.json()["entry"])
        fans = [U(f"Fan{n}") for n in range(3)]
        # 0 and 1 tie on 2 likes. 0 entered first, so 0 ranks above 1.
        like(fans[0], items[0]["id"]); like(fans[1], items[0]["id"])
        like(fans[0], items[1]["id"]); like(fans[2], items[1]["id"])
        like(fans[0], items[2]["id"])
        # item 3 has no likes
        challenges.current_time.override = datetime(2026, 12, 24, 12, tzinfo=timezone.utc)
        still = makers[3].get(f"/api/challenges/{cid}").json()
        assert still["status"] == "open" and still["winners_visible"] is False
        challenges.current_time.override = datetime(2026, 12, 25, 8, tzinfo=timezone.utc)
        late = U("Late")
        late_item = publish(late, "Late tree")
        assert late.post(f"/api/challenges/{cid}/enter", json={"item_id": late_item["id"]}).status_code == 400
        shown = makers[0].get(f"/api/challenges/{cid}").json()
        assert shown["winners_visible"] is True
        places = [w["item_id"] for w in shown["winners"]]
        assert places == [items[0]["id"], items[1]["id"], items[2]["id"]]
        assert [w["place"] for w in shown["winners"]] == [1, 2, 3]
        assert shown["winners"][0]["likes"] == shown["winners"][1]["likes"] == 2
        again = makers[0].get(f"/api/challenges/{cid}").json()
        assert [w["item_id"] for w in again["winners"]] == places
        assert "no cash" in shown["blurb"].lower()
        assert shown["next_theme"].startswith("January:")
    finally:
        challenges.current_time.override = None
        for store, data in saved.items():
            store.write(data)
