"""Hotfix (owner decision 2026-11-03): no 18+ gate. New visitors land on the app; sign-up needs no birth date."""
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]


def test_no_gate_markup_or_script():
    html = TestClient(app).get("/").text
    assert 'id="ageGate"' not in html and "agegate.js" not in html
    assert not (ROOT / "static" / "agegate.js").exists()


def test_signup_without_birth_date_and_with_young_date_both_work():
    assert TestClient(app).post("/api/me/signup", json={"display_name": "Maker"}).status_code == 200
    assert TestClient(app).post("/api/me/signup", json={"display_name": "Sam", "dob": "2015-01-01"}).status_code == 200


def test_privacy_page_has_no_age_check():
    p = (ROOT / "static" / "privacy.html").read_text()
    assert "age check" not in p.replace("old age check", "") and "18 and over" not in p
