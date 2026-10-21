"""'Allow remixes: Yes/No' switch (chosen at upload, owner-editable, default Yes, enforced by the API)."""
import pytest

from app.community.store import ENGAGEMENT, LISTINGS, MODERATION, PREFS
from tests.b1 import client, photo_build


@pytest.fixture(autouse=True)
def _fresh():
    snap = {s: s.read() for s in (LISTINGS, ENGAGEMENT, PREFS, MODERATION)}
    yield
    for s, was in snap.items():
        s.write(was)


def pub(c, title="Src", **extra):
    body = {"build_id": photo_build(c), "title": title, "description": "d", "tags": ["x"], "accept_guidelines": True,
            "nsfw": False, "visibility": "public", "license_id": "cc-by-4.0", **extra}
    return c.post("/api/showcase", json=body)


def test_default_is_yes_and_remix_allowed():
    a, b = client({"display_name": "A", "dob": "1990-01-01"}), client({"display_name": "B", "dob": "1990-01-01"})
    src = pub(a).json()
    assert src["allow_remixes"] is True and src["can_remix"] is True
    seen = b.get(f"/api/showcase/{src['id']}").json()
    assert seen["can_remix"] and seen["remix_off_reason"] == ""
    r = pub(b, "Mine", remix_of=src["share_url"])
    assert r.status_code == 200, r.text
    assert r.json()["remix_chain"][0]["id"] == src["id"]


def test_off_at_upload_blocks_remix_server_side():
    a, b = client({"display_name": "A2", "dob": "1990-01-01"}), client({"display_name": "B2", "dob": "1990-01-01"})
    src = pub(a, allow_remixes="no").json()
    assert src["allow_remixes"] is False and src["can_remix"] is False
    seen = b.get(f"/api/showcase/{src['id']}").json()
    assert not seen["can_remix"] and "turned off remixes" in seen["remix_off_reason"]
    r = pub(b, "Copy", remix_of=src["id"])
    assert r.status_code == 403 and "turned off remixes" in r.json()["detail"]


def test_owner_toggle_keeps_existing_chain_and_only_owner_may_edit():
    a, b = client({"display_name": "A3", "dob": "1990-01-01"}), client({"display_name": "B3", "dob": "1990-01-01"})
    src = pub(a).json()
    rem = pub(b, "Remix1", remix_of=src["id"]).json()
    assert b.put(f"/api/showcase/{src['id']}/remixes", json={"allow_remixes": False}).status_code == 404   # not the owner
    r = a.put(f"/api/showcase/{src['id']}/remixes", json={"allow_remixes": False})
    assert r.status_code == 200 and r.json()["allow_remixes"] is False
    assert pub(b, "Remix2", remix_of=src["id"]).status_code == 403
    assert b.get(f"/api/showcase/{rem['id']}").json()["remix_chain"][0]["id"] == src["id"]      # credit kept
    assert a.put(f"/api/showcase/{src['id']}/remixes", json={"allow_remixes": "maybe"}).status_code == 400
    assert a.put(f"/api/showcase/{src['id']}/remixes", json={"allow_remixes": "yes"}).json()["can_remix"] is True


def test_bad_value_at_upload_is_400():
    a = client({"display_name": "A4", "dob": "1990-01-01"})
    assert pub(a, allow_remixes="perhaps").status_code == 400


def test_legacy_item_without_field_defaults_yes():
    from app.community import catalog
    assert catalog.allows_remixes({}) is True
    assert catalog.remix_status({"license_id": "cc-by-nd-4.0"})["can_remix"] is False
