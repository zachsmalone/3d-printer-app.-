"""Owner decision 2026-11-03 (Zach): no leftover 18+ wording on sign-up, terms or rules. The NSFW blur stays."""
from pathlib import Path

S = Path(__file__).resolve().parents[1] / "static"


def test_no_adults_only_wording_where_visitors_read():
    for f in ("community.js", "zeim-account.js", "terms.html", "COMMUNITY_GUIDELINES.html", "COMMUNITY_GUIDELINES.md"):
        t = (S / f).read_text()
        assert "18 and over" not in t and "adults 18" not in t, f
    assert "Sorry, ZEIM accounts are for adults" not in (S / "community.js").read_text()


def test_nsfw_blur_kept():
    assert "blurred" in (S / "COMMUNITY_GUIDELINES.html").read_text()
