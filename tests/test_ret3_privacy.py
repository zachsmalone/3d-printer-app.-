"""RET3: the privacy page is marked as a draft and keeps the claims checked against the code."""
import pathlib
P = (pathlib.Path(__file__).resolve().parents[1] / "static" / "privacy.html").read_text()


def test_marked_draft_and_matches_code_facts():
    assert 'class="draftnote"' in P
    assert "removed after 30 days" in P and "Starred builds" in P          # retention.py
    assert "never stores the address itself" in P                          # auth/store.py email_hash
    assert "no third-party trackers" in P
