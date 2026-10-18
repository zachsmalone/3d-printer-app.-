"""Quarantine (launch checklist Task 4: "quarantine for suspicious uploads — don't serve until
reviewed") — the pending-upload architecture:

  * scanner off (default): uploads behave exactly as before;
  * scanner on + clean: normal build;
  * scanner on + INFECTED: refused at the gate, never stored;
  * scanner on + UNREACHABLE (or an unusable verdict): the upload is NOT built — no artifacts,
    no metadata, nothing served or published. The original bytes + request context are parked in
    restricted pending storage (0700), and /api/uploads/resume re-runs the FULL pipeline once a
    scan clears them. Infected-on-resume discards it. Admins can list and discard pending uploads.
"""
from __future__ import annotations

import io
import json
import socket
import threading

import pytest

from app import config
from app.services import quarantine, uploadgate
from app.services.history import store
from tests.b1 import client, photo_build
from tests.test_objectstore import _FakeS3, s3  # noqa: F401 — the s3 fixture registers on import


class FakeClamd:
    """A minimal clamd speaking the spec INSTREAM protocol (4-byte BE lengths) over a unix socket."""

    def __init__(self, path, verdict=b"stream: OK\0"):
        self.path, self.verdict = path, verdict
        self.s = socket.socket(socket.AF_UNIX)
        self.s.bind(str(path))
        self.s.listen(4)
        self.running = True
        self.t = threading.Thread(target=self._serve, daemon=True)
        self.t.start()

    def _serve(self):
        import struct
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
                while True:                             # <4-byte BE length><data>, zero-length terminator
                    while len(buf) < 4:
                        buf += c.recv(64)
                    (n,) = struct.unpack("!I", buf[:4])
                    buf = buf[4:]
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
        import os as _os
        try:
            _os.unlink(self.path)
        except OSError:
            pass


def _png():
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (60, 40), (9, 99, 199)).save(b, "PNG")
    return b.getvalue()


def _gen(c, **form):
    return c.post("/api/generate", files={"file": ("photo.png", _png(), "image/png")},
                  data={"mode": "relief", **form})


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
    assert c.get(f"/api/download/{bid}/stl", follow_redirects=False).status_code in (200, 303)


def test_unreachable_scanner_parks_the_upload_no_build_nothing_served(scan_on):
    c = client()
    r = _gen(c)
    assert r.status_code == 202 and r.json()["status"] == "pending_scan", r.text
    pid = r.json()["pending_id"]
    # NO build was created: no artifacts, no metadata, no history entry
    assert c.get("/api/builds").json()["builds"] == []
    assert quarantine.pending_bytes(pid) == _png()      # the original bytes are held, intact
    # the pending upload is not servable by any path (there is nothing to serve)
    assert c.get(f"/api/download/{pid}/stl").status_code in (403, 404)
    # resume while the scanner is STILL down: still pending, still no build
    r2 = c.post(f"/api/uploads/resume/{pid}")
    assert r2.status_code == 202 and r2.json()["status"] == "pending_scan"
    assert c.get("/api/builds").json()["builds"] == []


def test_resume_after_clean_scan_builds_normally(scan_on):
    c = client()
    r = _gen(c, title="Keepsake")
    pid = r.json()["pending_id"]
    clamd = FakeClamd(scan_on, b"stream: OK\0")          # scanner is back
    out = c.post(f"/api/uploads/resume/{pid}")
    assert out.status_code == 200, out.text               # the FULL pipeline ran, gate re-checked
    bid = out.json()["id"]
    assert out.json()["title"] == "Keepsake"             # the stored request context replayed
    assert c.get(f"/api/download/{bid}/stl", follow_redirects=False).status_code in (200, 303)
    # the pending upload is consumed: a second resume is a 404
    assert c.post(f"/api/uploads/resume/{pid}").status_code == 404
    clamd.stop()


def test_resume_after_infected_scan_discards_and_never_builds(scan_on):
    c = client()
    r = _gen(c)
    pid = r.json()["pending_id"]
    clamd = FakeClamd(scan_on, b"stream: Eicar-Test-Signature FOUND\0")
    out = c.post(f"/api/uploads/resume/{pid}")
    assert out.status_code == 422                        # flagged: discarded, nothing kept
    assert c.get("/api/builds").json()["builds"] == []   # no build exists
    assert c.post(f"/api/uploads/resume/{pid}").status_code == 404   # the pending record is gone
    clamd.stop()


def test_infected_upload_is_refused_at_the_gate_never_stored(scan_on):
    clamd = FakeClamd(scan_on, b"stream: Eicar-Test-Signature FOUND\0")
    c = client()
    before = {p["id"] for p in quarantine.list_pending()}    # baseline: earlier tests may have parked uploads
    r = _gen(c)
    assert r.status_code == 415                          # refused; nothing was stored
    assert "Nothing about it was stored" in r.json()["detail"]
    assert c.get("/api/builds").json()["builds"] == []
    after = {p["id"] for p in quarantine.list_pending()}
    assert not (after - before)                            # and nothing new was parked either
    clamd.stop()


def test_error_or_malformed_clamd_replies_hold_the_upload(scan_on):
    # an ERROR/unknown reply is NOT a clean verdict: parked as pending, never trusted
    for bad in (b"ERROR: could not read file\0", b"garbage\0"):
        clamd = FakeClamd(scan_on, bad)
        c = client()
        r = _gen(c)
        assert r.status_code == 202 and r.json()["status"] == "pending_scan"
        clamd.stop()


def test_not_ok_error_reply_and_unterminated_reply_are_not_clean(scan_on):
    # "ERROR: NOT OK" must NOT be accepted as success, a reply missing its NUL terminator
    # (cut off mid-verdict) is not a verdict at all, and "ERROR: OK"/"garbage: OK" are not
    # whitelisted success replies
    for bad in (b"ERROR: NOT OK\0", b"stream: OK", b"ERROR: OK\0", b"garbage: OK\0"):
        clamd = FakeClamd(scan_on, bad)
        c = client()
        r = _gen(c)
        assert r.status_code == 202 and r.json()["status"] == "pending_scan", bad
        clamd.stop()


def test_resume_is_owner_only(scan_on):
    c = client()
    r = _gen(c)
    pid = r.json()["pending_id"]
    other = client()
    assert other.post(f"/api/uploads/resume/{pid}").status_code == 404   # not yours: invisible


def test_admin_pending_endpoints_are_audited(scan_on):
    c = client()
    r = _gen(c)
    pid = r.json()["pending_id"]
    # auth required
    assert c.get("/api/moderation/pending-uploads").status_code == 403
    assert c.delete(f"/api/moderation/pending-uploads/{pid}").status_code == 403
    lst = c.get("/api/moderation/pending-uploads", headers={"x-admin-token": "t0k"})
    assert lst.status_code == 200 and any(p["id"] == pid for p in lst.json()["pending"])
    d = c.delete(f"/api/moderation/pending-uploads/{pid}", headers={"x-admin-token": "t0k"})
    assert d.status_code == 200 and d.json()["ok"] is True
    assert c.post(f"/api/uploads/resume/{pid}").status_code == 404         # discarded is gone
    entries = c.get("/api/moderation/audit", headers={"x-admin-token": "t0k"}).json()["entries"]
    assert any(e.get("action") == "pending_discard" and e.get("item") == pid for e in entries)


def test_pending_upload_is_not_published_to_object_storage(s3, scan_on):
    """With S3 configured, a pending upload never reaches the bucket (there is nothing to mirror)."""
    c = client()
    r = _gen(c)
    assert r.status_code == 202
    pid = r.json()["pending_id"]
    assert not [k for k in _FakeS3.objects if pid in k or "builds/" in k]


def test_admin_metrics_require_the_admin_token():
    """The metrics endpoint is admin-only (the /healthz liveness probe stays public)."""
    c = client()
    assert c.get("/healthz").status_code == 200                      # liveness: no auth
    assert c.get("/api/admin/metrics").status_code == 403           # no token
    assert c.get("/api/admin/metrics", headers={"x-admin-token": "wrong"}).status_code == 403
    ok = c.get("/api/admin/metrics", headers={"x-admin-token": "t0k"})
    assert ok.status_code == 200
    body = ok.json()
    assert {"moderation", "quarantined_builds", "storage", "slicing", "disk_free_mb"} <= set(body)
    assert {"open_reports", "oldest_open_age_s"} <= set(body["moderation"])
    assert {"total", "failures"} <= set(body["slicing"])


def test_slicing_stats_record_success_and_failure():
    from app.services import slicestats
    slicestats.record(True)
    before = slicestats.snapshot()
    try:
        raise ValueError("boom")
    except ValueError:
        slicestats.record(False, "boom")
    after = slicestats.snapshot()
    assert after["total"] == before["total"] + 1
    assert after["failures"] == before["failures"] + 1
    assert after["last_error"] == "boom"


def test_slicing_metrics_count_success_and_failure_through_the_real_api(monkeypatch):
    """One REAL successful slice and one REAL failure through POST /api/slice — both outcomes
    asserted, no conditionals."""
    from app.services import slicestats, slicer
    from app.api import printing
    if not slicer.status()["available"]:
        pytest.skip("PrusaSlicer unavailable in this environment")
    c = client()
    bid = photo_build(c)
    before = slicestats.snapshot()
    r = c.post(f"/api/slice/{bid}", data={"layer_height": 0.2, "fill_density": 15})
    assert r.status_code == 200 and (r.json().get("ok") or "download" in r.json()), r.text
    mid = slicestats.snapshot()
    assert mid["total"] == before["total"] + 1                        # the success is counted
    assert mid["failures"] == before["failures"]

    def boom(*a, **k):
        raise RuntimeError("slicer exploded")
    monkeypatch.setattr(printing, "_slice_inner", boom)               # inject a slice failure
    with pytest.raises(RuntimeError):
        c.post(f"/api/slice/{bid}", data={"layer_height": 0.2, "fill_density": 15})
    after = slicestats.snapshot()
    assert after["total"] == mid["total"] + 1                         # the failure is counted
    assert after["failures"] == mid["failures"] + 1


def test_invalid_pending_ids_cannot_reach_the_filesystem(scan_on):
    """Pending ids are validated at every service boundary: path tricks never reach a path
    join or rmtree."""
    c = client()
    r = _gen(c)
    pid = r.json()["pending_id"]
    for bad in ("..", "../evil", "a" * 13, "x" * 11, "abc/def", "PASSWD"):
        assert quarantine.discard_pending(bad, "test") is False
        assert quarantine.pending_context(bad) is None
        assert quarantine.pending_bytes(bad) is None
        assert c.post(f"/api/uploads/resume/{bad}").status_code == 404
        assert c.delete(f"/api/moderation/pending-uploads/{bad}",
                        headers={"x-admin-token": "t0k"}).status_code == 404
    # the real pending upload is untouched by all of those attempts
    assert quarantine.pending_bytes(pid) == _png()


def test_resume_failure_retains_the_pending_upload(monkeypatch, scan_on):
    """If generation fails after a clean scan (history full, storage error), the pending upload
    is RETAINED — the user can retry. It is consumed only on success or a validated rejection."""
    c = client()
    r = _gen(c, title="Retry me")          # scanner DOWN at upload: parked
    pid = r.json()["pending_id"]
    clamd = FakeClamd(scan_on, b"stream: OK\0")          # scanner is back, clean
    # force every generate to fail: history full (limit 0 => nothing can be reserved)
    monkeypatch.setattr(store, "limit", 0)
    refused = c.post(f"/api/uploads/resume/{pid}")
    assert refused.status_code == 409                                 # the pipeline refused to build
    assert quarantine.pending_bytes(pid) == _png()                   # retained, not consumed
    monkeypatch.setattr(store, "limit", 20)
    out = c.post(f"/api/uploads/resume/{pid}")                       # retry: now it works
    assert out.status_code == 200 and out.json()["title"] == "Retry me"
    assert c.post(f"/api/uploads/resume/{pid}").status_code == 404   # consumed by the success
    clamd.stop()


def test_staged_context_replays_nondefault_fields(scan_on):
    """The stored request context replays the EXACT original request: numeric, boolean and
    mode-specific fields, not just the title."""
    c = client()
    r = _gen(c, title="Ctx test", width_mm=123.5, resolution=150, invert=True,
             base_mm=4.5, relief_mm=2.5)    # scanner DOWN at upload: parked
    assert r.status_code == 202
    pid = r.json()["pending_id"]
    clamd = FakeClamd(scan_on, b"stream: OK\0")          # scanner is back, clean
    out = c.post(f"/api/uploads/resume/{pid}")
    assert out.status_code == 200, out.text
    params = out.json()["params"]
    assert params["width_mm"] == 123.5
    assert params["resolution"] == 150
    assert params["invert"] is True
    assert params["base_mm"] == 4.5
    assert params["relief_mm"] == 2.5
    clamd.stop()


def test_user_erasure_removes_pending_uploads_too(scan_on):
    """"'Delete everything I made' covers parked (scanner-down) uploads: both the original
    bytes and the request context are removed."""
    c = client()
    r = _gen(c, title="Erase me")
    pid = r.json()["pending_id"]
    d = quarantine._pending_root() / pid
    assert (d / "original.bin").exists() and (d / "context.json").exists()
    out = c.delete("/api/me/builds")
    assert out.status_code == 200
    assert out.json()["pending_uploads"] >= 1
    assert not d.exists()                                   # both files gone with the directory


def test_pending_uploads_expire_after_seven_days(scan_on):
    """Retention: a parked upload is transient — anything not resumed within
    PENDING_MAX_AGE_DAYS (default 7) is swept away."""
    c = client()
    r = _gen(c)
    pid = r.json()["pending_id"]
    ctx = json.loads((quarantine._pending_root() / pid / "context.json").read_text())
    ctx["ts"] = ctx["ts"] - 8 * 86400                      # parked 8 days ago
    (quarantine._pending_root() / pid / "context.json").write_text(json.dumps(ctx))
    from app.services import retention
    out = retention.purge_expired(store)                   # the retention sweep covers pendings
    assert out["pending_expired"] == 1
    assert not (quarantine._pending_root() / pid).exists()
