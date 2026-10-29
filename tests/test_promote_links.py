"""Promote your accounts: public links, no server-setup text, Connect only when keys exist."""
from pathlib import Path

import pytest

from app.community import links
from app.services import accounts
from tests.b1 import ADULT, client, photo_build

ROOT = Path(__file__).resolve().parents[1]
PAGES = ("/", "/static/app.js", "/static/community.js", "/static/send.js", "/static/agegate.js", "/workbench/")
BANNED = ("PHOTO3D_", "restart the server", "Scaffolding", "not implemented", "Not configured")


def test_rendered_pages_hide_setup_text():
    c = client()
    blobs = [c.get(path).text for path in PAGES]
    blobs.append(c.get("/api/accounts").text)
    home = blobs[0]
    for phrase in BANNED:
        for path, blob in zip(PAGES + ("/api/accounts",), blobs):
            assert phrase not in blob, (path, phrase)
    assert "Coming soon" not in home
    assert "Coming soon" not in blobs[1]
    assert "Coming soon" not in blobs[2]
    js = (ROOT / "static/app.js").read_text(encoding="utf-8")
    assert "p.can_connect" in js and "env_vars" not in js
    assert 'data-clear="' in js and ">Remove</button>" in js
    assert ">Save</button>" in (ROOT / "static/index.html").read_text(encoding="utf-8")


def test_handles_and_links_normalize():
    assert links.clean({"tiktok": "@maker.one"})["tiktok"]["url"] == "https://www.tiktok.com/@maker.one"
    assert links.clean({"tiktok": "https://www.tiktok.com/@maker.one"})["tiktok"]["url"] == "https://www.tiktok.com/@maker.one"
    assert links.clean({"instagram": "maker.fan"})["instagram"]["url"] == "https://www.instagram.com/maker.fan"
    assert links.clean({"reddit": "https://old.reddit.com/user/maker_one"})["reddit"]["url"] == "https://www.reddit.com/user/maker_one"
    assert links.clean({"patreon": "desk-lamp"})["patreon"]["url"] == "https://www.patreon.com/desk-lamp"
    assert links.clean({"youtube": "@ZeimPrints"})["youtube"]["url"] == "https://www.youtube.com/@ZeimPrints"
    channel = "UC" + "a" * 22
    assert links.clean({"youtube": f"https://youtube.com/channel/{channel}"})["youtube"]["url"] == f"https://www.youtube.com/channel/{channel}"
    assert links.clean({"x": "https://twitter.com/ZeimApp"})["x"]["url"] == "https://x.com/ZeimApp"
    assert links.clean({"website": "http://www.Example.com/about"})["website"]["url"] == "https://example.com/about"
    assert links.clean({"tiktok": "  "}) == {}
    with pytest.raises(ValueError):
        links.clean({"tiktok": "bad handle!"})
    with pytest.raises(ValueError):
        links.clean({"tiktok": "https://www.tiktok.com/@maker.one/video/1"})
    with pytest.raises(ValueError):
        links.clean({"youtube": "https://youtu.be/abc"})
    with pytest.raises(ValueError):
        links.clean({"website": "javascript:alert(1)"})
    with pytest.raises(ValueError):
        links.clean({"nope": "maker"})


def test_links_show_on_the_profile_and_on_a_post(monkeypatch):
    monkeypatch.delenv("PHOTO3D_REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("PHOTO3D_REDDIT_CLIENT_SECRET", raising=False)
    maker = client(ADULT)
    saved = maker.put("/api/me/links", json={
        "tiktok": "@lamp.maker",
        "instagram": "https://www.instagram.com/lamp.maker",
        "x": "lamp_maker",
        "website": "https://lamps.example/about",
        "reddit": "",
    })
    assert saved.status_code == 200, saved.text
    urls = {k: v["url"] for k, v in saved.json()["links"].items()}
    assert urls["tiktok"] == "https://www.tiktok.com/@lamp.maker"
    assert urls["instagram"] == "https://www.instagram.com/lamp.maker"
    assert urls["x"] == "https://x.com/lamp_maker"
    assert urls["website"] == "https://lamps.example/about"
    assert "reddit" not in urls
    me = maker.get("/api/me").json()
    page = client().get(f"/u/{me['id']}")
    assert page.status_code == 200, page.text
    assert 'rel="noopener nofollow ugc"' in page.text
    assert 'href="https://www.tiktok.com/@lamp.maker"' in page.text
    assert 'aria-label="TikTok"' in page.text
    assert "PHOTO3D_" not in page.text
    item = maker.post("/api/showcase", json={
        "build_id": photo_build(maker), "title": "Linked lamp", "description": "d", "tags": ["lamp"],
        "accept_guidelines": True, "nsfw": False, "visibility": "public", "license_id": "cc-by-4.0",
    })
    assert item.status_code == 200, item.text
    shown = {row["id"]: row["url"] for row in item.json()["creator_links"]}
    assert shown["tiktok"] == urls["tiktok"]
    post = client().get(f"/p/{item.json()['id']}")
    assert 'href="https://x.com/lamp_maker"' in post.text
    assert 'rel="noopener nofollow ugc"' in post.text
    gone = maker.put("/api/me/links", json={"tiktok": "", "x": "lamp_maker"})
    assert gone.status_code == 200 and "tiktok" not in gone.json()["links"] and "x" in gone.json()["links"]


def test_connect_appears_only_when_that_platform_has_keys(monkeypatch):
    for name in ("TIKTOK", "INSTAGRAM", "REDDIT", "PATREON"):
        monkeypatch.delenv(f"PHOTO3D_{name}_CLIENT_ID", raising=False)
        monkeypatch.delenv(f"PHOTO3D_{name}_CLIENT_SECRET", raising=False)
    assert accounts.status() == [
        {"id": "tiktok", "label": "TikTok", "can_connect": False, "connected": False},
        {"id": "instagram", "label": "Instagram", "can_connect": False, "connected": False},
        {"id": "reddit", "label": "Reddit", "can_connect": False, "connected": False},
        {"id": "patreon", "label": "Patreon", "can_connect": False, "connected": False},
    ]
    assert client().get("/api/accounts").json()["providers"] == []
    monkeypatch.setenv("PHOTO3D_TIKTOK_CLIENT_ID", "app-id")
    monkeypatch.setenv("PHOTO3D_TIKTOK_CLIENT_SECRET", "app-secret")
    rows = client().get("/api/accounts").json()["providers"]
    assert rows == [{"id": "tiktok", "label": "TikTok", "can_connect": True, "connected": False}]
    assert "PHOTO3D_" not in client().get("/api/accounts").text
