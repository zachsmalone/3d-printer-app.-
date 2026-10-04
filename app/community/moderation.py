"""Reporting + moderation queue (STUB-level but functional locally). Family-friendly only.

Reports are stored; `minor_safety` reports hide the item immediately pending review.
The queue is only readable with header X-Admin-Token == PHOTO3D_ADMIN_TOKEN (unset = disabled).
Real launch needs: trained reviewers, escalation + NCMEC reporting for CSAM, takedown/appeals
workflow, audit log, hash-matching - see LEGAL.md.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from .store import MODERATION

REASONS = ["minor_safety", "not_family_friendly", "copyright", "harassment", "personal_info", "other"]


def report(item_id: str, sid: str, reason: str, details: str) -> dict:
    if reason not in REASONS:
        raise ValueError(f"reason must be one of {REASONS}")
    r = {"id": secrets.token_hex(5), "item_id": item_id, "reporter": sid, "reason": reason,
         "details": (details or "")[:1000], "created": datetime.now(timezone.utc).isoformat(), "status": "open"}

    def f(m):
        m["reports"].append(r)
        if reason == "minor_safety" and item_id not in m["hidden"]:
            m["hidden"].append(item_id)   # fail safe: hidden until a human reviews
    MODERATION.update(f)
    return {"id": r["id"], "status": "open", "auto_hidden": reason == "minor_safety"}


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
        out.update(r)
    MODERATION.update(f)
    return out
