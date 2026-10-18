"""Build-file storage: object storage when configured (PHOTO3D_S3_*), local disk otherwise.

This is the app's ONE path for build artifacts that can live in object storage:
the exported model files, the sanitized source photo, and thumbnails. Local disk
remains the working surface the slicer and editor read from (PrusaSlicer needs a
local file; edit.js works on the local build dir) — when S3 is configured the
artifacts are ALSO written to the bucket and downloads redirect to presigned
URLs, so the local disk becomes a scratch cache rather than the system of record.

Nothing changes when PHOTO3D_S3_* is unset: put() is a no-op, signed_url() is None
and callers fall back to serving local files. Switching it on is a config change,
not a code change.
"""
from __future__ import annotations

import json
import logging
import os
import threading

_PENDING_LOCK = threading.Lock()
from pathlib import Path

from .. import config
from . import objectstore

log = logging.getLogger("zeim.storage")

_ARTIFACTS = "builds/{bid}/{name}"


def enabled() -> bool:
    return objectstore.enabled()


def artifact_key(bid: str, name: str) -> str:
    """Stable key for one build artifact, e.g. builds/<bid>/model.stl."""
    return _ARTIFACTS.format(bid=bid, name=name)


def put(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    """Write one artifact to object storage. No-op when not configured (local disk already has it)."""
    if enabled():
        objectstore.put(key, data, content_type)


def put_build(bid: str, name: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    put(artifact_key(bid, name), data, content_type)


def signed_url(key: str, ttl_s: int = 900) -> str | None:
    """Presigned GET URL, or None when object storage is not configured (serve locally)."""
    if not enabled():
        return None
    return objectstore.signed_url(key, ttl_s)


def _pending_path() -> Path:
    return Path(config.DATA) / "pending_deletions.json"


def _load_pending() -> dict:
    """Pending deletions are SAFETY data: a corrupt file must never read as 'nothing pending'.
    Raises RuntimeError on corruption — callers either preserve it loudly or (delete_build,
    where recording the new deletion is mandatory) move it aside for manual recovery."""
    try:
        return json.loads(_pending_path().read_text())
    except FileNotFoundError:
        return {}
    except Exception as e:
        raise RuntimeError(f"pending_deletions.json unreadable ({e}) — refusing to treat it as empty")


def _save_pending(d: dict) -> None:
    """Atomic (tmp + rename) so a crash mid-write can never truncate the safety record.
    Callers hold _PENDING_LOCK (the whole load/modify/save sequence must be serialized)."""
    p = _pending_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1))
    os.replace(tmp, p)


def _artifact_names() -> tuple[str, ...]:
    return ("source", "thumb.png", *sorted(f"model.{e}" for e in ("stl", "obj", "3mf", "ply")))


def delete_build(bid: str) -> None:
    """Remove a build's artifacts from object storage, DURABLY: the keys are recorded in
    DATA/pending_deletions.json BEFORE any local metadata is gone, and retried until they
    succeed — a provider outage never silently orphans remote copies. Callers must remove
    local state only AFTER this returns: it RAISES if the queue cannot be persisted (so a
    crash between record and local removal can never orphan remote copies)."""
    if not enabled():
        return
    keys = [artifact_key(bid, n) for n in _artifact_names()]
    # the WHOLE load/modify/save sequence (including corruption handling) is inside the lock —
    # a load outside it loses concurrent enqueues. Single-process deployment: the app runs one
    # uvicorn worker (JSON-file storage is single-process by design); a module-level lock is
    # therefore sufficient — if multi-worker is ever configured, this needs a file lock.
    with _PENDING_LOCK:
        try:
            pending = _load_pending()
        except RuntimeError as e:
            # the safety record is corrupt: preserve it for manual recovery. If preservation
            # fails, REFUSE — overwriting would destroy the only recovery record.
            log.error("%s; preserving as pending_deletions.corrupt-*.json", e)
            import time as _time
            try:
                _pending_path().rename(_pending_path().with_name(
                    f"pending_deletions.corrupt-{int(_time.time())}.json"))
            except Exception as keep_err:
                raise RuntimeError(
                    f"pending_deletions.json corrupt AND unpreservable ({keep_err}) — "
                    "refusing to record a deletion over the recovery record")
            pending = {}
        pending[bid] = keys                   # recorded before we try
        try:
            _save_pending(pending)
        except Exception as e:
            raise RuntimeError(f"could not persist the pending-deletion record ({e}) — "
                              "refusing to delete locally: remote copies would be orphaned")
    retry_pending(bids=[bid])


def retry_pending(bids: list[str] | None = None) -> int:
    """Retry recorded deletions (all, or the given builds). Returns how many builds still
    have pending keys. Called from delete_build and safe to call from cron/startup.
    A corrupt record RAISES (loudly) rather than reading as 'nothing pending'."""
    if not enabled():
        return 0
    with _PENDING_LOCK:                         # the whole load/modify/save sequence
        pending = _load_pending()
        for bid in list(pending):
            if bids is not None and bid not in bids:
                continue
            for k in list(pending[bid]):
                try:
                    objectstore.delete(k)
                    pending[bid].remove(k)
                except Exception:
                    log.warning("object-storage deletion still pending for %s (will retry)", bid)
                    break
            if not pending[bid]:
                del pending[bid]               # fully deleted remotely: forget it
        _save_pending(pending)
        return len(pending)
