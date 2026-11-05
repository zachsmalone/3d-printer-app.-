"""Hotfix (owner decision 2026-11-03): no 18+ gate. New visitors land on the app; sign-up needs no birth date.

Leftover gate pieces (the overlay script, its CSS, /api/me/adult, and the PHOTO3D_AGE_GATE switch) stay gone.
NSFW blur and the Mature content label stay.
"""
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.community import challenges
from app.community.store import CHALLENGES
from app.main import app

ROOT = Path(__file__).resolve().parents[1]


def test_no_gate_markup_or_script():
    html = TestClient(app).get("/").text
    assert 'id="ageGate"' not in html and "agegate.js" not in html and "data-agegate" not in html
    assert not (ROOT / "static" / "agegate.js").exists()
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert ".agegate" not in css and "html.gated" not in css
    assert ".ph.nsfw img" in css and "Mature content" in (ROOT / "static" / "moderation.js").read_text(encoding="utf-8")
    assert not hasattr(config, "AGE_GATE") and not hasattr(config, "MIN_SIGNUP_AGE")
    c = TestClient(app)
    assert c.get("/api/me/adult").status_code == 404
    assert c.put("/api/me/adult", json={"adult": True}).status_code == 404
    assert "18+ only" not in (ROOT / "static" / "moderation.js").read_text(encoding="utf-8")
    assert "18+ only" not in (ROOT / "app" / "api" / "community.py").read_text(encoding="utf-8")
    assert "rm -f static/agegate.js" in (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_signup_without_birth_date_and_with_young_date_both_work():
    assert TestClient(app).post("/api/me/signup", json={"display_name": "Maker"}).status_code == 200
    assert TestClient(app).post("/api/me/signup", json={"display_name": "Sam", "dob": "2015-01-01"}).status_code == 200


def test_privacy_page_has_no_age_check():
    p = (ROOT / "static" / "privacy.html").read_text()
    assert "age check" not in p.replace("old age check", "") and "18 and over" not in p


def test_challenge_rules_keep_the_guidelines_line_only():
    for rules in (challenges.REMIX["rules"], challenges.XMAS["rules"]):
        assert "18+ only" not in " ".join(rules)
        assert "Keep it within the Community Guidelines." in rules
    saved = CHALLENGES.read()
    CHALLENGES.write([{
        "id": challenges.REMIX_ID,
        "status": "open",
        "rules": ["18+ only. Keep it within the Community Guidelines.", "Prize-free: ZEIM offers no cash or prizes for this challenge."],
    }])
    try:
        got = challenges.get(challenges.REMIX_ID)
        assert got["status"] == "closed"
        assert "18+ only" not in " ".join(got["rules"])
        assert "Keep it within the Community Guidelines." in got["rules"]
    finally:
        CHALLENGES.write(saved)
