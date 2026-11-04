"""Self-serve 'Delete my account' (owner decision 2026-11-03).

request(): marks the account, disables its passkey/email/password login and ends every session at once.
purge_due(): removes marked accounts and their data. It runs at startup and then hourly in-process (no cron),
so a marked account is gone well within the 7 days the privacy page promises.

Removed: the account record, its auth login (accounts/credentials/sessions rows), builds and Edit projects,
parked uploads, shared Showcase projects, "I printed this" photos, collections, questions it asked, challenge
entries, favorites, preferences, learning progress, notices, and its sid in like/download lists.
Kept: anonymous Trending counters (hashed, not linkable) and moderation reports (safety records).
"""
from __future__ import annotations

import logging
import shutil
import threading
import time

from .store import (CHALLENGE_ENTRIES, COLLECTIONS, ENGAGEMENT, FAVORITES, LISTINGS, PREFS, PRINTS, PROGRESS,
                    QUESTIONS, USERS)

log = logging.getLogger("zeim.audit")
MARK = "delete_requested_at"


def _auth_ids(svc, user_id: str) -> list[str]:
    rows = svc.store.all("SELECT id FROM accounts WHERE id=? OR legacy_id=?", (user_id, user_id)) if user_id else []
    return [r["id"] for r in rows]


def request(sid: str, svc=None, now: float | None = None) -> None:
    now = now or time.time()
    uid = (USERS.read().get(sid) or {}).get("id", "")
    USERS.update(lambda d: d[sid].__setitem__(MARK, now))
    if svc is not None:
        for aid in _auth_ids(svc, uid):
            svc.store.run("UPDATE accounts SET disabled_at=? WHERE id=?", (now, aid))
            svc.revoke_all(aid)
    log.info("account deletion requested: account=%s", uid)


def is_marked(user: dict | None) -> bool:
    return bool(user and user.get(MARK))


def _purge(sid: str, user: dict, svc=None) -> None:
    from . import catalog, notify, ownership
    from .social import PDIR
    from ..services import quarantine
    ownership.purge_builds(sid)
    quarantine.purge_for(sid)
    for i in [i for i in LISTINGS.read() if i.get("owner_sid") == sid]:
        shutil.rmtree(catalog.LDIR / i["id"], ignore_errors=True)
    for p in [p for p in PRINTS.read() if p.get("owner_sid") == sid]:
        (PDIR / f"{p['id']}.{p['ext']}").unlink(missing_ok=True)

    def keep(store, key):
        store.update(lambda l: l.__setitem__(slice(None), [x for x in l if x.get(key) != sid]))
    keep(LISTINGS, "owner_sid"); keep(PRINTS, "owner_sid"); keep(COLLECTIONS, "owner_sid")
    keep(QUESTIONS, "asker_sid"); keep(CHALLENGE_ENTRIES, "owner_sid"); keep(notify.NOTICES, "sid")
    for store in (FAVORITES, PREFS, PROGRESS):
        store.update(lambda d: d.pop(sid, None))

    def scrub(e):
        for part in e.values():
            if isinstance(part, dict):
                for k, v in part.items():
                    if isinstance(v, list) and sid in v:
                        part[k] = [x for x in v if x != sid]
    ENGAGEMENT.update(scrub)
    if svc is not None:
        for aid in _auth_ids(svc, user.get("id", "")):
            for t in ("sessions", "credentials", "email_codes", "ceremonies"):
                try:
                    svc.store.run(f"DELETE FROM {t} WHERE account_id=?", (aid,))
                except Exception:
                    pass                      # table without account_id
            svc.store.run("DELETE FROM accounts WHERE id=?", (aid,))
    USERS.update(lambda d: d.pop(sid, None))
    log.info("account deleted: account=%s", user.get("id", ""))


def purge_due(svc=None) -> int:
    due = [(sid, u) for sid, u in USERS.read().items() if is_marked(u)]
    for sid, u in due:
        try:
            _purge(sid, u, svc)
        except Exception:
            log.exception("account purge failed: account=%s", u.get("id", ""))
    return len(due)


def start_background(app, interval_s: int = 3600):
    def loop():
        while True:
            try:
                purge_due(getattr(app.state, "auth_service", None))
            except Exception:
                log.exception("account purge run failed")
            time.sleep(interval_s)
    t = threading.Thread(target=loop, name="zeim-account-purge", daemon=True)
    t.start()
    return t
