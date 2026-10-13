"""Grooming-style phrase detection (exact list + pattern layer). Fixtures stay clean — no explicit content."""
import pytest
from app.community import safety
from app.community import moderation

# Phrases that should be refused (paraphrases / abbreviations of the child-safety list).
MUST_BLOCK = [
    "how old are you",
    "hw old r u",
    "what is your age",
    "what grade are you in",
    "where do you live",
    "where are you from",
    "where r u from",
    "what school do you go to",
    "dont tell your parents",
    "don't tell your mom",
    "keep this between us",
    "our little secret",
    "are your parents home",
    "are you alone",
    "send me a photo of yourself",
    "show me your face",
    "meet in person",
    "lets go private",
    "add me on discord",
]

# Ordinary maker / lesson talk that must still pass.
MUST_PASS = [
    "Where do I find the infill setting?",
    "What age group is this lesson for?",
    "Can you send me the STL file",
    "Lets meet at the printer after lunch",
    "Printed on 2026-10-04",
    "trade secret hinge design",
    "secret compartment for the battery",
    "ball bearing",
    "Nigeria",
    "Layer 0.2 mm, 15% infill",
]


@pytest.mark.parametrize("t", MUST_BLOCK)
def test_grooming_style_phrases_are_blocked(t):
    assert safety.scan(t) is not None, t


@pytest.mark.parametrize("t", MUST_PASS)
def test_benign_maker_talk_still_passes(t):
    assert safety.scan(t) is None, t


def test_grooming_layer_returns_language_code():
    assert safety.scan_grooming("what is your age") == "language"
    assert safety.scan_grooming("hello nozzle") is None


def test_report_underage_user_reason_exists():
    """ZEIM is 18+ only: 'Report underage user' is a first-class report reason (already wired)."""
    assert "underage_user" in moderation.REASONS
