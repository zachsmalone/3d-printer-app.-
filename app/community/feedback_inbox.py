"""Read-only inbox of NPS scores and stored ZeimFeedback notes.

Collection is unchanged: scores stay anonymous date+number lines, and notes stay
the records already written under DATA/feedback/. This module only reads them.
Access is the existing owner/admin check (local owner, or X-Admin-Token) or a
signed-in account with site_admin set on the user record. Denied requests get 404.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Request

from .. import config
from .identity import Actor

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


def can_view(request: Request, actor: Actor | None) -> bool:
    """True for the local machine owner, a valid admin token, or a site_admin account."""
    from ..api import guards
    if guards.is_owner(request) or guards.is_admin(request):
        return True
    return bool(actor and actor.user and actor.user.get("site_admin"))


def require(request: Request, actor: Actor | None) -> None:
    if not can_view(request, actor):
        raise HTTPException(404, "Not found")


def _limit(raw, default: int = DEFAULT_LIMIT) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = default
    return max(1, min(MAX_LIMIT, n))


def _offset(raw) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 0
    return max(0, n)


def nps_records() -> list[dict]:
    """All stored recommend scores, newest date first, then higher scores first on the same day."""
    folder = config.DATA / "metrics"
    rows: list[dict] = []
    if not folder.is_dir():
        return rows
    for path in sorted(folder.glob("*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("e") != "nps" or not isinstance(rec.get("s"), int) or isinstance(rec.get("s"), bool):
                continue
            if not 0 <= rec["s"] <= 10:
                continue
            day = rec.get("d") if isinstance(rec.get("d"), str) else ""
            rows.append({"date": day, "score": rec["s"]})
    rows.sort(key=lambda r: (r["date"], r["score"]), reverse=True)
    return rows


def nps_summary(rows: list[dict] | None = None) -> dict:
    """Counts and NPS from real scores only. NPS = % promoters (9-10) minus % detractors (0-6)."""
    rows = nps_records() if rows is None else rows
    scores = [r["score"] for r in rows]
    n = len(scores)
    promoters = sum(1 for s in scores if s >= 9)
    passives = sum(1 for s in scores if 7 <= s <= 8)
    detractors = sum(1 for s in scores if s <= 6)
    score = round(100 * (promoters - detractors) / n) if n else None
    return {
        "answers": n,
        "promoters": promoters,
        "passives": passives,
        "detractors": detractors,
        "score": score,
    }


def _note_time(raw) -> str:
    try:
        ts = float(raw)
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def note_records() -> list[dict]:
    """Stored written notes, newest first. Fields are only those already on disk."""
    folder: Path = config.DATA / "feedback"
    rows: list[dict] = []
    if not folder.is_dir():
        return rows
    for path in folder.glob("*.json"):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(rec, dict):
            continue
        rows.append({
            "id": path.stem,
            "at": rec.get("at"),
            "date": _note_time(rec.get("at")),
            "who": str(rec["who"])[:80] if rec.get("who") is not None else "",
            "text": str(rec.get("text") or rec.get("message") or ""),
            "emailed": bool(rec.get("emailed")),
        })
    rows.sort(key=lambda r: (r["at"] is not None, r["at"] or 0), reverse=True)
    return rows


def _page(rows: list, offset: int, limit: int) -> dict:
    return {"items": rows[offset:offset + limit], "total": len(rows), "offset": offset, "limit": limit}


def inbox(notes_offset=0, notes_limit=DEFAULT_LIMIT, scores_offset=0, scores_limit=DEFAULT_LIMIT) -> dict:
    scores = nps_records()
    notes = note_records()
    so, sl = _offset(scores_offset), _limit(scores_limit)
    no, nl = _offset(notes_offset), _limit(notes_limit)
    return {
        "nps": nps_summary(scores),
        "scores": _page(scores, so, sl),
        "notes": _page(notes, no, nl),
    }
