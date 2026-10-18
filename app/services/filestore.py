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

import logging

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


def delete_build(bid: str) -> None:
    """Best-effort removal of a build's artifacts from object storage (local deletion is the caller's job)."""
    if not enabled():
        return
    for name in ("source", "thumb.png", *sorted(f"model.{e}" for e in ("stl", "obj", "3mf", "ply"))):
        try:
            objectstore.delete(artifact_key(bid, name))
        except Exception:                        # never let cleanup break a delete flow
            log.exception("object-storage cleanup failed for build %s", bid)
