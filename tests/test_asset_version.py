"""JS and CSS URLs carry a per-deploy version so a phone does not keep an old module after a release."""
import json
from fastapi.testclient import TestClient

from app import assets
from app.assets import ASSET_VERSION, stamp_html
from app.main import app

def test_homepage_scripts_and_styles_are_versioned_and_html_stays_no_cache():
    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"
    html = r.text
    assert f'src="/static/community.js?v={ASSET_VERSION}"' in html
    # showcase-open.js is imported from community.js, so it is remapped rather than a <script src>.
    assert f'src="/static/boot.js?v={ASSET_VERSION}"' in html
    assert f'href="/static/style.css?v={ASSET_VERSION}"' in html or f'href="/static/zeim-b2.css?v={ASSET_VERSION}"' in html
    # Import map sends every /static/*.js specifier (including relative imports) to the same version.
    start = html.index('<script type="importmap">') + len('<script type="importmap">')
    end = html.index("</script>", start)
    imports = json.loads(html[start:end])["imports"]
    assert imports["/static/community.js"] == f"/static/community.js?v={ASSET_VERSION}"
    assert imports["/static/showcase-open.js"] == f"/static/showcase-open.js?v={ASSET_VERSION}"
    assert imports["three"].endswith(f"?v={ASSET_VERSION}")
    # Stamped CSP still covers every inline script on the page (the import map body changed).
    csp = r.headers["content-security-policy"]
    assert "script-src 'self' 'sha256-" in csp and "unsafe-eval" not in csp


def test_unversioned_js_stays_no_cache_and_matching_v_may_be_cached():
    c = TestClient(app)
    raw = c.get("/static/community.js")
    assert raw.status_code == 200 and raw.headers["cache-control"] == "no-cache"
    good = c.get(f"/static/community.js?v={ASSET_VERSION}")
    assert good.status_code == 200
    assert good.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert good.content == raw.content
    stale = c.get("/static/community.js?v=deadbeef0000")
    assert stale.status_code == 200 and stale.headers["cache-control"] == "no-cache"


def test_stamp_is_idempotent_and_prefers_deploy_sha(tmp_path, monkeypatch):
    src = '<html><head><script type="importmap">{"imports":{"three":"/static/vendor/three.module.min.js"}}</script></head><body><script type="module" src="/static/community.js"></script></body></html>'
    once = stamp_html(src, ver="abcdef123456")
    twice = stamp_html(once, ver="abcdef123456")
    assert once == twice
    assert once.count("?v=abcdef123456") >= 2
    assert '"three":"/static/vendor/three.module.min.js?v=abcdef123456"' in once.replace(" ", "")

    sha = tmp_path / ".deploy-sha"
    sha.write_text("2ad20969438beb8c3d756bfeb0aa0ed2a8206348\n", encoding="utf-8")
    monkeypatch.setattr(assets, "ROOT", tmp_path)
    assert assets._deploy_sha() == "2ad20969438b"
    assert assets.asset_version() == "2ad20969438b"


def test_coming_soon_page_is_not_rewritten(monkeypatch):
    from app import config
    monkeypatch.setenv("ZEIM_COMING_SOON", "1")
    assert config.coming_soon_enabled() is True
    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert "ZEIM is almost ready" in r.text
    assert "importmap" not in r.text
    assert "?v=" not in r.text
    assert "no-store" in r.headers["cache-control"]
