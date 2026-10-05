"""Reporting + moderation queue (STUB-level but functional locally). Family-friendly only.

Reports are stored; `minor_safety` reports hide the item immediately pending review.
The queue is only readable with header X-Admin-Token == PHOTO3D_ADMIN_TOKEN (unset = disabled).
Real launch needs: trained reviewers, escalation + NCMEC reporting for CSAM, takedown/appeals
workflow, audit log, hash-matching - see LEGAL.md.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone

from .store import MODERATION

_audit = logging.getLogger("zeim.audit")
_who = lambda sid: hashlib.sha256(("rep:" + (sid or "")).encode()).hexdigest()[:8]       # a stable short tag; never the session id itself
REASONS = ["minor_safety", "not_family_friendly", "copyright", "harassment", "personal_info", "other"]


def report(item_id: str, sid: str, reason: str, details: str) -> dict:
    """One OPEN report per (reporter, item, reason): a repeat returns the existing id. `minor_safety` hides the item at once (fail safe);
    nothing else is ever auto-hidden by a count of reports (CR-11 f)."""
    if reason not in REASONS:
        raise ValueError(f"reason must be one of {REASONS}")
    r = {"id": secrets.token_hex(5), "item_id": item_id, "reporter": sid, "reason": reason,
         "details": (details or "")[:1000], "created": datetime.now(timezone.utc).isoformat(), "status": "open"}
    out = {}

    def f(m):
        same = next((x for x in m["reports"] if x["status"] == "open" and x["reporter"] == sid and x["item_id"] == item_id and x["reason"] == reason), None)
        if same:
            out.update(id=same["id"], status="open", auto_hidden=same["reason"] == "minor_safety", duplicate=True)
            return
        m["reports"].append(r)
        if reason == "minor_safety" and item_id not in m["hidden"]:
            m["hidden"].append(item_id)   # fail safe: hidden until a human reviews
            _audit.info("moderation auto-hide: item=%s report=%s reason=minor_safety reporter=%s at=%s", item_id, r["id"], _who(sid), r["created"])
        out.update(id=r["id"], status="open", auto_hidden=reason == "minor_safety")
    MODERATION.update(f)
    if not out.get("duplicate"):
        _audit.info("moderation report: item=%s report=%s reason=%s reporter=%s at=%s", item_id, out["id"], reason, _who(sid), r["created"])
    return out


def queue() -> list[dict]:
    return [r for r in MODERATION.read()["reports"] if r["status"] == "open"]


def resolve(report_id: str, action: str) -> dict:
    if action not in ("hide", "restore", "dismiss"):
        raise ValueError("action must be hide|restore|dismiss")
    out = {}

    def f(m):
        r = next((x for x in m["reports"] if x["id"] == report_id), None)
        if not r:
            raise KeyError(report_id)
        i = r["item_id"]
        if action == "hide" and i not in m["hidden"]:
            m["hidden"].append(i)
        elif action == "restore" and i in m["hidden"]:
            m["hidden"].remove(i)
        r["status"] = "dismissed" if action == "dismiss" else "actioned"
        r["resolved"] = datetime.now(timezone.utc).isoformat()
        out.update(r)
    MODERATION.update(f)
    _audit.info("moderation %s: item=%s report=%s reporter=%s reported_at=%s at=%s", action, out["item_id"], report_id, _who(out["reporter"]), out["created"], out["resolved"])
    return out


def oldest_open_age_s():
    """Seconds since the oldest still-open report was filed (None when the queue is empty)."""
    q = queue()
    if not q:
        return None
    t = min(datetime.fromisoformat(r["created"]) for r in q)
    return max(0, int((datetime.now(timezone.utc) - t).total_seconds()))
