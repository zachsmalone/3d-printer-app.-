"""Enter the prize-free Remix challenge from a saved Studio build.

The file is published through the same Showcase path as in-app work. A Studio id
is not a Showcase id, and the enter call does not ask for a pasted URL.
"""
import os

import pytest

from app import config
from app.community import challenges, fingerprint as fp
from app.community import protect
from app.community.store import CHALLENGE_ENTRIES, CHALLENGES, LISTINGS
from tests.b1 import client, photo_build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_STL = os.path.join(ROOT, "static", "sample_model.stl")


@pytest.fixture(autouse=True)
def _fresh():
    snap = {s: s.read() for s in (LISTINGS, CHALLENGES, CHALLENGE_ENTRIES, protect.FINGERPRINTS)}
    yield
    for s, was in snap.items():
        s.write(was)


def U(n):
    return client({"display_name": n, "dob": "1990-01-01"})


def showcase(c, title="Pub", build=None, **extra):
    body = {"build_id": build or photo_build(c), "title": title, "description": "d",
            "tags": ["lamp"], "accept_guidelines": True, "nsfw": False,
            "visibility": "public", "license_id": "cc-by-4.0"}
    body.update(extra)
    r = c.post("/api/showcase", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def enter(c, bid, **extra):
    body = {"build_id": bid, "title": extra.pop("title", "Studio remix"), "description": "d",
            "tags": ["lamp"], "accept_guidelines": True, "nsfw": False,
            "visibility": extra.pop("visibility", "public"), "license_id": "cc-by-4.0"}
    body.update(extra)
    return c.post(f"/api/challenges/{challenges.REMIX_ID}/enter", json=body)


def test_enter_challenge_from_studio():
    """A saved Studio file is published and entered. Credit, the AI label, and the remix switch stay."""
    a, b = U("StSrc"), U("StMaker")
    src = showcase(a, "Source lamp", ai_made=True)
    bid = photo_build(b)
    r = enter(b, bid, remix_of=src["id"], ai_made=False, allow_remixes=False, title="My studio remix")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["prize_free"] is True
    assert "no cash" in body["message"].lower() and "no prizes" in body["message"].lower()
    assert "rank" not in body and "prize_amount" not in body
    item_id = body["entry"]["item_id"]
    project = body["project"]
    assert project["id"] == item_id
    assert project["remix_chain"][0]["id"] == src["id"]
    assert project["ai_made"] is True and project["ai_locked"] is True
    assert project["allow_remixes"] is False
    row = next(i for i in LISTINGS.read() if i["id"] == item_id)
    assert row["source_build_id"] == bid
    later = U("StLater")
    refused = later.post("/api/showcase", json={
        "build_id": photo_build(later), "title": "Off the entry", "description": "d",
        "tags": ["lamp"], "accept_guidelines": True, "nsfw": False,
        "visibility": "public", "license_id": "cc-by-4.0", "remix_of": item_id})
    assert refused.status_code == 403
    assert "turned off remixes" in refused.json()["detail"]

    again = enter(b, photo_build(b), remix_of=src["id"], title="Second studio file")
    assert again.status_code == 400
    assert "one remix per person" in again.json()["detail"].lower()

    other = U("StOther")
    foreign = enter(other, bid, remix_of=src["id"], title="Not mine")
    assert foreign.status_code == 404

    off = showcase(a, "Remixes off", allow_remixes=False)
    blocked = U("StBlocked")
    before_entries = len(CHALLENGE_ENTRIES.read())
    no = enter(blocked, photo_build(blocked), remix_of=off["id"], title="Blocked remix")
    assert no.status_code == 403
    assert "turned off remixes" in no.json()["detail"]
    assert len(CHALLENGE_ENTRIES.read()) == before_entries

    plain = U("StPlain")
    missing = enter(plain, photo_build(plain), title="No credit")
    assert missing.status_code == 400
    assert "credited remix" in missing.json()["detail"].lower()
    n = len(LISTINGS.read())
    private = enter(plain, photo_build(plain), remix_of=src["id"], visibility="private", title="Stay private")
    assert private.status_code == 400
    assert "public" in private.json()["detail"].lower()
    assert len(LISTINGS.read()) == n

    saved = U("StSaved")
    saved_id = photo_build(saved)
    posted = showcase(saved, "Already public", build=saved_id, remix_of=src["id"])
    before = len(LISTINGS.read())
    reuse = saved.post(f"/api/challenges/{challenges.REMIX_ID}/enter", json={"build_id": saved_id})
    assert reuse.status_code == 200, reuse.text
    assert reuse.json()["entry"]["item_id"] == posted["id"]
    assert reuse.json()["prize_free"] is True
    assert len(LISTINGS.read()) == before


def test_studio_enter_still_refuses_a_reupload(monkeypatch):
    """A Studio file that matches someone else's model still hits re-upload protection."""
    monkeypatch.setattr(config, "DUPLICATE_CHECK", True)
    protect.FINGERPRINTS.write({})
    real = fp.safe_compute
    target = fp.compute(SAMPLE_STL)
    phase = {"fake": True}

    def wrapped(path):
        if str(config.ORIGINALS) in str(path):
            return real(path)
        return target if phase["fake"] else real(path)

    monkeypatch.setattr(fp, "safe_compute", wrapped)
    owner, maker, other = U("ReOwn"), U("ReMaker"), U("ReOther")
    locked = showcase(owner, "Locked shape", allow_remixes=False)
    phase["fake"] = False
    credit = showcase(other, "Different shape")
    phase["fake"] = True
    n = len(LISTINGS.read())
    refused = enter(maker, photo_build(maker), remix_of=credit["id"], title="Copied shape")
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "copy_refused"
    assert refused.json()["original"]["id"] == locked["id"]
    assert not any(i.get("title") == "Copied shape" for i in LISTINGS.read())
    assert len(LISTINGS.read()) == n


def test_studio_enter_accepts_a_credited_reupload(monkeypatch):
    monkeypatch.setattr(config, "DUPLICATE_CHECK", True)
    protect.FINGERPRINTS.write({})
    real = fp.safe_compute
    target = fp.compute(SAMPLE_STL)

    def wrapped(path):
        if str(config.ORIGINALS) in str(path):
            return real(path)
        return target

    monkeypatch.setattr(fp, "safe_compute", wrapped)
    owner, maker = U("CrOwn"), U("CrMaker")
    src = showcase(owner, "Remixable shape")
    r = enter(maker, photo_build(maker), remix_of=src["id"], title="Credited copy")
    assert r.status_code == 200, r.text
    assert r.json()["project"]["remix_chain"][0]["id"] == src["id"]
    assert r.json()["prize_free"] is True
