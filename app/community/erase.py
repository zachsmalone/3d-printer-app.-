"""Delete ONE account's data, on purpose (the documented underage-account process; see README "Underage accounts").

Never runs automatically. A moderator first suspends the account (POST /api/moderation/users/<id>/suspend), then the
server admin runs:  python tools/delete_user_data.py <account id>            (dry run: lists what would go)
                    python tools/delete_user_data.py <account id> --confirm  (deletes)
Removes: the account record (date of birth included), its builds / Edit projects (source photos included), its Showcase
projects, its "I printed this" photos, its personalization data and favorites, and follows of it. Reports about it stay
(with the account id only) so moderators keep a record of what was done.
"""
from __future__ import annotations

import logging
import shutil

_audit = logging.getLogger("zeim.audit")


def plan(account_id: str) -> dict | None:
    from .identity import user_by_id
    from .store import LISTINGS, PRINTS
    sid, u = user_by_id(account_id)
    if not u:
        return None
    from ..services.history import store
    return {"account_id": account_id, "username": u.get("username"), "suspended": bool(u.get("suspended")),
            "builds": len(store.list(sid)), "projects": sum(1 for i in LISTINGS.read() if i.get("owner_sid") == sid),
            "print_photos": sum(1 for p in PRINTS.read() if p.get("owner_sid") == sid)}


def erase(account_id: str) -> dict | None:
    from . import catalog, ownership, personalization, social
    from .identity import user_by_id
    from .store import LISTINGS, PRINTS, USERS
    sid, u = user_by_id(account_id)
    if not u:
        return None
    out = plan(account_id)
    ownership.purge_builds(sid)
    for pid in [i["id"] for i in LISTINGS.read() if i.get("owner_sid") == sid]:
        shutil.rmtree(catalog.LDIR / pid, ignore_errors=True)
    LISTINGS.update(lambda l: l.__setitem__(slice(None), [i for i in l if i.get("owner_sid") != sid]))
    for p in [p for p in PRINTS.read() if p.get("owner_sid") == sid]:
        social.delete_print(p["id"], sid)
    personalization.clear(sid)
    social.clear_person(sid)

    def f(d):
        d.pop(sid, None)
        for other in d.values():
            if account_id in other.get("following", []):
                other["following"].remove(account_id)
    USERS.update(f)
    _audit.info("account data deleted: account=%s builds=%s projects=%s print_photos=%s",
                account_id, out["builds"], out["projects"], out["print_photos"])
    return out
