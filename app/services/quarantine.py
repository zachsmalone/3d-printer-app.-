"""Quarantine: uploads accepted while the malware scanner was explicitly enabled but UNREACHABLE
are held — never served — until a scan (or an admin) clears them.

Launch-checklist Task 4: "Implement quarantine for suspicious uploads (don't serve until reviewed)".
Policy:
  * scanner off (the default): no quarantine, uploads behave exactly as before;
  * scanner on + clean: normal;
  * scanner on + INFECTED: refused at the upload gate, never stored;
  * scanner on + UNREACHABLE: the upload is accepted (every other check ran) but the build is
    marked quarantined — its files are not served, shared or printed until a scan or an admin
    release clears it. The owner still sees the build's status metadata.

Every transition is logged in the moderation audit trail; the admin release is authorized by the
admin token and audited like every other moderation action.
"""
from __future__ import annotations

import logging

from .. import config
from ..community import moderation
from ..services.history import store

log = logging.getLogger("zeim.quarantine")

QUARANTINE_MSG = ("This file is pending its malware scan, so it can't be downloaded or shared yet. "
                  "It will unlock automatically once the scanner is back — nothing was lost.")


def is_quarantined(bid: str) -> bool:
    try:
        return bool(store.get(bid).get("quarantined"))
    except KeyError:
        return False


def mark(bid: str) -> None:
    """Flag a build as pending its malware scan (called by the upload flow when the scanner was down)."""
    meta = store.get(bid)
    if meta.get("quarantined"):
        return
    meta["quarantined"] = True
    store.save(meta)
    moderation._log("quarantine", item=bid, reason="scanner unavailable at upload")
    log.warning("build quarantined: scanner was unreachable at upload time")


def _stored_bytes(bid: str) -> bytes | None:
    """The bytes that could be served: the stored source file (if any), else the first model."""
    try:
        meta = store.get(bid)
    except KeyError:
        return None
    src = meta.get("source")
    if src:
        p = store.dir(bid) / src
        if p.exists():
            return p.read_bytes()
    p = store.dir(bid) / "model.stl"
    return p.read_bytes() if p.exists() else None


def rescan(bid: str) -> str:
    """Scan a quarantined build's stored bytes. -> 'off' | 'clean' | 'infected' | 'unavailable'.
    A clean (or scanner-off) result clears the flag; infected keeps it."""
    from . import uploadgate
    if not is_quarantined(bid):
        return "off" if not config.CLAMAV else "clean"
    data = _stored_bytes(bid)
    if data is None:
        _clear(bid, "nothing stored to scan")
        return "clean"
    clean, signature, state = uploadgate.scan_bytes(data)
    if state == "infected":
        log.error("quarantined build re-scanned: STILL INFECTED (%s)", signature)
        moderation._log("quarantine_scan", item=bid, verdict="infected", signature=signature)
        return "infected"
    if state == "unscanned":
        return "unavailable"
    _clear(bid, "scan clean" if state == "clean" else "scanner disabled")
    return "clean"


def _clear(bid: str, why: str) -> None:
    meta = store.get(bid)
    if meta.pop("quarantined", None):
        store.save(meta)
        moderation._log("quarantine_release", item=bid, reason=why)
        log.info("quarantine lifted for build (%s)", why)


def release(bid: str) -> dict:
    """Admin release: clears the flag by decision (audited), without a scan."""
    if not is_quarantined(bid):
        raise KeyError("not quarantined")
    _clear(bid, "admin release")
    return {"ok": True, "id": bid}


def guard(bid: str) -> None:
    """Serving-path check. Raises HTTPException while the build is still quarantined:
    a re-scan runs first (scanner back + clean -> the flag clears and serving proceeds);
    still unreachable -> 409 pending-scan; infected -> 422. """
    from fastapi import HTTPException
    if not is_quarantined(bid):
        return
    verdict = rescan(bid)
    if verdict == "infected":
        raise HTTPException(422, "That file was flagged by the malware scanner and can't be downloaded or shared.")
    if verdict == "unavailable":
        raise HTTPException(409, QUARANTINE_MSG)
