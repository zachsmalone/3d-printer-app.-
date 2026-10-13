"""PrusaSlicer attribution is shown; docs follow the 2026-10-13 decision (ZEIM's own code stays private)."""
import re
from pathlib import Path
from tests.b1 import client

ROOT = Path(__file__).resolve().parents[1]
TEXT = "Slicing powered by PrusaSlicer (AGPL-3.0), unmodified"
LINK = 'href="https://github.com/prusa3d/PrusaSlicer"'


def _plain(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))


def test_attribution_on_credits_page_and_footer():
    r = client().get("/credits"); assert r.status_code == 200
    for html in (r.text, (ROOT / "static/index.html").read_text()):
        assert TEXT in _plain(html) and LINK in html


def test_docs_no_longer_say_zeim_source_must_be_public():
    bad = re.compile(r"ZEIM must (make|publish)[^.]*source|source code available to its users|public copy of the repository", re.I)
    for f in ("docs/licensing.md", "ROADMAP.md", "static/terms.html", "README.md"):
        assert not bad.search((ROOT / f).read_text()), f
    lic = (ROOT / "docs/licensing.md").read_text()
    assert "stays private" in lic and "not legal advice" in lic
    assert re.search(r"Nobody may modify, patch.*link PrusaSlicer", lic)
    assert "separate" in lic
