"""TASK26: the service worker caches static files only, never pages or the API, and its cache name changes per deploy."""
import re
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app, SW_VERSION

c = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_sw_is_served_from_root_and_never_cached():
    r = c.get("/sw.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert "no-store" in r.headers["cache-control"]
    assert f'"zeim-static-{SW_VERSION}"' in r.text and "__VERSION__" not in r.text


def test_old_caches_are_deleted_and_only_static_is_cached():
    js = c.get("/sw.js").text
    assert "caches.delete(k)" in js and "k !== CACHE" in js
    assert "skipWaiting" in js and "clients.claim" in js
    assert js.count(".put(") == 1                     # one place writes to the cache...
    put_block = js[js.index('startsWith("/static/")'):js.index("r.mode === \"navigate\"")]
    assert ".put(" in put_block                       # ...and it is the /static/ branch
    assert "fetch(r, {cache:\"reload\"}).then" in put_block  # network first, skip HTTP cache, cache only as fallback


def test_version_changes_each_start(monkeypatch):
    import importlib, app.main as m
    v1 = m._sw_version(); v2 = m._sw_version()
    assert v1 != v2 and re.fullmatch(r"[0-9a-f]{12}", v1)


def test_pages_register_it():
    for p in ("static/index.html", "static/cad.html"):
        assert '/static/sw-register.js' in (ROOT / p).read_text()
    assert 'register("/sw.js"' in (ROOT / "static/sw-register.js").read_text()
