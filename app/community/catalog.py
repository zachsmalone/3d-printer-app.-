"""Showcase catalog: community projects. EVERYTHING IS FREE - there is no pricing, paywall or
locked file in this product. Seed items are the ZEIM Originals (original=true) from library/originals.
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
from . import originals_qa, privacy
from ..services.credits import credit_line
from ..services.history import store as _bstore
from .store import ENGAGEMENT, LISTINGS, MODERATION, USERS

LDIR = DATA / "projects"
LDIR.mkdir(exist_ok=True)


class Denied(Exception):
    def __init__(self, status, msg, extra: dict | None = None):
        super().__init__(msg)
        self.status, self.msg, self.extra = status, msg, extra or {}


CREATORS: dict = {}      # the old invented "Example: Ada/Ben/Cleo" seed creators are gone (Originals-first, Oct 2026)

# ---- ZEIM Originals (library/originals, NOT in git: the deploy ships the folder separately; see config.ORIGINALS) ----
WILDLIFE = "Wildlife Calls"
_MCACHE: dict = {}


def _manifest() -> dict:
    p = config.ORIGINALS / "originals_manifest.json"
    try:
        key = (str(p), p.stat().st_mtime)
    except OSError:
        return {}
    if _MCACHE.get("key") != key:
        _MCACHE.update(key=key, data=json.loads(p.read_text()))
    return _MCACHE["data"]


# Category names shown to makers. School features were removed (2026-10-12), so the manifest's "School STEM" shows as plain "STEM & Science".
CATEGORY_LABEL = {"School STEM": "STEM & Science"}


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 1) if f > 0 else None


def _size(x: dict):
    """Real bounding box from the manifest, in mm ({x, y, z, note}); None when the manifest has no usable size (never guessed)."""
    d = x.get("dimensions_mm") or {}
    xyz = {k: _num(d.get(k)) for k in ("x", "y", "z")} if isinstance(d, dict) else {}
    if not xyz or None in xyz.values():
        return None
    return {**xyz, "note": str(d.get("note", ""))[:160]}


def _parts(x: dict) -> list[dict]:
    """Kit parts: {name, size_mm:[x, y, z]} when the manifest gives three real sizes, or {name, about} when it describes the part
    in words ("hex-scute shell with inner lip"). A row that is neither is dropped, never filled in."""
    out = []
    for name, v in (x.get("parts") or {}).items() if isinstance(x.get("parts"), dict) else []:
        row = {"name": str(name).replace("_", " ")[:60]}
        if isinstance(v, str) and v.strip():
            row["about"] = v.strip()[:160]
        else:
            nums = [_num(n) for n in (v if isinstance(v, (list, tuple)) else [])][:3]
            if len(nums) != 3 or None in nums:
                continue
            row["size_mm"] = nums
        out.append(row)
    return out[:20]


def _steps(x: dict) -> list[str]:
    """Assembly steps exactly as the manifest words them (they carry their own numbering, e.g. "1-3. Seat the insert"); blanks dropped."""
    raw = x.get("assembly_steps") or []
    return [str(t).strip()[:300] for t in raw if str(t).strip()][:12] if isinstance(raw, list) else []


def _seed():
    """The 45 ZEIM Originals from the manifest (empty list when the library is not installed on this server)."""
    m = _manifest()
    out = []
    for n, x in enumerate(m.get("models", [])):
        stl, png = x.get("file", ""), x.get("preview", "")
        cat = CATEGORY_LABEL.get(x.get("category", ""), x.get("category", ""))
        names = [f for f in originals_qa.PLATES.get(x["slug"], []) if (config.ORIGINALS / f).is_file()] or [stl]
        files = [{"name": f, "size_kb": round((config.ORIGINALS / f).stat().st_size / 1024)} for f in names if f and (config.ORIGINALS / f).is_file()]
        out.append({"id": "zo-" + x["slug"], "slug": x["slug"], "title": x["title"], "creator": "ZEIM", "creator_id": "zeim",
                    "original": True, "example": False, "category": cat, "difficulty": x.get("difficulty", ""),
                    "tags": [t for t in re.split(r"[^a-z0-9]+", (cat + " " + x.get("difficulty", "")).lower()) if t],
                    "size_mm": _size(x), "parts": _parts(x), "assembly_steps": _steps(x),
                    "supports_level": str(x.get("supports_needed", ""))[:40], "supports_detail": str(x.get("supports_detail", ""))[:400],
                    "mode": "original", "downloads": 0, "likes": 0, "description": x.get("description", ""),
                    "how_used": x.get("how_it_is_used", ""), "material": x.get("suggested_material_and_print_notes", ""),
                    "caveats": x.get("fit_notes", ""), "printer": x.get("printer", ""), "untested_note": x.get("untested_note", ""),
                    "needs_supports": x["slug"] in originals_qa.NEEDS_SUPPORTS,
                    "low_contact": originals_qa.LOW_CONTACT.get(x["slug"], ""), "plates": len(files) > 1,
                    "license_id": "cc-by-4.0", "created": f"2026-10-01T00:{n // 60:02d}:{n % 60:02d}+00:00", "files": files,
                    "preview": png if png and (config.ORIGINALS / png).is_file() else "", "has_thumb": bool(png and (config.ORIGINALS / png).is_file()),
                    "owner_sid": None, "visibility": "public", "hidden": False})
    return out


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


def counts_visible(i: dict, users: dict, actor=None) -> bool:
    """May nozzle/download numbers for this item be shown? (Public items only; examples only if the flag says so.)"""
    if not is_public(i, users):
        return False
    return not (i.get("example") and not config.SHOW_COUNTS_FOR_EXAMPLES)


def resolve(i: dict, users: dict | None = None) -> dict:
    """Credit follows the ACCOUNT, not a copy of its name: the uploader's CURRENT username is looked up by account id every time, so a rename
    updates every old credit, and the display name (which may be a real name) is never shown as the creator of a community project."""
    if i.get("example") or not i.get("creator_id"):
        return i
    users = USERS.read() if users is None else users
    tu = next((u for u in users.values() if u.get("id") == i["creator_id"]), None)
    name = (tu or {}).get("username") or i.get("creator_username")           # account gone -> the last known username
    return {**i, "creator_username": name, "creator": "@" + name} if name else i


def _proof(i: dict) -> dict:
    from . import originals_proof
    return originals_proof.proof(i["id"])


def public(i: dict, actor: Actor) -> dict:
    following = bool(actor.user and i["creator_id"] in actor.user.get("following", []))
    users = USERS.read()
    tu = next((u for u in users.values() if u["id"] == i["creator_id"]), None)
    pub = is_public(i, users)
    i = resolve(i, users)
    show_counts = counts_visible(i, users, actor)
    return {"likes": i.get("_likes", 0) if show_counts else None, "liked": bool(pub and actor.sid in i.get("_likers", [])),
            "liked_by_others": bool(pub and i.get("owner_sid") == actor.sid and i.get("_likes", 0) > 0),
            "counts_hidden": bool(pub and not show_counts),
            "can_like": bool(pub and i.get("owner_sid") != actor.sid),
            "visibility": privacy.effective(i.get("visibility", "private"), users.get(i.get("owner_sid"))) if i.get("owner_sid") else "public",
            "can_like_reason": ("" if (pub and i.get("owner_sid") != actor.sid) else
                                "own" if i.get("owner_sid") == actor.sid else "not_public"),
            "can_follow": privacy.can_follow(actor, tu, bool(i.get("example"))),"id": i["id"], "title": i["title"], "creator": i["creator"], "creator_id": i["creator_id"],
            "example": i.get("example", False), "nsfw": bool(i.get("nsfw")), "tags": i["tags"], "mode": i["mode"],
            "downloads": i.get("_downloads", 0) if show_counts else None, "description": i["description"], "created": i["created"],
            "owned": bool(i.get("owner_sid") and i["owner_sid"] == actor.sid), "following_creator": following,
            "share_url": f"/p/{i['id']}",
            "original": bool(i.get("original")), "category": i.get("category", ""), "difficulty": i.get("difficulty", ""),
            "printer_suggested": "FDM" if i.get("original") else "", "printer_note": i.get("printer", ""),
            "untested": bool(i.get("original")) and _proof(i)["badge"] != "test_printed", "untested_note": i.get("untested_note", ""),
            "proof": _proof(i) if i.get("original") else None,
            "material": i.get("material", ""), "caveats": i.get("caveats", ""),
            "needs_supports": bool(i.get("needs_supports")), "low_contact": i.get("low_contact", ""), "plates": bool(i.get("plates")), "how_used": i.get("how_used", ""),
            "size_mm": i.get("size_mm") if i.get("original") else None, "parts": i.get("parts", []) if i.get("original") else [],
            "assembly_steps": i.get("assembly_steps", []) if i.get("original") else [],
            "supports_level": i.get("supports_level", "") if i.get("original") else "", "supports_detail": i.get("supports_detail", "") if i.get("original") else "",
            "creator_username": i.get("creator_username"), "credit": credit_line(i),
            "favorited": bool(actor.user) and _social().is_fav(actor.sid, i["id"]), "can_favorite": bool(actor.user),
            "license_id": i.get("license_id") or "",
            **remix_status(i),
            "first_posted": str(i.get("created", ""))[:10],
            "view_only": bool(i.get("view_only")),
            "ai_made": bool(i.get("ai_made")),
            "community_printed": bool(not i.get("example") and _social().prints_for(i["id"])),   # >=1 approved 'I printed this'
            "tip_url": i.get("tip_url") or "",
            "download_blocked": _dl_blocked(i, actor),
            "held_for_review": bool(i.get("owner_sid") == actor.sid and i.get("hidden") and i.get("held")),
            "remix_chain": remix_chain(i, actor), "prints_count": len(_social().prints_for(i["id"])), "no_model": not i["files"],
            "thumb": f"/api/showcase/{i['id']}/thumb" if i.get("has_thumb") else None,
            "files": [{"name": f["name"], "size_kb": f["size_kb"],
                       "url": None if _dl_blocked(i, actor) else f"/api/showcase/{i['id']}/files/{f['name']}"} for f in i["files"]]}


VIEW_ONLY_MSG = "The maker made this project view only: you can look at it, but it can't be downloaded."


def _dl_blocked(i: dict, actor) -> bool:
    """'View only, no download': everyone but the owner is refused the files (enforced again in the file route)."""
    return bool(i.get("view_only")) and not (actor is not None and i.get("owner_sid") and i["owner_sid"] == actor.sid)


def _owner_edit(actor: Actor, item_id: str, fn) -> dict:
    found = {}

    def f(l):
        for i in l:
            if i["id"] == item_id and i.get("owner_sid") == actor.sid and not i.get("example"):
                fn(i)
                found["i"] = dict(i)
    LISTINGS.update(f)
    if "i" not in found:
        raise Denied(404, "not found")
    return found["i"]


def set_tip_url(actor: Actor, item_id: str, url) -> dict:
    from . import tips
    try:
        url = tips.check(url)
    except ValueError as e:
        raise Denied(400, str(e))
    return _owner_edit(actor, item_id, lambda i: i.__setitem__("tip_url", url))


def set_ai_made(actor: Actor, item_id: str, on) -> dict:
    """Owner may add the AI-made label; a 2D->3D build keeps it (it is honest provenance)."""
    if not isinstance(on, bool):
        raise Denied(400, "ai_made must be true or false")
    def fn(i):
        if not on and i.get("mode") == "ai3d":
            raise Denied(400, "This model came from the 2D to 3D tab, so it keeps the AI-made label.")
        i["ai_made"] = on
    return _owner_edit(actor, item_id, fn)


def set_view_only(actor: Actor, item_id: str, on) -> dict:
    if not isinstance(on, bool):
        raise Denied(400, "view_only must be true or false")
    found = {}

    def f(l):
        for i in l:
            if i["id"] == item_id and i.get("owner_sid") == actor.sid:
                i["view_only"] = on
                found.update(i)
    LISTINGS.update(f)
    if not found:
        raise Denied(404, "not found")
    return get(item_id, actor)


def allows_remixes(i: dict) -> bool:
    """The maker's 'Allow remixes' switch. Defaults to Yes: projects posted before the switch existed keep allowing them."""
    return i.get("allow_remixes", True) is not False


REMIX_OFF_MSG = "The maker turned off remixes for this project, so it can't be credited as the source of a new one."


def remix_status(i: dict) -> dict:
    """What the Remix button shows: allowed only when the maker's switch is on AND the licence permits adaptations."""
    from . import licensing
    on = allows_remixes(i)
    lic = licensing.may_remix(i.get("license_id"))
    why = "" if (on and lic) else (REMIX_OFF_MSG if not on else
                                   "This project's licence doesn't allow publishing remixes of it.")
    return {"allow_remixes": on, "can_remix": on and lic, "remix_off_reason": why}


def set_allow_remixes(actor: Actor, item_id: str, allow) -> dict:
    """Owner only. Turning remixes off never removes credit from remixes that already exist."""
    if not isinstance(allow, bool):
        raise Denied(400, "allow_remixes must be true or false")
    found = {}

    def f(l):
        for i in l:
            if i["id"] == item_id and i.get("owner_sid") == actor.sid:
                i["allow_remixes"] = allow
                found.update(i)
    LISTINGS.update(f)
    if not found:
        raise Denied(404, "not found")
    return get(item_id, actor)


def _social():
    from . import social
    return social


def remix_chain(i: dict, actor, limit: int = 10) -> list[dict]:
    """'Remixed from X by Y', walking back through the chain. A parent this viewer may not see shows as an unlinked
    'a project that is no longer available' so private work is never revealed."""
    out, seen, cur = [], {i["id"]}, i.get("remix_of")
    if not cur:
        return out
    users = USERS.read()
    ok = _visible(actor, users) if actor is not None else (lambda x: True)
    by_id = {x["id"]: x for x in _all()}
    while cur and cur not in seen and len(out) < limit:
        seen.add(cur)
        p = by_id.get(cur)
        if not p or not ok(p):
            out.append({"id": None, "title": "a project that is no longer available", "creator": None, "creator_id": None})
            break
        p = resolve(p, users)
        out.append({"id": p["id"], "title": p["title"], "creator": p["creator"], "creator_id": p["creator_id"], "url": f"/p/{p['id']}"})
        cur = p.get("remix_of")
    return out


def get(item_id: str, actor: Actor) -> dict:
    """Return a project only if `actor` may see it (private/followers-only look like 404 to others)."""
    ok = _visible(actor, USERS.read())
    for i in _all():
        if i["id"] == item_id and ok(i):
            return i
    raise Denied(404, "not found")


def categories(actor: Actor) -> list[str]:
    ok = _visible(actor, USERS.read())
    return sorted({i["category"] for i in _all() if i.get("category") and ok(i)})


def hides_mature(actor: Actor) -> bool:
    """Mature (artistic-nudity) content is HIDDEN by default, for signed-out visitors too. Only an account that opted in
    (setting 'hide_mature' explicitly False) sees it, and then as a blurred 'Mature content' card with confirm-before-unblur."""
    return not (actor.user and actor.user.get("hide_mature") is False)


def mature_ok(i: dict, actor: Actor) -> bool:
    return not (i.get("nsfw") and hides_mature(actor) and i.get("owner_sid") != actor.sid)


def list_items(actor: Actor, tab: str, q: str = "", weights: dict | None = None, category: str = "") -> list[dict]:
    ok = _visible(actor, USERS.read())
    items = [i for i in _all() if ok(i) and mature_ok(i, actor)]
    if category:
        items = [i for i in items if i.get("category") == category]
    if q:
        terms = q.lower().split()
        items = [i for i in items if all(t in (i["title"] + " " + " ".join(i["tags"]) + " " + i["description"]).lower() for t in terms)]
    if tab == "foryou":
        w = weights or {}
        scored = [(sum(w.get(t, 0) for t in i["tags"]), i) for i in items]
        return [i for s, i in sorted(scored, key=lambda x: (-x[0], -trending_score(x[1]))) if s > 0]
    if tab == "free":    # everything is free: newest first
        return sorted(items, key=lambda i: i["created"], reverse=True)
    if tab == "following":   # projects by the people I follow, newest first (no DMs, no comments: just their work)
        follows = set((actor.user or {}).get("following", []))
        return sorted([i for i in items if i.get("creator_id") in follows], key=lambda i: i["created"], reverse=True)
    from . import social
    users = USERS.read()   # Trending: public projects only, ranked by RECENT favorites / downloads / 'I printed this' / nozzles with time decay
    now = datetime.now(timezone.utc)
    h = social.heat(now.timestamp())
    # score ties (brand-new projects with no activity) fall back to newest first
    pubs = sorted([i for i in items if is_public(i, users)], key=lambda i: i["created"], reverse=True)
    return sorted(pubs, key=lambda i: -social.trending_rank(h.get(i["id"], 0.0), trending_score(i, now)))


def known_tags(actor: Actor) -> set[str]:
    ok = _visible(actor, USERS.read())
    return {t for i in _all() if ok(i) for t in i["tags"]}


def mine(actor: Actor) -> list[dict]:
    return [i for i in _all() if i.get("owner_sid") == actor.sid and not i["hidden"]]


def set_visibility(actor: Actor, item_id: str, level: str, remix_of: str = "") -> dict:
    try:
        level = privacy.check_level(actor, level)
    except (ValueError, PermissionError) as e:
        raise Denied(422 if isinstance(e, ValueError) else 403, str(e))
    mine = next((i for i in _all() if i["id"] == item_id and i.get("owner_sid") == actor.sid), None)
    if not mine:
        raise Denied(404, "not found")
    remix_of = (remix_of or "").strip().rsplit("/p/", 1)[-1].strip("/ ")
    if remix_of:
        try:
            src = get(remix_of, actor)
        except Denied:
            raise Denied(422, "We couldn't find the project you remixed. Paste its Showcase link.")
        if not remix_status(src)["can_remix"]:
            raise Denied(403, REMIX_OFF_MSG)
    if level != "private" and config.DUPLICATE_CHECK and actor.user:
        from . import protect
        fp = protect.FINGERPRINTS.read().get(item_id, {}).get("fp")
        match = protect.find_match(fp, actor.user["id"], remix_of or mine.get("remix_of", ""), exclude=item_id)
        if match:
            c = protect.share_conflict(match)
            raise Denied(409, c["message"], c)
    found = {}

    def f(l):
        for i in l:
            if i["id"] == item_id and i.get("owner_sid") == actor.sid:
                i["visibility"] = level
                if remix_of:
                    i["remix_of"] = remix_of
                found.update(i)
    LISTINGS.update(f)
    if not found:
        raise Denied(404, "not found")
    return found


def create_project(actor: Actor, *, title, description, tags, build_id, accept_guidelines, visibility=None, remix_of: str = "", nsfw: bool | None = None, license_id: str | None = None,
                   allow_remixes: bool = True, view_only: bool = False, ai_made: bool = False, tip_url: str = "") -> dict:
    from . import licensing, tips
    try:
        tip_url = tips.check(tip_url)
    except ValueError as e:
        raise Denied(400, str(e))
    try:
        lid = licensing.check(license_id)              # new projects always carry one (default: private use)
    except ValueError as e:
        raise Denied(400, str(e))                     # spec: an invalid value is a 400
    if not actor.user:
        raise Denied(401, "Create an account to publish.")
    if not accept_guidelines:
        raise Denied(422, "You must confirm this project follows the Community Guidelines "
                          "(mild NSFW only when tagged; nothing explicit; no content involving minors in any unsafe context).")
    if nsfw is None:
        raise Denied(422, "Please answer: Is this NSFW (mild nudity / mature art)? Yes or No.")
    title = (title or "").strip()[:80]
    if not title:
        raise Denied(422, "title required")
    try:
        bmeta = _bstore.get(build_id)
    except KeyError:
        raise Denied(422, "unknown build")
    if bmeta.get("owner_sid") != actor.sid:
        raise Denied(422, "unknown build")      # you can only publish your own builds
    try:
        visibility = privacy.check_level(actor, visibility or privacy.default_level(actor))
    except ValueError as e:
        raise Denied(422, str(e))
    except PermissionError as e:
        raise Denied(403, str(e))
    remix_of = (remix_of or "").strip()
    if remix_of:
        remix_of = remix_of.rsplit("/p/", 1)[-1].strip("/ ")        # accept a share link or a bare id
        try:
            src = get(remix_of, actor)                                # you can only credit a project you can see
        except Denied:
            raise Denied(422, "We couldn't find the project you remixed. Paste its Showcase link.")
        if not allows_remixes(src):
            raise Denied(403, REMIX_OFF_MSG)
        if not licensing.may_remix(src.get("license_id")):
            raise Denied(422, "That project's licence doesn't allow publishing remixes of it. "
                                "Pick a project marked as remixable, or ask its maker to change the licence.")
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
    mode = bmeta["mode"]
    item = {"id": pid, "title": title, "creator": actor.user["display_name"], "creator_id": actor.user["id"], "creator_username": actor.user.get("username"),
            "example": False, "tags": [t.strip().lower() for t in tags if t.strip()][:8], "mode": mode,
            "downloads": 0, "description": (description or "")[:500],
            "created": datetime.now(timezone.utc).isoformat(), "files": files,
            "owner_sid": actor.sid, "visibility": visibility, "has_thumb": (d / "thumb.png").exists(), "hidden": False,
            "nsfw": bool(nsfw), "license_id": lid, "allow_remixes": allow_remixes is not False,
            "view_only": bool(view_only),
            # honest AI label: the creator said so, or the build came from ZEIM's 2D->3D tab (can't be unticked)
            "ai_made": bool(ai_made) or bool(bmeta.get("ai")) or mode == "ai3d"}
    if tip_url:
        item["tip_url"] = tip_url
    if remix_of:
        item["remix_of"] = remix_of
    # re-upload protection: fingerprint the geometry. Sharing (followers / public) a near-match of ANOTHER maker's
    # visible project is not allowed as-is: remixable originals get a credited-remix offer, remix-off ones a refusal.
    # Keeping it Private is always fine (it is also kept in the maker's Studio library either way).
    from . import fingerprint, protect
    fpr = fingerprint.safe_compute(d / f"{slug}.stl")
    match = protect.find_match(fpr, actor.user["id"], remix_of) if config.DUPLICATE_CHECK else None
    warnings = []
    mine_hit = protect.own_match(fpr, actor.user["id"]) if fpr else None
    if mine_hit:
        warnings.append(f"This looks like your project \"{mine_hit['title'][:60]}\". It was posted anyway.")
    if match and visibility != "private":
        shutil.rmtree(d, ignore_errors=True)
        from ..services.history import store as _bs0
        _bs0.set_saved(build_id)
        c = protect.share_conflict(match)
        raise Denied(409, c["message"], c)
    if match:
        item["copy_of"] = match["item"]["id"]          # private copy: fine, but re-checked if it is ever shared
    LISTINGS.update(lambda l: l.append(item))
    protect.remember(pid, fpr)
    item["_warnings"] = warnings
    from ..services.history import store as _bs
    _bs.set_saved(build_id)
    return item


def file_path(i: dict, name: str):
    """Real file for user projects; None for seed items (placeholder is generated by the caller)."""
    if i.get("example") or not any(f["name"] == name for f in i["files"]):
        return None
    if i.get("original"):
        return config.ORIGINALS / name
    p = LDIR / i["id"] / name
    return p if p.exists() else None


def thumb_path(i: dict):
    if i.get("original"):
        return (config.ORIGINALS / i["preview"]) if i.get("preview") else None
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
    _social().record("download", i["id"], actor.sid)


def set_like(i: dict, actor: Actor, liked: bool | None = None) -> dict:
    """Like / unlike (toggle when `liked` is None). Public projects only; one like per visitor; no dislikes exist."""
    if not is_public(i):
        raise Denied(404, "not found")       # private / followers-only: no likes at all
    if i.get("owner_sid") == actor.sid:
        raise Denied(403, "You can't nozzle your own project.")
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
    (_social().record if res["liked"] else _social().unrecord)("nozzle", i["id"], actor.sid)
    if not counts_visible(i, USERS.read(), actor):
        res["likes"] = None
    return res
