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
from ..core.imagesafe import TOO_BIG, UNREADABLE
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


def _allowed(sid: str, now: float, source: str = "generate") -> bool:
    """Per-account hourly limit. db mode: SQLite counter (shared by all workers); json mode: in-process.
    Mesh edit/CAD imports have their own (larger) budget: opening your own files is cheap and frequent.
    Photo-prep previews use a separate cap (source ai3d-prep) so they do not spend the upload allowance."""
    # Photo-prep previews are the same photo the mesh job will upload. They have their own
    # small cap so a few crops do not use up the hourly upload allowance. The mesh job still counts.
    if source == "edit":
        limit, key = config.EDIT_UPLOADS_PER_HOUR, f"edit:{sid}"
    elif source == "ai3d-prep":
        limit, key = 30, f"ai3dprep:{sid}"
    else:
        limit, key = config.UPLOADS_PER_HOUR, sid
    if limit <= 0 or config.TESTING_MODE:                 # testing mode: no hourly upload quota
        return True
    if config.STORAGE_MODE == "db":
        from .. import db
        db.upload_events_prune(now, _HOUR)                # best-effort housekeeping
        return db.upload_events_hit(key, now, _HOUR, limit)
    # json mode: in-process limiter (documented limitation for multi-worker json deployments)
    from ..core import ratelimit
    return ratelimit.hit(f"upload:{key}", limit=limit, window_s=_HOUR)


def scan_bytes(data: bytes) -> tuple[bool, str, str]:
    """Scan via a local clamd (INSTREAM). -> (clean, signature, state) where state is
    'off' (scanning not enabled) | 'clean' | 'infected' | 'unscanned' (scanner on but unreachable).
    An unreachable clamd is NOT silently clean — the upload flow marks the build quarantined
    (services/quarantine.py) instead of trusting an unscanned file."""
    if not config.CLAMAV:
        return True, "", "off"
    import socket
    import struct
    try:
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(30)
        s.connect(config.CLAMAV_SOCKET)
        try:
            s.sendall(b"zINSTREAM\0")
            # clamd INSTREAM framing: each chunk is <4-byte network-order length><data>,
            # terminated by a zero-length chunk (4 zero bytes) — NOT hex text.
            for i in range(0, len(data), 32768):
                chunk = data[i:i + 32768]
                s.sendall(struct.pack("!I", len(chunk)) + chunk)
            s.sendall(struct.pack("!I", 0))
            s.shutdown(socket.SHUT_WR)
            reply = b""
            while True:
                part = s.recv(4096)
                if not part:
                    break
                reply += part
        finally:
            s.close()
        # clamd INSTREAM replies end with a NUL terminator: "stream: OK\0" or
        # "stream: <SIGNATURE> FOUND\0". Errors arrive as "ERROR: <text>\0" or are cut off.
        # Verdict grammar is STRICT: an unterminated reply or anything that is not exactly
        # a clean or infected verdict is NOT a verdict — the upload is held, never trusted.
        if not reply.endswith(b"\0"):
            log.warning("clamd reply missing its NUL terminator (%r) — upload held", reply[:120])
            return True, "", "unscanned"
        body = reply[:-1].decode("utf-8", "replace").strip()
        if body.endswith(" FOUND"):
            return False, body[:-len(" FOUND")].strip(), "infected"
        if body in ("OK", "stream: OK"):                     # EXACTLY the supported success replies
            return True, "", "clean"
        # empty / malformed / ERROR replies are NOT a clean verdict: hold the upload
        log.warning("clamd gave an unusable verdict (%r) — upload quarantined pending scan", body[:120])
        return True, "", "unscanned"
    except Exception as e:
        log.warning("PHOTO3D_CLAMAV=1 but clamd unreachable (%s) — upload quarantined pending scan", e)
        return True, "", "unscanned"


def gate(data: bytes, actor_sid: str, source: str = "generate", **limits) -> uploadsafe.Checked:
    """Check one upload before anything parses it. Raises GateError; returns uploadsafe's Checked.
    `limits` are passed to uploadsafe.check (e.g. max_bytes for the 500 MB editor upload)."""
    now = time.time()
    if not _allowed(actor_sid, now, source):
        _audit({"sid": actor_sid, "src": source, "size": len(data), "verdict": "rate_limited"})
        if source == "ai3d-prep":
            raise GateError(429, "You have reached this hour's photo prep limit (30). Try again later.")
        raise GateError(429, f"You have reached this hour's upload limit ({config.UPLOADS_PER_HOUR}). Try again later.")
    try:
        checked = uploadsafe.check(data, **limits)
    except uploadsafe.Rejected as e:
        _audit({"sid": actor_sid, "src": source, "size": len(data), "verdict": f"rejected:{e.reason}"})
        if e.reason == "too_big":
            raise GateError(413, "That file is too big to upload.")
        if e.reason in ("unknown_type", "image_bad_header"):
            # the photo flow's existing friendly contract (imagesafe's message, 400)
            raise GateError(400, UNREADABLE)
        if e.reason == "image_too_many_pixels":
            # the sniff only fires on a structurally valid header (IHDR is validated first),
            # so this is a genuine oversized image: same 400 + message imagesafe gives
            raise GateError(400, TOO_BIG)
        raise GateError(415, "That file type can't be used here. Upload a photo (or STL/OBJ/3MF where offered).")
    clean, signature, scan_state = scan_bytes(data)
    checked.scan_state = scan_state
    if not clean:
        _audit({"sid": actor_sid, "src": source, "size": len(data), "verdict": f"malware:{signature}"})
        log.warning("upload refused by malware scan (sid hidden in audit log)")
        raise GateError(415, "That file can't be uploaded. Nothing about it was stored.")
    if scan_state == "unscanned":
        _audit({"sid": actor_sid, "src": source, "size": len(data), "verdict": "quarantined:scanner_unreachable"})
    _audit({"sid": actor_sid, "src": source, "kind": checked.kind, "format": checked.format,
            "size": checked.size_bytes, "verdict": "ok"})
    return checked
