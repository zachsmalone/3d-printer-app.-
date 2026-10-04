"""Tunnel-gate items: signed /f/ links are scoped to one file and short-lived, redacted in logs, and need a configured
public address on a shared server."""
import logging, time
from app import config
from app.community import privacy
from app.main import app
from tests import b1


def _setup():
    c = b1.client(b1.ADULT)
    return c, b1.photo_build(c)


def _tok_url(c, bid, fmt):
    sl = {s["format"]: s for s in c.get(f"/api/print/{bid}/links").json()["slicers"]}
    return sl[fmt]["file_url"].replace("http://testserver", "")


def test_token_is_scoped_to_one_file():
    c, bid = _setup()
    u3 = _tok_url(c, bid, "3mf")
    other = b1.client()
    assert other.get(u3).status_code == 200
    # same token, different file of the SAME build -> refused
    assert other.get(u3.replace("model.3mf", "model.stl")).status_code == 404
    assert other.get(u3.replace("model.3mf", "thumb.png")).status_code == 404


def test_token_lifetime_is_ten_minutes_not_two_hours():
    assert privacy.LINK_TTL <= 10 * 60
    t = privacy.make_token("abc", "model.3mf")
    assert int(t.split("-")[0]) - time.time() <= 10 * 60 + 2
    assert privacy.check_token("abc", "model.3mf", t) and not privacy.check_token("abc", "model.stl", t)
    assert not privacy.check_token("abc", "model.3mf", privacy.make_token("abc", "model.3mf", ttl=-5))


def test_tokens_are_redacted_in_the_access_log():
    f = [x for x in logging.getLogger("uvicorn.access").filters if type(x).__name__ == "RedactTokens"]
    assert f, "redaction filter not installed"
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                            ("1.2.3.4:5", "GET", "/f/1790000000-deadbeef/abc123/model.3mf", "1.1", 200), None)
    f[0].filter(rec)
    out = rec.getMessage()
    assert "deadbeef" not in out and "/f/[redacted]/abc123/model.3mf" in out


def test_shared_mode_needs_public_base_url_for_slicer_links(monkeypatch):
    c, bid = _setup()
    monkeypatch.setattr(config, "MODE", "shared")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "")
    j = c.get(f"/api/print/{bid}/links")
    assert j.status_code == 200
    d = j.json()
    assert d["slicers"] == [] and "public address" in d["slicer_links_disabled"]
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://zeim.example.org")
    d = c.get(f"/api/print/{bid}/links").json()
    assert d["slicers"] and d["slicers"][0]["file_url"].startswith("https://zeim.example.org/f/")
