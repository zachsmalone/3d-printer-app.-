"""Reporting + moderation queue (STUB-level but functional locally). Mild NSFW is allowed when tagged; explicit content is removed.

Reports are stored; `minor_safety` reports hide the item immediately pending review.
`underage_user` = "this account holder seems to be under 18" (ZEIM is 18+ only). It names the ACCOUNT (account_id); a moderator
can resolve it with action "suspend", which suspends the account (its content is then shown to nobody else, it can't share or send).
Accounts and data are never deleted by this process; suspension is reversible.
The queue is only readable with header X-Admin-Token == PHOTO3D_ADMIN_TOKEN (unset = disabled).
Launch workflow: appeals (appeal()), a persistent audit trail (log/audit_trail), secure evidence preservation
(preserve()) and NCMEC escalation (escalate_ncmec) — see docs/legal/ncmec-procedure.md.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ..config import DATA
from .store import MODERATION

_audit = logging.getLogger("zeim.audit")
_who = lambda sid: hashlib.sha256(("rep:" + (sid or "")).encode()).hexdigest()[:8]       # a stable short tag; never the session id itself
REASONS = ["minor_safety", "underage_user", "not_family_friendly", "copyright", "harassment", "personal_info", "should_be_nsfw", "other"]
# mark_nsfw / unmark_nsfw flip the item's mature tag; remove = take explicit content down (same as hide, logged as removal)
ACTIONS = ("hide", "restore", "dismiss", "suspend", "mark_nsfw", "unmark_nsfw", "remove")


def report(item_id: str, sid: str, reason: str, details: str, account_id: str | None = None,
           ip: str = "", user_agent: str = "") -> dict:
    """One OPEN report per (reporter, item, reason): a repeat returns the existing id. `minor_safety` hides the item at once (fail safe);
    nothing else is ever auto-hidden by a count of reports (CR-11 f).
    ip/user_agent are recorded for moderation use ONLY (never shown publicly) — required context for
    NCMEC escalation (docs/legal/ncmec-procedure.md)."""
    if reason not in REASONS:
        raise ValueError(f"reason must be one of {REASONS}")
    if reason == "underage_user" and not account_id:
        raise ValueError("This item has no account to report.")
    r = {"id": secrets.token_hex(5), "item_id": item_id, "reporter": sid, "reason": reason,
         "details": (details or "")[:1000], "account_id": account_id, "created": datetime.now(timezone.utc).isoformat(), "status": "open",
         "ip": (ip or "")[:64], "user_agent": (user_agent or "")[:200]}
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
        _log("report", report_id=out["id"], item=item_id, reason=reason)
    return out


def queue() -> list[dict]:
    return [r for r in MODERATION.read()["reports"] if r["status"] in ("open", "appealed")]


def _log(action: str, **kw) -> None:
    """Persistent audit trail: every moderation event appends one entry (who/what/when)."""
    entry = {"at": datetime.now(timezone.utc).isoformat(), "action": action, **kw}

    def f(m):
        m.setdefault("log", []).append(entry)
    MODERATION.update(f)


def audit_trail(limit: int = 200) -> list[dict]:
    """Newest-first moderation audit entries (admin-only view)."""
    return list(reversed(MODERATION.read().get("log", [])))[:limit]


def resolve(report_id: str, action: str) -> dict:
    if action not in ACTIONS:
        raise ValueError("action must be " + "|".join(ACTIONS))
    out = {}

    def f(m):
        r = next((x for x in m["reports"] if x["id"] == report_id), None)
        if not r:
            raise KeyError(report_id)
        if r["status"] == "escalated_ncmec":
            raise ValueError("This report is escalated for NCMEC reporting — it stays on the escalated queue.")
        i = r["item_id"]
        if action == "suspend" and not r.get("account_id"):
            raise ValueError("this report names no account to suspend")
        if action in ("hide", "suspend", "remove") and i and not i.startswith("user:") and i not in m["hidden"]:
            m["hidden"].append(i)
        elif action == "restore" and i in m["hidden"]:
            m["hidden"].remove(i)
        r["status"] = "dismissed" if action == "dismiss" else "actioned"
        r["resolved"] = datetime.now(timezone.utc).isoformat()
        out.update(r)
    MODERATION.update(f)
    if action in ("mark_nsfw", "unmark_nsfw"):
        set_nsfw(out["item_id"], action == "mark_nsfw")
    if action == "suspend":
        suspend(out["account_id"], "report " + report_id)
    _audit.info("moderation %s: item=%s report=%s reporter=%s reported_at=%s at=%s", action, out["item_id"], report_id, _who(out["reporter"]), out["created"], out["resolved"])
    _log(action, report_id=report_id, item=out["item_id"], was_appealed=out.get("was_appealed", False))
    return out


def appeal(report_id: str, sid: str, text: str = "") -> dict:
    """The person affected by a decision asks for it to be looked at again.
    Only the account whose item was actioned (or the reported account itself) may appeal. The
    report re-enters the queue as "appealed"; a moderator re-resolves it (restore = uphold,
    dismiss/remove = reject)."""
    out = {}

    def f(m):
        r = next((x for x in m["reports"] if x["id"] == report_id), None)
        if not r:
            raise KeyError(report_id)
        if r["status"] == "open":
            raise ValueError("This report is still open — it has not been decided yet.")
        if r["status"] not in ("actioned", "dismissed"):
            raise ValueError(f"This report cannot be appealed (status {r['status']}).")
        owner_ok = (r.get("reporter") == sid)
        if not owner_ok and r["item_id"].startswith("user:"):
            from .store import USERS
            owner_ok = any(u.get("id") == r["item_id"][5:] and k == sid for k, u in USERS.read().items())
        if not owner_ok:
            from .store import LISTINGS
            owner_ok = any(i.get("id") == r["item_id"] and i.get("owner_sid") == sid for i in LISTINGS.read())
        if not owner_ok:
            raise PermissionError("Only the person the decision was about can appeal it.")
        r["appeal"] = {"by": sid, "text": (text or "")[:1000], "at": datetime.now(timezone.utc).isoformat()}
        r["status"] = "appealed"
        out.update(r)
    MODERATION.update(f)
    _audit.info("moderation appeal: report=%s by=%s", report_id, _who(sid))
    _log("appeal", report_id=report_id, item=out["item_id"])
    return out


def appeal_for_item(item_id: str, sid: str, text: str = "") -> dict:
    """User-facing appeal: appeal the most recent DECIDED report about this item. Raises KeyError if none."""
    reports = sorted((r for r in MODERATION.read()["reports"] if r["item_id"] == item_id
                      and r["status"] in ("actioned", "dismissed")), key=lambda r: r["created"])
    if not reports:
        raise KeyError(item_id)
    return appeal(reports[-1]["id"], sid, text)


def _preservation_dir(report_id: str) -> Path:
    p = DATA / "preservation" / report_id
    p.mkdir(parents=True, exist_ok=True)
    try:
        p.chmod(0o700)          # only the server account can read preserved evidence
    except OSError:
        pass
    return p


def preserve(report_id: str) -> dict:
    """Securely preserve the reported content + report context for possible law-enforcement reporting.
    Copies the item's files into DATA/preservation/<report_id>/ (mode 700, never served by any route)
    with a sidecar holding the report context (reason, reporter tag, ip/user_agent, timestamps).
    Evidence is preserved BEFORE any escalation decision (docs/legal/ncmec-procedure.md)."""
    r = next((x for x in MODERATION.read()["reports"] if x["id"] == report_id), None)
    if not r:
        raise KeyError(report_id)
    item_id = r["item_id"]
    dest = _preservation_dir(report_id)
    copied = []
    sources: list[Path] = []
    if item_id.startswith("print:"):
        sources = sorted((DATA / "prints").glob(item_id[6:] + ".*"))
    elif item_id.startswith("user:"):
        sources = []          # an account report: the user record stays in place (never deleted)
    else:
        d = DATA / "projects" / item_id
        if d.is_dir():
            sources = sorted(p for p in d.iterdir() if p.is_file())
    for p in sources:
        shutil.copy2(p, dest / p.name)
        try:
            (dest / p.name).chmod(0o600)
        except OSError:
            pass
        copied.append(p.name)
    sidecar = {"report": {k: v for k, v in r.items() if k != "details"},
               "reporter_tag": _who(r.get("reporter", "")), "preserved_at": datetime.now(timezone.utc).isoformat(),
               "files": copied}
    (dest / "context.json").write_text(json.dumps(sidecar, indent=1, default=str))
    _log("preserve", report_id=report_id, item=item_id, files=len(copied))
    return {"report_id": report_id, "files": copied, "dir": str(dest)}


def escalate_ncmec(report_id: str, note: str = "") -> dict:
    """Mark a report as escalated for NCMEC CyberTipline reporting. Does NOT auto-submit anything:
    a human files the report (docs/legal/ncmec-procedure.md) — this records the decision, requires
    the evidence to be preserved first, and puts the report on the escalated queue."""
    r = next((x for x in MODERATION.read()["reports"] if x["id"] == report_id), None)
    if not r:
        raise KeyError(report_id)
    if not (DATA / "preservation" / report_id / "context.json").exists():
        raise ValueError("Preserve the evidence first (moderation.preserve) — never escalate without it.")
    out = {}

    def f(m):
        rr = next((x for x in m["reports"] if x["id"] == report_id), None)
        if not rr:
            raise KeyError(report_id)
        rr["status"] = "escalated_ncmec"
        rr["escalated"] = {"at": datetime.now(timezone.utc).isoformat(), "note": (note or "")[:500]}
        out.update(rr)
    MODERATION.update(f)
    _audit.critical("moderation NCMEC escalation: report=%s item=%s", report_id, out["item_id"])
    _log("escalate_ncmec", report_id=report_id, item=out["item_id"])
    return out


def oldest_open_age_s():
    """Seconds since the oldest still-open report was filed (None when the queue is empty)."""
    q = queue()
    if not q:
        return None
    t = min(datetime.fromisoformat(r["created"]) for r in q)
    return max(0, int((datetime.now(timezone.utc) - t).total_seconds()))


def suspend(account_id: str, why: str = "") -> bool:
    """Suspend an account (reversible; deletes nothing). Returns False if no such account."""
    from .store import USERS
    done = []

    def f(d):
        for u in d.values():
            if u.get("id") == account_id:
                u["suspended"] = {"at": datetime.now(timezone.utc).isoformat(), "why": why[:100]}
                done.append(1)
    USERS.update(f)
    if done:
        _audit.info("moderation suspend: account=%s why=%s", account_id, why[:100])
    return bool(done)


def unsuspend(account_id: str) -> bool:
    from .store import USERS
    done = []

    def f(d):
        for u in d.values():
            if u.get("id") == account_id and u.pop("suspended", None):
                done.append(1)
    USERS.update(f)
    if done:
        _audit.info("moderation unsuspend: account=%s", account_id)
    return bool(done)


def set_nsfw(item_id: str, on: bool) -> bool:
    """Moderator flips the mature tag on a Showcase project or a print photo ("print:<id>"). Returns False if not found."""
    from .store import LISTINGS
    done = []
    if item_id.startswith("print:"):
        from .store import PRINTS

        def f(l):
            for p in l:
                if p["id"] == item_id[6:]:
                    p["nsfw"] = bool(on); done.append(1)
        PRINTS.update(f)
    else:
        def g(l):
            for i in l:
                if i["id"] == item_id:
                    i["nsfw"] = bool(on); done.append(1)
        LISTINGS.update(g)
    if done:
        _audit.info("moderation nsfw=%s: item=%s", bool(on), item_id)
    return bool(done)
