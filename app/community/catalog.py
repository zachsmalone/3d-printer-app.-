"""Showcase catalog: community projects. EVERYTHING IS FREE - there is no pricing, paywall or
locked file in this product. Seed items are EXAMPLES (example=true), not real creator content.
"""
from __future__ import annotations

import json
import re
import secrets
import shutil
from datetime import datetime, timezone

from .. import config
from ..config import DATA, OUT, MAX_BUILDS
from .identity import Actor
from . import classrooms, privacy
from ..services.credits import credit_line
from .store import ENGAGEMENT, LISTINGS, MODERATION, USERS

LDIR = DATA / "projects"
LDIR.mkdir(exist_ok=True)


class Denied(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status, self.msg = status, msg


CREATORS = {"ex-ada": "Example: Ada", "ex-ben": "Example: Ben", "ex-cleo": "Example: Cleo"}


def _seed():
    def it(i, who, title, tags, mode, dl, desc, day):
        return {"id": f"ex{i:02d}", "title": title, "creator": CREATORS[who], "creator_id": who, "example": True,
                "tags": tags, "mode": mode, "downloads": dl, "likes": dl // 9, "description": desc,
                "created": f"2026-09-{day:02d}T00:00:00+00:00", "files": [],            # examples have no model yet: nothing to download until a real Original is attached
                
                "owner_sid": None, "visibility": "public", "hidden": False}
    return [
        it(1, "ex-ada", "Sunset Landscape Lithophane", ["landscape", "lithophane", "nightlight"], "lithophane", 1840, "A warm sunset panel tuned for backlit display.", 2),
        it(2, "ex-ben", "Pet Portrait Relief Frame", ["pets", "portrait", "relief", "gift"], "relief", 920, "Raised relief frame template for pet photos.", 9),
        it(3, "ex-cleo", "Pop-art Burst Starter", ["popart", "halftone", "poster"], "popart", 1210, "Four-layer halftone pop-art starter.", 12),
        it(4, "ex-ada", "Moon Phases Lamp Panel", ["space", "lithophane", "lamp", "nightlight"], "lithophane", 2300, "A moon-phase panel for a small lamp.", 5),
        it(5, "ex-cleo", "Floral Layers Pop-art", ["floral", "popart", "gift"], "popart", 640, "Layered flowers that stand off the page.", 20),
        it(6, "ex-ben", "Skyline Night Panel", ["landscape", "city", "lithophane"], "lithophane", 705, "City skyline with deep shadows.", 15),
        it(7, "ex-ada", "Classroom Dino Relief", ["kids", "classroom", "relief", "dinosaur"], "relief", 1500, "Friendly dino relief, great first print for a class.", 22),
        it(8, "ex-ben", "Family Portrait Frame", ["gift", "portrait", "lithophane"], "lithophane", 380, "Simple frame style for family portraits.", 25),
        it(9, "ex-cleo", "Retro Comic Halftone", ["popart", "comic", "halftone"], "popart", 510, "Comic-dot look in five layers.", 27),
    ]


def _all() -> list[dict]:
    hidden = set(MODERATION.read()["hidden"])
    items = _seed() + LISTINGS.read()
    eng = ENGAGEMENT.read()
    for i in items:
        i["hidden"] = i["id"] in hidden
        # base = example seed numbers (or legacy counters); plus ONE per distinct visitor session
        i["_likers"] = eng["likes"].get(i["id"], [])
        i["_dlers"] = eng["downloads"].get(i["id"], [])
        # EXAMPLE seed items carry invented numbers: they never take part in ranking (and are not shown) unless the flag says so
        seed_ok = not i.get("example") or config.SHOW_COUNTS_FOR_EXAMPLES
        i["_likes"] = (int(i.get("likes", 0)) if seed_ok else 0) + len(i["_likers"])
        i["_downloads"] = (int(i.get("downloads", 0)) if seed_ok else 0) + len(i["_dlers"])
    return items


def is_public(i: dict, users: dict | None = None) -> bool:
    """Only PUBLIC projects take part in likes / download counts / Trending (private & followers-only never do)."""
    if i["hidden"]:
        return False
    if not i.get("owner_sid"):
        return i.get("visibility", "public") == "public"
    users = USERS.read() if users is None else users
    return privacy.effective(i.get("visibility", "private"), users.get(i["owner_sid"])) == "public"


# ---- Trending score (documented in README) ----
LIKE_WEIGHT, DOWNLOAD_WEIGHT, HALF_LIFE_DAYS, DECAY_FLOOR = 3.0, 1.0, 21.0, 0.15


def trending_score(i: dict, now: datetime | None = None) -> float:
    """score = ln(1 + 3*likes + 1*downloads) * (0.15 + 0.85 * 0.5^(age_days / 21))
    likes/downloads are distinct-visitor counts; the log damps runaway totals, recency decay lets newer work surface."""
    import math
    now = now or datetime.now(timezone.utc)
    try:
        age = max(0.0, (now - datetime.fromisoformat(i["created"])).total_seconds() / 86400)
    except Exception:
        age = 0.0
    eng = LIKE_WEIGHT * i.get("_likes", 0) + DOWNLOAD_WEIGHT * i.get("_downloads", 0)
    return math.log1p(eng) * (DECAY_FLOOR + (1 - DECAY_FLOOR) * 0.5 ** (age / HALF_LIFE_DAYS))


def _visible(actor: Actor, users: dict):
    return lambda i: (not i["hidden"]) and privacy.can_view(actor, i.get("owner_sid"), i.get("visibility", "private"), users)


def counts_visible(i: dict, users: dict) -> bool:
    """May like/download numbers for this item be shown to people? (Examples: only if the flag says so; minors: not by default.)"""
    if not is_public(i, users):
        return False
    if i.get("example") and not config.SHOW_COUNTS_FOR_EXAMPLES:
        return False
    owner_u = users.get(i.get("owner_sid")) if i.get("owner_sid") else None
    return not (config.HIDE_COUNTS_FOR_MINORS and privacy.is_minor(owner_u))


def resolve(i: dict, users: dict | None = None) -> dict:
    """Credit follows the ACCOUNT, not a copy of its name: the uploader's CURRENT username is looked up by account id every time, so a rename
    updates every old credit, and the display name (which may be a real name) is never shown as the creator of a community project."""
    if i.get("example") or not i.get("creator_id"):
        return i
    users = USERS.read() if users is None else users
    tu = next((u for u in users.values() if u.get("id") == i["creator_id"]), None)
    name = (tu or {}).get("username") or i.get("creator_username")           # account gone -> the last known username
    return {**i, "creator_username": name, "creator": "@" + name} if name else i


def public(i: dict, actor: Actor) -> dict:
    following = bool(actor.user and i["creator_id"] in actor.user.get("following", []))
    users = USERS.read()
    tu = next((u for u in users.values() if u["id"] == i["creator_id"]), None)
    pub = is_public(i, users)
    i = resolve(i, users)
    show_counts = counts_visible(i, users)
    return {"likes": i.get("_likes", 0) if show_counts else None, "liked": bool(pub and actor.sid in i.get("_likers", [])),
            "liked_by_others": bool(pub and i.get("owner_sid") == actor.sid and i.get("_likes", 0) > 0),
            "counts_hidden": bool(pub and not show_counts),
            "can_like": bool(pub and i.get("owner_sid") != actor.sid and (classrooms.showcase_policy(actor.sid) or {"likes": True})["likes"]),
            "visibility": privacy.effective(i.get("visibility", "private"), users.get(i.get("owner_sid"))) if i.get("owner_sid") else "public",
            "can_follow": privacy.can_follow(actor, tu, bool(i.get("example"))),"id": i["id"], "title": i["title"], "creator": i["creator"], "creator_id": i["creator_id"],
            "example": i.get("example", False), "tags": i["tags"], "mode": i["mode"],
            "downloads": i.get("_downloads", 0) if show_counts else None, "description": i["description"], "created": i["created"],
            "owned": bool(i.get("owner_sid") and i["owner_sid"] == actor.sid), "following_creator": following,
            "share_url": f"/p/{i['id']}",
            "creator_username": i.get("creator_username"), "credit": credit_line(i), "no_model": not i["files"],
            "thumb": f"/api/showcase/{i['id']}/thumb" if i.get("has_thumb") else None,
            "files": [{"name": f["name"], "size_kb": f["size_kb"],
                       "url": f"/api/showcase/{i['id']}/files/{f['name']}"} for f in i["files"]]}


def get(item_id: str, actor: Actor) -> dict:
    """Return a project only if `actor` may see it (private/followers-only look like 404 to others)."""
    ok = _visible(actor, USERS.read())
    for i in _all():
        if i["id"] == item_id and ok(i):
            return i
    raise Denied(404, "not found")


def list_items(actor: Actor, tab: str, q: str = "", weights: dict | None = None) -> list[dict]:
    ok = _visible(actor, USERS.read())
    items = [i for i in _all() if ok(i)]
    if q:
        terms = q.lower().split()
        items = [i for i in items if all(t in (i["title"] + " " + " ".join(i["tags"]) + " " + i["description"]).lower() for t in terms)]
    if tab == "foryou":
        w = weights or {}
        scored = [(sum(w.get(t, 0) for t in i["tags"]), i) for i in items]
        return [i for s, i in sorted(scored, key=lambda x: (-x[0], -trending_score(x[1]))) if s > 0]
    if tab == "free":    # everything is free: newest first
        return sorted(items, key=lambda i: i["created"], reverse=True)
    users = USERS.read()   # Trending: public projects only, ranked by likes + downloads with recency decay
    now = datetime.now(timezone.utc)
    # score ties (e.g. examples without counts, brand-new projects) fall back to newest first
    pubs = sorted([i for i in items if is_public(i, users)], key=lambda i: i["created"], reverse=True)
    return sorted(pubs, key=lambda i: -trending_score(i, now))


def known_tags(actor: Actor) -> set[str]:
    ok = _visible(actor, USERS.read())
    return {t for i in _all() if ok(i) for t in i["tags"]}


def mine(actor: Actor) -> list[dict]:
    return [i for i in _all() if i.get("owner_sid") == actor.sid and not i["hidden"]]


def set_visibility(actor: Actor, item_id: str, level: str) -> dict:
    try:
        level = privacy.check_level(actor, level)
    except (ValueError, PermissionError) as e:
        raise Denied(422 if isinstance(e, ValueError) else 403, str(e))
    found = {}

    def f(l):
        for i in l:
            if i["id"] == item_id and i.get("owner_sid") == actor.sid:
                i["visibility"] = level
                found.update(i)
    LISTINGS.update(f)
    if not found:
        raise Denied(404, "not found")
    return found


def create_project(actor: Actor, *, title, description, tags, build_id, accept_guidelines, visibility=None) -> dict:
    if not actor.user:
        raise Denied(401, "Create an account to publish.")
    if not accept_guidelines:
        raise Denied(422, "You must confirm this project follows the Community Guidelines "
                          "(family-friendly only, no content involving minors in any unsafe context).")
    title = (title or "").strip()[:80]
    if not title:
        raise Denied(422, "title required")
    if not build_id.isalnum() or not (OUT / build_id / "meta.json").exists():
        raise Denied(422, "unknown build")
    if json.loads((OUT / build_id / "meta.json").read_text()).get("owner_sid") != actor.sid:
        raise Denied(422, "unknown build")      # you can only publish your own builds
    try:
        visibility = privacy.check_level(actor, visibility or privacy.default_level(actor))
    except ValueError as e:
        raise Denied(422, str(e))
    except PermissionError as e:
        raise Denied(403, str(e))
    from ..services import editproj
    editproj.ensure_exports(build_id)       # edit projects write their STL/3MF lazily
    pid = secrets.token_hex(5)
    d = LDIR / pid
    d.mkdir(parents=True)
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or "model"
    files = []
    for ext in ("3mf", "stl"):
        shutil.copy(OUT / build_id / f"model.{ext}", d / f"{slug}.{ext}")
        files.append({"name": f"{slug}.{ext}", "size_kb": round((d / f"{slug}.{ext}").stat().st_size / 1024)})
    if (OUT / build_id / "thumb.png").exists():
        shutil.copy(OUT / build_id / "thumb.png", d / "thumb.png")
    mode = json.loads((OUT / build_id / "meta.json").read_text())["mode"]
    item = {"id": pid, "title": title, "creator": actor.user["display_name"], "creator_id": actor.user["id"], "creator_username": actor.user.get("username"),
            "example": False, "tags": [t.strip().lower() for t in tags if t.strip()][:8], "mode": mode,
            "downloads": 0, "description": (description or "")[:500],
            "created": datetime.now(timezone.utc).isoformat(), "files": files,
            "owner_sid": actor.sid, "visibility": visibility, "has_thumb": (d / "thumb.png").exists(), "hidden": False}
    LISTINGS.update(lambda l: l.append(item))
    from ..services.history import store as _bs
    _bs.set_saved(build_id)
    return item


def file_path(i: dict, name: str):
    """Real file for user projects; None for seed items (placeholder is generated by the caller)."""
    if i.get("example") or not any(f["name"] == name for f in i["files"]):
        return None
    p = LDIR / i["id"] / name
    return p if p.exists() else None


def thumb_path(i: dict):
    p = LDIR / i["id"] / "thumb.png"
    return p if p.exists() else None


def count_download(i: dict, actor: Actor):
    """Count a download once per visitor session, only for public projects, never for the owner's own downloads."""
    if not is_public(i) or i.get("owner_sid") == actor.sid:
        return

    def f(d):
        lst = d["downloads"].setdefault(i["id"], [])
        if actor.sid not in lst:
            lst.append(actor.sid)
    ENGAGEMENT.update(f)


def set_like(i: dict, actor: Actor, liked: bool | None = None) -> dict:
    """Like / unlike (toggle when `liked` is None). Public projects only; one like per visitor; no dislikes exist."""
    if not is_public(i):
        raise Denied(404, "not found")       # private / followers-only: no likes at all
    if i.get("owner_sid") == actor.sid:
        raise Denied(403, "You can't like your own project.")
    res = {}

    def f(d):
        lst = d["likes"].setdefault(i["id"], [])
        want = (actor.sid not in lst) if liked is None else bool(liked)
        if want and actor.sid not in lst:
            lst.append(actor.sid)
        if not want and actor.sid in lst:
            lst.remove(actor.sid)
        res["liked"] = actor.sid in lst
        res["likes"] = (int(i.get("likes", 0)) if (not i.get("example") or config.SHOW_COUNTS_FOR_EXAMPLES) else 0) + len(lst)
    ENGAGEMENT.update(f)
    if not counts_visible(i, USERS.read()):
        res["likes"] = None
    return res
