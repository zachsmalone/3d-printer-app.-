"""How long ZEIM keeps per-build files, and what it does when the disk is nearly full.

Rules (all configurable by environment variable, see app/config.py):
  * a build the person STARRED (favorite) is never removed by age or by a low disk. Only the person deleting it, or "Delete my stuff"
    / deleting the account, removes it.
  * a build that was SAVED on purpose (shared to the Showcase or sent to a class) is kept 30 days (PHOTO3D_KEEP_SAVED_DAYS);
  * any other build is kept 7 days (PHOTO3D_KEEP_UNSAVED_DAYS).
  * a folder with no build metadata at all (a build that never finished) is removed after one day.
Cleanup only ever looks at the direct sub-folders of the per-build data folder (OUT). It refuses to run if that folder is, or sits inside,
library/, static/ or the code. Logs say HOW MANY were removed, never which files or whose.
"""
from __future__ import annotations

import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from .. import config
from .history import BuildStore, store as _store

log = logging.getLogger("zeim.cleanup")
FORBIDDEN = ("library", "static", "app", "tests", "reports", ".git", ".venv")


class DiskLow(Exception):
    pass


def _safe_root(root: Path) -> Path:
    """The per-build folder, but only if it is not the library, the static files or the code (or inside / above them)."""
    r = Path(root).resolve()
    base = config.ROOT.resolve()
    for name in FORBIDDEN:
        f = base / name
        if r == f or f in r.parents or r in f.parents:
            raise PermissionError("cleanup refuses to touch this folder")
    if r == base or r in base.parents:
        raise PermissionError("cleanup refuses to touch this folder")
    return r


def build_dirs(root: Path):
    """Direct children that look like a build folder: a plain (non-symlink) directory whose name is alphanumeric."""
    r = _safe_root(root)
    for p in r.iterdir():
        if p.is_dir() and not p.is_symlink() and p.name.isalnum():
            yield p


def _age_days(meta: dict, now: float) -> float:
    try:
        t = datetime.fromisoformat(meta["created"]).timestamp()
    except Exception:
        return 0.0
    return (now - t) / 86400


def keep_days(meta: dict) -> float | None:
    """None = kept until the person deletes it (starred)."""
    if meta.get("favorite"):
        return None
    return float(config.KEEP_SAVED_DAYS if meta.get("saved") else config.KEEP_UNSAVED_DAYS)


def expires_at(meta: dict) -> str | None:
    d = keep_days(meta)
    if d is None:
        return None
    try:
        return datetime.fromtimestamp(datetime.fromisoformat(meta["created"]).timestamp() + d * 86400, timezone.utc).isoformat()
    except Exception:
        return None


def purge_expired(bs: BuildStore = _store, now: float | None = None) -> dict:
    """Remove builds older than their keep time. Starred builds are skipped. Returns counts only.
    Metadata is read through BuildStore, so this works in json and db storage modes alike."""
    now = time.time() if now is None else now
    out = {"expired": 0, "unfinished": 0, "kept_starred": 0}
    with bs.lock:
        for d in list(build_dirs(bs.root)):
            try:
                meta = bs.get(d.name)            # db mode: the row is authoritative; json mode: meta.json
            except KeyError:
                meta = None
                mp = d / "meta.json"
                if not mp.exists():
                    if now - d.stat().st_mtime > 86400:
                        shutil.rmtree(d, ignore_errors=True); out["unfinished"] += 1
                    continue
                try:
                    import json
                    meta = json.loads(mp.read_text())   # json-era folder the store does not know: still readable
                except Exception:
                    continue
            days = keep_days(meta)
            if days is None:
                out["kept_starred"] += 1
            elif _age_days(meta, now) > days:
                bs.delete(d.name); out["expired"] += 1
    if out["expired"] or out["unfinished"]:
        log.info("retention: removed %d expired and %d unfinished builds (%d starred kept)", out["expired"], out["unfinished"], out["kept_starred"])
    return out


def free_bytes(root: Path | None = None) -> int:
    return shutil.disk_usage(root or config.OUT).free


def sweep_for_space(bs: BuildStore = _store, now: float | None = None) -> dict:
    """Disk is low: remove expired builds, then the oldest NON-starred builds (not the last 10 minutes) until there is room again."""
    now = time.time() if now is None else now
    out = purge_expired(bs, now)
    out["swept"] = 0
    target = config.DISK_TARGET_FREE_MB * 1024 * 1024
    if free_bytes(bs.root) >= target:
        return out
    with bs.lock:
        metas = [m for m in bs.list() if not m.get("favorite") and _age_days(m, now) * 86400 > 600]
        for m in sorted(metas, key=lambda m: m["created"]):
            if free_bytes(bs.root) >= target:
                break
            bs.delete(m["id"]); out["swept"] += 1
    if out["swept"]:
        log.warning("disk low: removed %d oldest unstarred builds to make room", out["swept"])
    return out


def check_disk(bs: BuildStore = _store):
    """Call before a heavy build. Sweeps if low; refuses (DiskLow) only if there is still no room without touching starred builds."""
    if free_bytes(bs.root) >= config.DISK_MIN_FREE_MB * 1024 * 1024:
        return
    sweep_for_space(bs)
    if free_bytes(bs.root) < config.DISK_MIN_FREE_MB * 1024 * 1024:
        raise DiskLow("ZEIM's storage is almost full, so it can't make a new build right now. Starred builds are never removed to make room. "
                      "Please delete a build you don't need, or try again later.")


def start_background(interval_s: int = 3600):
    """Startup clean-up now, then once an hour, in a daemon thread."""
    import threading

    def loop():
        while True:
            try:
                purge_expired()
            except Exception:
                log.exception("retention run failed")
            time.sleep(interval_s)
    t = threading.Thread(target=loop, name="zeim-retention", daemon=True)
    t.start()
    return t
