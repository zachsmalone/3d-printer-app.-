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
import shutil
import uuid
from pathlib import Path

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


def _root() -> Path:
    """DATA/quarantine — 0700, never served by any route (only this module touches it)."""
    p = Path(config.DATA) / "quarantine"
    p.mkdir(parents=True, exist_ok=True)
    p.chmod(0o700)
    return p


def hold_bytes(raw: bytes) -> Path:
    """Park the ORIGINAL upload bytes (pre-sanitize) in the restricted hold area. Returns the
    hold dir; quarantine.mark(bid, hold) claims it once the build id exists."""
    d = _root() / f".hold-{uuid.uuid4().hex[:12]}"
    d.mkdir()
    (d / "original.bin").write_bytes(raw)
    return d


def mark(bid: str, hold: Path | None = None) -> None:
    """Flag a build as pending its malware scan (called by the upload flow when the scanner was
    down) and claim the held original bytes for later re-scan."""
    meta = store.get(bid)
    if meta.get("quarantined"):
        if hold is not None:
            shutil.rmtree(hold, ignore_errors=True)
        return
    meta["quarantined"] = True
    store.save(meta)
    if hold is not None:
        dest = _root() / bid
        if dest.exists():
            shutil.rmtree(hold, ignore_errors=True)      # already held (should not happen)
        else:
            hold.rename(dest)
    moderation._log("quarantine", item=bid, reason="scanner unavailable at upload")
    log.warning("build quarantined: scanner was unreachable at upload time")


def _held_bytes(bid: str) -> bytes | None:
    """The ORIGINAL upload bytes held in the restricted area — what the pending scan reviews."""
    p = _root() / bid / "original.bin"
    return p.read_bytes() if p.exists() else None


def rescan(bid: str) -> str:
    """Scan the HELD ORIGINAL bytes. -> 'clean' | 'infected' | 'held'.
    Only an explicit clean scan (or an admin release) lifts the hold: a disabled scanner or
    missing held bytes leaves the build held — never a silent release."""
    from . import uploadgate
    if not is_quarantined(bid):
        return "clean"
    data = _held_bytes(bid)
    if data is None:
        log.error("quarantined build %s has no held bytes — staying held (admin release only)", bid)
        return "held"
    clean, signature, state = uploadgate.scan_bytes(data)
    if state == "infected":
        log.error("quarantined build re-scanned: STILL INFECTED (%s)", signature)
        moderation._log("quarantine_scan", item=bid, verdict="infected", signature=signature)
        return "infected"
    if state == "clean":
        _clear(bid, "scan clean")
        return "clean"
    return "held"                       # scanner off / unreachable / unusable verdict: keep holding


def _clear(bid: str, why: str) -> None:
    meta = store.get(bid)
    if meta.pop("quarantined", None):
        store.save(meta)
        held = _root() / bid
        if held.exists():
            shutil.rmtree(held, ignore_errors=True)     # the held original goes too
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
    if verdict != "clean":
        raise HTTPException(409, QUARANTINE_MSG)
