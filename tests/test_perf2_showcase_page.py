"""PERF2: /api/showcase sends one page (limit/offset, has_more) instead of every item."""
from types import SimpleNamespace
from app.api import community as c


def _run(monkeypatch, n, **kw):
    items = [{"id": f"i{k}", "ai_made": False} for k in range(n)]
    monkeypatch.setattr(c.guards, "showcase_gate", lambda a: None)
    monkeypatch.setattr(c.personalization, "get", lambda sid: {"enabled": False, "interests": {}})
    monkeypatch.setattr(c.catalog, "check_filters", lambda *a: {"mature": "hide"})
    monkeypatch.setattr(c.catalog, "hides_mature", lambda a: True)
    monkeypatch.setattr(c.catalog, "list_items", lambda *a, **k: items)
    monkeypatch.setattr(c.catalog, "apply_filters", lambda it, f, a: it)
    monkeypatch.setattr(c.catalog, "categories", lambda a: [])
    monkeypatch.setattr(c.catalog, "public", lambda i, a: i)
    monkeypatch.setattr(c, "_originals_notice", lambda: "")
    actor = SimpleNamespace(sid="s", user=None, is_adult=True)
    args = dict(tab="trending", q="", category="", sort="", ai="show", printer="", material="", supports="", licence="", mature="")
    args.update(kw)
    return c.showcase(actor=actor, **args)


def test_default_page_is_48_and_says_there_is_more(monkeypatch):
    r = _run(monkeypatch, 100)
    assert len(r["items"]) == 48 and r["has_more"] and r["result_count"] == 100


def test_offset_and_limit_are_clamped(monkeypatch):
    r = _run(monkeypatch, 100, limit=500, offset=90)
    assert len(r["items"]) == 10 and r["limit"] == 200 and not r["has_more"]
    assert len(_run(monkeypatch, 5, limit=0)["items"]) == 1


def test_small_lists_are_unchanged(monkeypatch):
    r = _run(monkeypatch, 6)
    assert len(r["items"]) == 6 and not r["has_more"]


def test_page_asks_with_a_limit_and_has_show_more():
    js = open("static/community.js").read()
    assert "&limit=${shLimit}" in js and 'id="shMore"' in js
