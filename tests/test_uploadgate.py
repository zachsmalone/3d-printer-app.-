"""Upload gate: content check + per-account hourly limit + audit log + optional clamd.

Covers app/services/uploadgate.py and its wiring into POST /api/generate.
"""
from __future__ import annotations

import json

import pytest

from app import config, db
from app.services import uploadgate, uploadsafe


def _png() -> bytes:
    import io
    from PIL import Image
    b = io.BytesIO()
    Image.effect_mandelbrot((96, 96), (-2, -1.5, 1, 1.5), 40).convert("RGB").save(b, "PNG")
    return b.getvalue()


@pytest.fixture
def fresh_log(monkeypatch, tmp_path):
    """Point the audit log at a fresh file AND clear the in-process rate limiter between tests."""
    from app.core import ratelimit
    ratelimit._hits.clear()
    p = tmp_path / "uploads.log.jsonl"
    monkeypatch.setattr(uploadgate, "AUDIT_LOG", p)
    return p


def _lines(p):
    return [json.loads(l) for l in p.read_text().splitlines()]


def test_gate_passes_valid_image_and_logs_it(fresh_log):
    checked = uploadgate.gate(_png(), "sid1")
    assert checked.kind == "image"
    entry = _lines(fresh_log)[-1]
    assert entry["verdict"] == "ok" and entry["sid"] == "sid1" and entry["kind"] == "image"
    assert entry["size"] > 0 and "ts" in entry


def test_gate_rejects_garbage_and_logs_it(fresh_log):
    with pytest.raises(uploadgate.GateError) as ei:
        uploadgate.gate(b"not an image or mesh at all", "sid1")
    # the photo flow's friendly contract: same 400 + UNREADABLE message imagesafe always gave
    assert ei.value.status == 400 and "couldn't open that photo" in str(ei.value.message)
    entry = _lines(fresh_log)[-1]
    assert entry["verdict"] == "rejected:unknown_type"


def test_audit_log_never_contains_file_bytes(fresh_log):
    data = _png()
    uploadgate.gate(data, "sid1")
    raw = fresh_log.read_text()
    # the log holds metadata only — not the upload content (it would double stored user data)
    assert str(data[:64]) not in raw
    assert "iVBOR" not in raw


def test_hourly_limit_per_account(fresh_log, monkeypatch):
    monkeypatch.setattr(config, "UPLOADS_PER_HOUR", 2)
    uploadgate.gate(_png(), "sid1")
    uploadgate.gate(_png(), "sid1")
    with pytest.raises(uploadgate.GateError) as ei:
        uploadgate.gate(_png(), "sid1")
    assert ei.value.status == 429
    # the limit is per account, not global: another account is unaffected
    uploadgate.gate(_png(), "sid2")
    assert _lines(fresh_log)[-1]["verdict"] == "ok"


def test_hourly_limit_shared_in_db_mode(fresh_log, monkeypatch, tmp_path):
    """db mode: the counter is SQLite-backed, so it survives a process restart and is shared by workers."""
    monkeypatch.setattr(config, "UPLOADS_PER_HOUR", 2)
    monkeypatch.setattr(config, "STORAGE_MODE", "db")
    monkeypatch.setattr(config, "DATA", tmp_path)
    db.reset()
    try:
        uploadgate.gate(_png(), "sid1")
        uploadgate.gate(_png(), "sid1")
        db.reset()                                  # simulate a restart: the counter must persist
        with pytest.raises(uploadgate.GateError) as ei:
            uploadgate.gate(_png(), "sid1")
        assert ei.value.status == 429
    finally:
        db.reset()
        monkeypatch.setattr(config, "STORAGE_MODE", "json")


def test_unreachable_clamd_allows_and_is_logged(fresh_log, monkeypatch, caplog):
    """PHOTO3D_CLAMAV=1 with clamd down: availability over false safety — allow, log the miss."""
    monkeypatch.setattr(config, "CLAMAV", True)
    monkeypatch.setattr(config, "CLAMAV_SOCKET", "/no/such/clamd.ctl")
    with caplog.at_level("WARNING", logger="zeim.uploads"):
        checked = uploadgate.gate(_png(), "sid1")
    assert checked.kind == "image"                   # not blocked by the scanner being down
    assert any("clamd unreachable" in r.message for r in caplog.records)


@pytest.fixture
def ack_on(monkeypatch):
    monkeypatch.setattr(config, "PHOTO_ACK_REQUIRED", True)


def test_generate_endpoint_enforces_the_gate(ack_on, monkeypatch):
    """End to end: POST /api/generate is gated (rate limit reached -> 429 before any parsing)."""
    from tests.b1 import client, gen
    monkeypatch.setattr(config, "UPLOADS_PER_HOUR", 1)
    c = client()
    r1 = gen(c)
    assert r1.status_code == 200, r1.text
    r2 = gen(c)
    assert r2.status_code == 429
