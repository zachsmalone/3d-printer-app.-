"""Account badges. Earned by real actions, or seeded. No money and no prizes.

Each badge has visibility "public" (the default) or "private". Public badges
show on profiles and posts. A private badge is visible only to its owner, on
their own badge box. Tester is private, and only username cc0hort is awarded
it. Official OG is permanent once earned and goes to that account plus the
first 100 accounts by creation time. Creator is public and only username
ZeimApp is awarded it.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..services.entitlements import TESTER_USERNAME, grant_pro_comp

CREATOR_USERNAME = "zeimapp"
PLACE_BADGE = {1: "win_gold", 2: "win_silver", 3: "win_bronze"}
from .store import PRINTS, USERS

OG_LIMIT = 100
EXPORT_EXTS = frozenset({"stl", "3mf", "gcode"})

TESTER_NOTE = (
    "cc0hort, thank you. You found problems before anyone else had to. "
    "You helped find the solutions, and the inspiring things you create show what this app can be. "
    "You believed in me, and you are part of the reason I made ZEIM. — Zach"
)

# Order is the order on the Account card.
# visibility "private" stays on the owner's badge box. Missing visibility is public.
# `auto` is not a task: it shows only after it has been earned.
CATALOG = (
    {
        "id": "tester",
        "name": "Tester",
        "label": "Thank you for being a tester",
        "note": TESTER_NOTE,
        "private": True,
        "visibility": "private",
        "how": "",
    },
    {
        "id": "creator",
        "name": "Creator",
        "label": "ZEIM founder",
        "visibility": "public",
        "auto": True,
        "how": "",
    },
    {
        "id": "official_og",
        "name": "Official OG",
        "label": "One of the first 100 accounts.",
        "auto": True,
        "how": "",
    },
    {
        "id": "first_slice",
        "name": "First Slice",
        "event": "fdm_slice",
        "need": 1,
        "how": "Slice a model in the FDM Slicer.",
    },
    {
        "id": "first_export",
        "name": "First Export",
        "event": "export",
        "need": 1,
        "how": "Download G-code, 3MF, or STL.",
    },
    {
        "id": "first_print",
        "name": "First Print",
        "event": "print_shared",
        "need": 1,
        "how": 'Post an "I printed this" photo.',
    },
    {
        "id": "first_lithophane",
        "name": "First Lithophane",
        "event": "lithophane",
        "need": 1,
        "how": "Make a lithophane from a photo.",
    },
    {
        "id": "first_resin",
        "name": "First Resin slice",
        "event": "resin_slice",
        "need": 1,
        "how": "Prepare a model in TorchC0.",
    },
    {
        "id": "first_cad",
        "name": "First CAD model saved",
        "event": "cad_save",
        "need": 1,
        "how": "Save a CAD model.",
    },
    {
        "id": "first_showcase",
        "name": "First Showcase publish",
        "event": "showcase",
        "need": 1,
        "how": "Publish a project to Showcase.",
    },
    {
        "id": "first_remix",
        "name": "First Remix",
        "event": "remix",
        "need": 1,
        "how": "Publish a project that credits a remix.",
    },
    {
        "id": "challenge_entrant",
        "name": "Challenge Entrant",
        "event": "challenge",
        "need": 1,
        "how": "Enter a remix challenge.",
    },
    {
        "id": "prints_10",
        "name": "10 Prints Shared",
        "event": "print_shared",
        "need": 10,
        "how": 'Share 10 "I printed this" photos.',
    },
    {"id": "win_gold", "name": "Gold winner", "tier": "gold", "auto": True, "visibility": "public", "how": ""},
    {"id": "win_silver", "name": "Silver winner", "tier": "silver", "auto": True, "visibility": "public", "how": ""},
    {"id": "win_bronze", "name": "Bronze winner", "tier": "bronze", "auto": True, "visibility": "public", "how": ""},
    {"id": "likes_10", "name": "10 likes", "event": "likes_received", "need": 10, "visibility": "public", "how": "Try sharing work people nozzle."},
    {"id": "likes_50", "name": "50 likes", "event": "likes_received", "need": 50, "visibility": "public", "how": "Try sharing work people nozzle."},
    {"id": "likes_100", "name": "100 likes", "event": "likes_received", "need": 100, "visibility": "public", "how": "Try sharing work people nozzle."},
    {"id": "likes_500", "name": "500 likes", "event": "likes_received", "need": 500, "visibility": "public", "how": "Try sharing work people nozzle."},
    {"id": "challenge_likes_10", "name": "Challenge likes", "event": "challenge_likes", "need": 10, "visibility": "public", "how": "Try entering a challenge."},
    {"id": "supports_bronze", "name": "Supports", "tier": "bronze", "event": "supports_slice", "need": 1, "visibility": "public", "how": "Try a slice with supports on."},
    {"id": "supports_silver", "name": "Supports", "tier": "silver", "event": "supports_slice", "need": 3, "visibility": "public", "how": "Try a slice with supports on."},
    {"id": "supports_gold", "name": "Supports", "tier": "gold", "event": "supports_slice", "need": 10, "visibility": "public", "how": "Try a slice with supports on."},
    {"id": "split_bronze", "name": "Smart split", "tier": "bronze", "event": "smart_split", "need": 1, "visibility": "public", "how": "Try Smart split with a connector."},
    {"id": "infill_bronze", "name": "Adaptive infill", "tier": "bronze", "event": "adaptive_infill", "need": 1, "visibility": "public", "how": "Try adaptive infill."},
    {"id": "litho_detail", "name": "Fine lithophane", "tier": "gold", "event": "litho_detail", "need": 1, "visibility": "public", "how": "Try a lithophane at a high detail setting."},
    {"id": "fillet_bronze", "name": "Fillet", "tier": "bronze", "event": "fillet", "need": 1, "visibility": "public", "how": "Try a fillet or chamfer in CAD."},
    {"id": "remixed_by_others", "name": "Remixed onward", "event": "remixed_by", "need": 1, "visibility": "public", "how": "Try publishing something others remix."},
    {"id": "printed_by_5", "name": "Printed by others", "event": "printed_by_others", "need": 5, "visibility": "public", "how": "Try a model that 5 other people print."},
)

_BY_ID = {spec["id"]: spec for spec in CATALOG}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _order_key(sid: str, user: dict) -> tuple:
    created = user.get("created")
    if isinstance(created, str) and created:
        return (0, created, sid)
    return (1, "", sid)


def _grant(user: dict, badge_id: str) -> bool:
    """Add a badge once. Never removes one, and never rewrites earned_at."""
    have = user.get("badges")
    if not isinstance(have, dict):
        have = {}
        user["badges"] = have
    if badge_id in have:
        return False
    have[badge_id] = {"earned_at": _now()}
    unseen = user.get("badge_unseen")
    if not isinstance(unseen, list):
        unseen = []
        user["badge_unseen"] = unseen
    if badge_id not in unseen:
        unseen.append(badge_id)
    return True


def apply_seed(users: dict) -> dict:
    """Grant OG, the tester badge, and the Pro comp. Mutates `users`. Safe to run again.

    Official OG goes to the first 100 accounts by `created` (missing dates sort last)
    and always to username cc0hort. Already-earned badges stay, even if that account
    would no longer fall inside the first 100.
    """
    stats = {"comp": 0, "og": 0, "tester": 0}
    if not isinstance(users, dict):
        return stats
    ranked = sorted(
        ((sid, u) for sid, u in users.items() if isinstance(u, dict)),
        key=lambda su: _order_key(su[0], su[1]),
    )
    for i, (_sid, user) in enumerate(ranked):
        if i >= OG_LIMIT:
            break
        if _grant(user, "official_og"):
            stats["og"] += 1
    for user in users.values():
        if not isinstance(user, dict):
            continue
        if (user.get("username") or "").lower() == CREATOR_USERNAME and _grant(user, "creator"):
            stats["creator"] = stats.get("creator", 0) + 1
        if (user.get("username") or "").lower() != TESTER_USERNAME:
            continue
        if grant_pro_comp(user):
            stats["comp"] += 1
        if _grant(user, "tester"):
            stats["tester"] += 1
        if _grant(user, "official_og"):
            stats["og"] += 1
    return stats


def seed() -> dict:
    """Idempotent startup / sign-up seed. Looks up cc0hort by username."""
    stats: dict = {}

    def f(data):
        stats.update(apply_seed(data))

    USERS.update(f)
    return stats


def print_share_count(sid: str) -> int:
    """Posted "I printed this" photos for this account. Rejected ones do not count."""
    n = 0
    for row in PRINTS.read():
        if not isinstance(row, dict):
            continue
        if row.get("owner_sid") != sid:
            continue
        if row.get("status") == "rejected":
            continue
        n += 1
    return n


def record(sid: str, event: str, *, count: int | None = None) -> list[dict]:
    """Count one real event and award any badge that crosses its line. Idempotent awards.

    `count` sets the progress (used for photos, which are counted from the store).
    Without it, progress goes up by one. Awards are never removed if the count later drops.
    Unknown events and unknown accounts award nothing.
    """
    specs = [spec for spec in CATALOG if spec.get("event") == event]
    if not sid or not specs:
        return []
    newly: list[str] = []

    def f(data):
        if not isinstance(data, dict):
            return
        user = data.get(sid)
        if not isinstance(user, dict):
            return
        prog = user.get("badge_progress")
        if not isinstance(prog, dict):
            prog = {}
            user["badge_progress"] = prog
        if count is None:
            prog[event] = int(prog.get(event) or 0) + 1
        else:
            prog[event] = int(count)
        have_now = int(prog.get(event) or 0)
        for spec in specs:
            need = int(spec.get("need") or 1)
            if have_now >= need and _grant(user, spec["id"]):
                newly.append(spec["id"])

    USERS.update(f)
    return [{"id": badge_id, "name": _BY_ID[badge_id]["name"]} for badge_id in newly]


def award_for(actor, *events: str) -> list[dict]:
    """Award for a signed-in account. Guests and unknown events get nothing."""
    if actor is None or not getattr(actor, "user", None) or not getattr(actor, "sid", None):
        return []
    found: list[dict] = []
    seen: set[str] = set()
    for event in events:
        live = print_share_count(actor.sid) if event == "print_shared" else None
        for badge in record(actor.sid, event, count=live):
            if badge["id"] not in seen:
                seen.add(badge["id"])
                found.append(badge)
    return found


def merge(payload: dict, actor, *events: str) -> dict:
    """Copy `payload` and add `badges_new` when this action earned something."""
    earned = award_for(actor, *events)
    if not earned:
        return payload
    out = dict(payload)
    prev = [b for b in (out.get("badges_new") or []) if isinstance(b, dict)]
    ids = {b.get("id") for b in prev}
    for badge in earned:
        if badge["id"] not in ids:
            prev.append(badge)
    out["badges_new"] = prev
    return out


def _stamp(response, earned: list[dict]):
    if earned and response is not None:
        response.headers["X-Zeim-Badges"] = ",".join(f"{badge['id']}|{badge['name']}" for badge in earned)
    return response


def stamp(response, actor, event: str):
    return _stamp(response, award_for(actor, event))


def stamp_sid(response, sid: str, event: str):
    """Award an export to the account that produced the file (slice downloads have no cookie)."""
    if not sid:
        return response
    user = USERS.read().get(sid)
    if not isinstance(user, dict):
        return response

    class _Who:
        pass

    who = _Who()
    who.sid = sid
    who.user = user
    return stamp(response, who, event)


def _visibility(spec: dict) -> str:
    """public, or private (only the owner sees it). Private is the Tester badge unless a spec says otherwise."""
    vis = spec.get("visibility")
    if vis in ("public", "private"):
        return vis
    return "private" if spec.get("private") else "public"


def _is_tester(user: dict) -> bool:
    return (user.get("username") or "").lower() == TESTER_USERNAME


def _rows(user: dict, *, owner: bool) -> list[dict]:
    have = user.get("badges") if isinstance(user.get("badges"), dict) else {}
    prog = user.get("badge_progress") if isinstance(user.get("badge_progress"), dict) else {}
    tester = _is_tester(user)
    out = []
    for spec in CATALOG:
        earned = spec["id"] in have
        private = _visibility(spec) == "private"
        if private:
            # Private-to-owner, and only after it is earned. Tester stays on
            # cc0hort's own box even if the id is copied onto another account.
            if not (owner and earned) or (spec["id"] == "tester" and not tester):
                continue
        elif spec.get("auto") and not earned:
            continue
        need = int(spec.get("need") or 1)
        progress = int(prog.get(spec["event"]) or 0) if spec.get("event") else 0
        note = ""
        if earned and owner and private:
            note = spec.get("note") or ""
        row = {
            "id": spec["id"],
            "name": spec["name"],
            "earned": earned,
            "how": "" if earned else (spec.get("how") or ""),
            "label": spec.get("label") or "",
            "note": note,
            "tier": spec.get("tier") or "",
            "visibility": _visibility(spec),
        }
        if earned:
            stored = have.get(spec["id"]) if isinstance(have.get(spec["id"]), dict) else {}
            row["earned_at"] = stored.get("earned_at")
        elif need > 1:
            row["progress"] = progress
            row["need"] = need
        out.append(row)
    return out


def for_owner(sid: str) -> dict:
    user = USERS.read().get(sid)
    if not isinstance(user, dict):
        return {"signed_up": False, "badges": [], "unseen": []}
    rows = _rows(user, owner=True)
    visible = {row["id"] for row in rows}
    unseen_ids = user.get("badge_unseen") if isinstance(user.get("badge_unseen"), list) else []
    unseen = []
    for badge_id in unseen_ids:
        if badge_id not in visible or badge_id not in _BY_ID:
            continue
        unseen.append({"id": badge_id, "name": _BY_ID[badge_id]["name"]})
    n = win_tally(user)
    return {"signed_up": True, "badges": rows, "unseen": unseen, "win_tally": n, "win_label": win_label(n)}


def public_earned(user: dict | None) -> list[dict]:
    """Earned badges safe to show on a public profile. Tester is never included."""
    if not isinstance(user, dict):
        return []
    have = user.get("badges") if isinstance(user.get("badges"), dict) else {}
    out = []
    for spec in CATALOG:
        if _visibility(spec) == "private":
            continue
        if spec["id"] in have:
            out.append({"id": spec["id"], "name": spec["name"]})
    return out


def win_tally(user: dict | None) -> int:
    if not isinstance(user, dict):
        return 0
    wins = user.get("challenge_wins")
    return len(wins) if isinstance(wins, list) else 0


def win_label(n: int) -> str:
    return f"Monthly winner ×{n}" if n else ""


def award_winners(winners: list[dict], challenge_id: str) -> None:
    """One gold, silver, or bronze badge per place, and one tick on the win tally. Idempotent per challenge."""
    def f(data):
        if not isinstance(data, dict):
            return
        for w in winners:
            sid = w.get("owner_sid") or ""
            place = int(w.get("place") or 0)
            badge_id = PLACE_BADGE.get(place)
            user = data.get(sid)
            if not badge_id or not isinstance(user, dict):
                continue
            wins = user.get("challenge_wins")
            if not isinstance(wins, list):
                wins = []
                user["challenge_wins"] = wins
            if any(isinstance(row, dict) and row.get("challenge_id") == challenge_id for row in wins):
                continue
            wins.append({"challenge_id": challenge_id, "place": place})
            _grant(user, badge_id)
    USERS.update(f)


def note_likes(owner_sid: str, *, received: int, on_entries: int) -> list[dict]:
    """Award like milestones from a real like count. Challenge-entry likes are counted again on their own line."""
    found = []
    seen = set()
    for badge in record(owner_sid, "likes_received", count=received) + record(owner_sid, "challenge_likes", count=on_entries):
        if badge["id"] not in seen:
            seen.add(badge["id"])
            found.append(badge)
    return found


def mark_seen(sid: str) -> None:
    def f(data):
        user = data.get(sid) if isinstance(data, dict) else None
        if isinstance(user, dict):
            user["badge_unseen"] = []

    USERS.update(f)
