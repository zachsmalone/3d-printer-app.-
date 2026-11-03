"""RET3: the approved privacy page (no draft banner) keeps the claims checked against the code."""
import pathlib
P = (pathlib.Path(__file__).resolve().parents[1] / "static" / "privacy.html").read_text()


def test_approved_and_matches_code_facts():
    assert "draftnote" not in P and "<strong>Draft.</strong>" not in P
    assert "removed after 30 days" in P and "Starred builds" in P          # retention.py
    assert "never stores the address itself" in P                          # auth/store.py email_hash
    assert "no third-party trackers" in P
