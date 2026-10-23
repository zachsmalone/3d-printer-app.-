"""Opt-in design integration: same CSP, local assets, unchanged original homepage."""
import re
from pathlib import Path
from tests.b1 import client
from app.config import STATIC
from app.main import CSP


def test_workbench_redirect_and_original_homepage():
    c = client()
    r = c.get("/workbench", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/workbench/"
    # unchanged apart from A's test-only age-gate switch (conftest sets PHOTO3D_AGE_GATE=0)
    from app import config
    want = (STATIC / "index.html").read_bytes()
    if not config.AGE_GATE:
        want = want.replace(b'<html lang="en">', b'<html lang="en" data-agegate="off">', 1)
    assert c.get("/").content == want


def test_workbench_html_uses_only_same_origin_runtime_assets():
    r = client().get("/workbench/")
    assert r.status_code == 200
    assert "ZEIM · Perplexity workbench" in r.text
    assert r.headers["content-security-policy"] == CSP
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-robots-tag"] == "noindex, nofollow"
    assert r.headers["x-frame-options"] == "DENY"
    assert "api.fontshare.com" not in r.text
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", r.text)
    assert 'src="/static/perplexity-workbench/app.js"' in r.text
    assert 'href="/static/perplexity-workbench/style.css"' in r.text
    assert 'src="/static/logo-header.png"' in r.text
    assert 'aria-label="Return to the original ZEIM app"' in r.text


def test_workbench_assets_fonts_and_notices_are_packaged_and_cache_safe():
    c = client()
    for path in ("app.js", "style.css", "build-info.json",
                 "fonts/manrope-latin-400-normal.woff2",
                 "fonts/manrope-latin-500-normal.woff2",
                 "fonts/manrope-latin-700-normal.woff2",
                 "licenses/three-MIT.txt", "licenses/lucide-ISC.txt",
                 "licenses/manrope-OFL.txt"):
        r = c.get("/static/perplexity-workbench/" + path)
        assert r.status_code == 200, path
        assert r.headers["cache-control"] == "no-cache", path
        assert r.headers["content-security-policy"] == CSP, path
    assert "http" not in c.get("/static/perplexity-workbench/style.css").text
    assert c.post("/workbench/").status_code == 405


def test_provenance_and_editable_source_exist():
    root = Path(__file__).resolve().parent.parent
    for path in ("workbench/perplexity/src/app.js", "workbench/perplexity/src/geometry.js",
                 "workbench/perplexity/package-lock.json",
                 "docs/design/perplexity/REA-ArtCraft.md"):
        assert (root / path).is_file(), path
