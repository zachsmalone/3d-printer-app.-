"""Upload gate: content check + per-account rate limit + audit log (+ optional local ClamAV).

Called at every upload entry point BEFORE any parsing. Today that is /api/generate
(photos). Print photos go through imagesafe + the image-moderation hook (kept as-is);
mesh uploads through /edit/new use meshedit.sniff (Copilot's file — wiring uploadsafe
there is deliberately left to that workstream, see docs/uploadsafe.md).

Rules:
  * the hourly limit is per ACCOUNT, not per browser session — it holds across devices;
    in db mode the counter lives in SQLite (shared by all workers), in json mode it is
    the in-process limiter (single-worker deployments);
  * the audit log DATA/uploads.log.jsonl records ts/sid/kind/format/size/verdict — never
    file bytes, never file content;
  * rejected files are NOT stored (keeping rejected — possibly illegal — content on disk
    is worse than discarding it). "Quarantine until reviewed" applies to print photos,
    which already land as review-pending, hidden until a moderator approves them;
  * optional malware scan is local clamd only (PHOTO3D_CLAMAV=1). If clamd is unreachable,
    uploads are allowed and the miss is logged — availability over false safety.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .. import config
from ..config import DATA
from ..core.imagesafe import UNREADABLE
from . import uploadsafe

log = logging.getLogger("zeim.uploads")

AUDIT_LOG = DATA / "uploads.log.jsonl"
_HOUR = 3600.0


class GateError(Exception):
    """Upload refused. status is the HTTP status, message is safe to show the user."""

    def __init__(self, status: int, message: str, reason: str = ""):
        super().__init__(message)
        self.status, self.message, self.reason = status, message, reason


def _audit(entry: dict) -> None:
    """Append one line to the audit log. Never raises: an audit problem must not break uploads."""
    try:
        entry["ts"] = time.time()
        with AUDIT_LOG.open("a") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        log.exception("upload audit log write failed")


def _allowed(sid: str, now: float) -> bool:
    """Per-account hourly limit. db mode: SQLite counter (shared by all workers); json mode: in-process."""
    if config.UPLOADS_PER_HOUR <= 0:
        return True
    if config.STORAGE_MODE == "db":
        from .. import db
        db.upload_events_prune(now, _HOUR)
        if db.upload_events_count(sid, now - _HOUR) >= config.UPLOADS_PER_HOUR:
            return False
        db.upload_events_add(sid, now)
        return True
    # json mode: in-process limiter (documented limitation for multi-worker json deployments)
    from ..core import ratelimit
    return ratelimit.hit(f"upload:{sid}", limit=config.UPLOADS_PER_HOUR, window_s=_HOUR)


def _clamav_clean(data: bytes) -> tuple[bool, str]:
    """Scan via a local clamd (INSTREAM). Returns (clean, signature). Unreachable clamd = clean."""
    if not config.CLAMAV:
        return True, ""
    import socket
    try:
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(30)
        s.connect(config.CLAMAV_SOCKET)
        try:
            s.sendall(b"zINSTREAM\0")
            for i in range(0, len(data), 32768):
                chunk = data[i:i + 32768]
                s.sendall(f"{len(chunk):x}".encode() + b"\0" + chunk)
            s.sendall(b"0\0")
            s.shutdown(socket.SHUT_WR)
            reply = b""
            while True:
                part = s.recv(4096)
                if not part:
                    break
                reply += part
        finally:
            s.close()
        verdict = reply.decode("utf-8", "replace").strip()
        if verdict.upper().startswith("OK"):
            return True, ""
        if "FOUND" in verdict.upper():
            return False, verdict.split("FOUND")[0].strip()
        return True, verdict      # unknown reply: do not block on a confused scanner
    except Exception as e:
        log.warning("PHOTO3D_CLAMAV=1 but clamd unreachable (%s) — upload allowed, miss logged", e)
        return True, ""


def gate(data: bytes, actor_sid: str, source: str = "generate") -> uploadsafe.Checked:
    """Check one upload before anything parses it. Raises GateError; returns uploadsafe's Checked."""
    now = time.time()
    if not _allowed(actor_sid, now):
        _audit({"sid": actor_sid, "src": source, "size": len(data), "verdict": "rate_limited"})
        raise GateError(429, f"You have reached this hour's upload limit ({config.UPLOADS_PER_HOUR}). Try again later.")
    try:
        checked = uploadsafe.check(data)
    except uploadsafe.Rejected as e:
        if e.reason == "image_too_many_pixels" and source == "generate":
            # photo flow only: defer the pixel cap to the decoder. imagesafe (which runs next, in
            # the same request) enforces its own cap AFTER decoding — the sniff only fires on a
            # structurally valid header (IHDR is validated first), so this is a genuine oversized
            # image, and imagesafe's own "very large" refusal still protects the worker. Logged.
            _audit({"sid": actor_sid, "src": source, "size": len(data), "verdict": "deferred:image_too_many_pixels"})
            sniffed = uploadsafe._sniff_image(data)
            checked = uploadsafe.Checked("image", sniffed[0], len(data),
                                         image={"width": sniffed[1], "height": sniffed[2],
                                                "pixels": sniffed[1] * sniffed[2]})
        else:
            _audit({"sid": actor_sid, "src": source, "size": len(data), "verdict": f"rejected:{e.reason}"})
            if e.reason == "too_big":
                raise GateError(413, "That file is too big to upload.")
            if e.reason in ("unknown_type", "image_bad_header"):
                # the photo flow's existing friendly contract (imagesafe's message, 400)
                raise GateError(400, UNREADABLE)
            raise GateError(415, "That file type can't be used here. Upload a photo (or STL/OBJ/3MF where offered).")
    clean, signature = _clamav_clean(data)
    if not clean:
        _audit({"sid": actor_sid, "src": source, "size": len(data), "verdict": f"malware:{signature}"})
        log.warning("upload refused by malware scan (sid hidden in audit log)")
        raise GateError(415, "That file can't be uploaded. Nothing about it was stored.")
    _audit({"sid": actor_sid, "src": source, "kind": checked.kind, "format": checked.format,
            "size": checked.size_bytes, "verdict": "ok"})
    return checked
