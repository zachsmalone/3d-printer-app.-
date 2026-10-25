"""ZeimFeedback: the address stays on the server, and a missing mailer is an honest save."""
import json
from pathlib import Path

from app import config
from app.api import feedback as fb
from tests.b1 import client


def test_address_is_not_in_the_page_or_the_response():
    blob = []
    for p in Path("static").rglob("*"):
        if p.suffix.lower() in {".js", ".html", ".css"} and p.is_file():
            blob.append(p.read_text(encoding="utf-8", errors="ignore"))
    assert fb.DESTINATION not in "\n".join(blob)
    c = client()
    r = c.post("/api/feedback", json={"message": "The FDM button was confusing", "email": "person@example.com", "from": "person@example.com"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["emailed"] is False
    assert fb.DESTINATION not in r.text
    assert "not been emailed" in body["message"]
    saved = list((config.DATA / "feedback").glob("*.json"))
    assert saved
    rec = json.loads(saved[-1].read_text())
    assert rec["text"].startswith("The FDM")
    assert rec["who"] == "guest"
    dumped = json.dumps(rec)
    assert "person@example.com" not in dumped and fb.DESTINATION not in dumped


def test_working_mailer_sends_without_echoing_the_address(monkeypatch):
    sent = []

    class Fake:
        def send(self, to, subject, text):
            sent.append((to, subject, text))

    monkeypatch.setattr(fb, "mailer_from_env", lambda env: Fake())
    r = client().post("/api/feedback", json={"message": "Hello from a maker"})
    assert r.status_code == 200, r.text
    assert r.json()["emailed"] is True
    assert fb.DESTINATION not in r.text
    assert sent[0][0] == fb.DESTINATION
    assert "guest" in sent[0][2] and "Hello from a maker" in sent[0][2]


def test_empty_feedback_is_refused():
    assert client().post("/api/feedback", json={"message": "   "}).status_code == 400
