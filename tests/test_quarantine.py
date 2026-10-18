"""Quarantine (launch checklist Task 4: "quarantine for suspicious uploads — don't serve until
reviewed"): uploads accepted while the malware scanner was explicitly ON but unreachable are held.

Tests cover: the hold (409 on every serving path while the scanner is down), the automatic
release (scanner back + clean re-scan), the infected verdict (422, still held), the audited
admin release, and the scanner-off default (no behavior change).
"""
from __future__ import annotations

import io
import json
import socket
import threading

import pytest

from app import config
from app.services import quarantine, uploadgate
from tests.b1 import client, photo_build


class FakeClamd:
    """A minimal clamd speaking INSTREAM over a unix socket, with a settable verdict."""

    def __init__(self, path, verdict=b"stream: OK\0"):
        self.path, self.verdict = path, verdict
        self.s = socket.socket(socket.AF_UNIX)
        self.s.bind(str(path))
        self.s.listen(4)
        self.running = True
        self.t = threading.Thread(target=self._serve, daemon=True)
        self.t.start()

    def _serve(self):
        while self.running:
            try:
                c, _ = self.s.accept()
            except OSError:
                return
            with c:
                buf = b""
                while b"zINSTREAM\0" not in buf:      # consume the command exactly
                    buf += c.recv(64)
                buf = buf.split(b"zINSTREAM\0", 1)[1]
                while True:                             # size-prefixed chunks until the zero-length terminator
                    while b"\0" not in buf:
                        buf += c.recv(64)
                    hdr, _, rest = buf.partition(b"\0")
                    buf = rest
                    try:
                        n = int(hdr, 16)
                    except ValueError:
                        return
                    if n == 0:
                        break
                    while len(buf) < n:
                        buf += c.recv(n - len(buf))
                    buf = buf[n:]
                c.sendall(self.verdict)
                c.shutdown(socket.SHUT_WR)

    def set_verdict(self, verdict: bytes):
        self.verdict = verdict

    def stop(self):
        self.running = False
        try:
            self.s.close()
        except OSError:
            pass


def _png():
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (60, 40), (9, 99, 199)).save(b, "PNG")
    return b.getvalue()


@pytest.fixture
def scan_on(monkeypatch, tmp_path):
    """ClamAV explicitly enabled, pointed at a socket that does not exist yet (scanner down)."""
    monkeypatch.setattr(config, "CLAMAV", True)
    monkeypatch.setattr(config, "CLAMAV_SOCKET", str(tmp_path / "clamd.ctl"))
    return tmp_path / "clamd.ctl"


def test_scanner_off_is_the_default_and_changes_nothing(monkeypatch):
    monkeypatch.setattr(config, "CLAMAV", False)
    checked = uploadgate.gate(_png(), "sid-q1")
    assert checked.scan_state == "off"
    c = client()
    bid = photo_build(c)
    assert quarantine.is_quarantined(bid) is False
    assert c.get(f"/api/download/{bid}/stl", follow_redirects=False).status_code in (200, 303)


def test_unreachable_scanner_holds_the_build_on_every_serving_path(scan_on):
    c = client()
    r = c.post("/api/generate", files={"file": ("photo.png", _png(), "image/png")}, data={"mode": "relief"})
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    assert quarantine.is_quarantined(bid) is True
    # the owner still sees the build's metadata
    row = [x for x in c.get("/api/builds").json()["builds"] if x["id"] == bid]
    assert row
    # ... but nothing is served, shared or printed while the scan is pending
    assert c.get(f"/api/download/{bid}/stl").status_code == 409
    assert c.get(f"/files/{bid}/model.stl").status_code == 409
    assert c.post("/api/showcase", json={"build_id": bid, "title": "x", "accept_guidelines": True,
                                         "nsfw": False, "visibility": "private"}).status_code == 409
    # and the audit trail records why
    entries = c.get("/api/moderation/audit", headers={"x-admin-token": "t0k"}).json()["entries"]
    assert any(e.get("action") == "quarantine" and e.get("item") == bid for e in entries)


def test_clean_rescan_releases_automatically(scan_on):
    c = client()
    # upload while the scanner is down -> quarantined
    r = c.post("/api/generate", files={"file": ("photo.png", _png(), "image/png")}, data={"mode": "relief"})
    bid = r.json()["id"]
    assert quarantine.is_quarantined(bid) is True
    clamd = FakeClamd(scan_on, b"stream: OK\0")          # scanner is back
    d = c.get(f"/api/download/{bid}/stl")
    assert d.status_code in (200, 303), d.text          # first serving attempt re-scans clean and proceeds
    assert quarantine.is_quarantined(bid) is False       # ...and the hold is lifted
    clamd.stop()


def test_infected_rescan_keeps_the_hold(scan_on):
    # upload while the scanner is down -> quarantined; scanner comes back and flags it on re-scan
    c = client()
    r = c.post("/api/generate", files={"file": ("photo.png", _png(), "image/png")}, data={"mode": "relief"})
    bid = r.json()["id"]
    clamd = FakeClamd(scan_on, b"stream: Eicar-Test-Signature FOUND\0")
    assert c.get(f"/api/download/{bid}/stl").status_code == 422
    assert quarantine.is_quarantined(bid) is True        # still held
    clamd.stop()


def test_infected_upload_is_refused_at_the_gate_never_stored(scan_on):
    clamd = FakeClamd(scan_on, b"stream: Eicar-Test-Signature FOUND\0")
    c = client()
    r = c.post("/api/generate", files={"file": ("photo.png", _png(), "image/png")}, data={"mode": "relief"})
    assert r.status_code == 415                          # refused; nothing was stored
    assert "Nothing about it was stored" in r.json()["detail"]
    assert c.get("/api/builds").json()["builds"] == []    # no build exists
    clamd.stop()


def test_admin_release_is_audited_and_unlocks(scan_on):
    c = client()
    r = c.post("/api/generate", files={"file": ("photo.png", _png(), "image/png")}, data={"mode": "relief"})
    bid = r.json()["id"]
    # wrong token is refused
    assert c.post(f"/api/moderation/release-quarantine/{bid}", headers={"x-admin-token": "nope"}).status_code == 403
    ok = c.post(f"/api/moderation/release-quarantine/{bid}", headers={"x-admin-token": "t0k"})
    assert ok.status_code == 200 and ok.json()["ok"] is True
    assert quarantine.is_quarantined(bid) is False
    assert c.get(f"/api/download/{bid}/stl", follow_redirects=False).status_code in (200, 303)
    entries = c.get("/api/moderation/audit", headers={"x-admin-token": "t0k"}).json()["entries"]
    assert any(e.get("action") == "quarantine_release" and e.get("item") == bid for e in entries)
    # releasing something not quarantined is a 404, not an error
    assert c.post(f"/api/moderation/release-quarantine/{bid}", headers={"x-admin-token": "t0k"}).status_code == 404
