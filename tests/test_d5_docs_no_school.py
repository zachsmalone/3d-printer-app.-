"""Docs (2026-10-13): README and ROADMAP keep only ONE short 'school features removed' note each - no leftover school/classroom/
teacher plans (rosters, LMS, FERPA, class codes, kid onboarding). ZEIM is 18+ only."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEFTOVER = re.compile(r"classroom|teacher tools?|class codes?|roster|\bLMS\b|FERPA|district|kid onboarding|not for school use|students?", re.I)


def test_docs_have_no_leftover_school_plans():
    for name in ("README.md", "ROADMAP.md"):
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            assert not LEFTOVER.search(line), (name, line)


def test_school_is_mentioned_only_as_removed_and_docs_say_18_plus():
    for name in ("README.md", "ROADMAP.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "18+" in text, name
        hits = [ln for ln in text.splitlines() if re.search(r"school|teacher", ln, re.I)]
        assert len(hits) <= 4, (name, hits)
        for ln in hits:
            assert re.search(r"\bno\b|removed", ln, re.I), (name, ln)
