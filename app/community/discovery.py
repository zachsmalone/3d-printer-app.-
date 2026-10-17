"""Sort options and related items for the showcase (docs/specs/showcase-gaps.md, items 4-5).

Both operate on catalog items AFTER the existing tab/visibility filtering, so nothing
here can surface a hidden, private or age-gated project. Sorting re-orders the tab's
already-filtered result set (the set itself is unbounded — there is no page or limit);
related items are compact public summaries — the full `catalog.public()` payload is
deliberately NOT embedded per related project.

Limits: related items cap 6 — up to 3 same-maker first, then same-tag matches fill
the remaining slots (so zero maker matches can yield 6 tag matches). An explicit
sort overrides the tab's own ordering (e.g. Trending decay weights) — documented
behaviour.
"""
from __future__ import annotations

SORTS = ("newest", "likes", "printed")
_PER_BUCKET = 3


def check_sort(sort: str) -> str:
    """'' (tab default) or a valid sort id; anything else raises ValueError."""
    if sort in ("", *SORTS):
        return sort
    raise ValueError(f"sort must be one of {' | '.join(SORTS)} (or omitted)")


def apply_sort(items: list[dict], sort: str) -> list[dict]:
    """Re-order an already-filtered item list (the list itself is unbounded). Ties break newest-first."""
    if sort not in SORTS:
        return items                                   # tab default: untouched
    def created(i: dict) -> str:
        return i.get("created", "")
    if sort == "newest":
        return sorted(items, key=created, reverse=True)
    if sort == "likes":
        return sorted(items, key=lambda i: (len(i.get("_likers", [])), created(i)), reverse=True)
    # printed: "I printed this" photo records on the project
    from . import social
    return sorted(items, key=lambda i: (len(social.prints_for(i["id"])), created(i)), reverse=True)


def related(i: dict, actor) -> list[dict]:
    """Up to 6 related projects for a listing: same maker first, then same primary tag.

    Compact summaries only (id, title, creator_id, licence, thumb URL, why). The pool is
    `list_items(actor, "free")` — the same visibility + maturity filter the showcase uses.
    """
    from . import catalog
    from .store import MODERATION
    cid = i.get("creator_id", "")
    primary = (i.get("tags") or [None])[0]
    # spec: hidden or REPORTED projects never appear — an open report keeps an item out of
    # related lists while a human reviews it, even though it stays visible in the showcase
    # itself (only minor_safety auto-hides; reports must not become a hide-any-item vector)
    reported = {r["item_id"] for r in MODERATION.read()["reports"] if r.get("status") == "open"}
    pool = [x for x in catalog.list_items(actor, "free")       # visible + mature-ok, newest first
           if x["id"] not in reported]
    by_maker = [x for x in pool if x.get("creator_id") == cid and x["id"] != i["id"]][:_PER_BUCKET]
    chosen = {x["id"]: (x, "maker") for x in by_maker}
    if primary:
        for x in pool:
            if len(chosen) >= 2 * _PER_BUCKET:
                break
            if primary in (x.get("tags") or []) and x["id"] != i["id"] and x["id"] not in chosen:
                chosen[x["id"]] = (x, "tag")
    return [{
        "id": x["id"], "title": x["title"], "creator_id": x.get("creator_id", ""), "why": why,
        "license_id": x.get("license_id") or "",
        "photo": f"/api/showcase/{x['id']}/thumb",
        "url": f"/api/showcase/{x['id']}",
    } for x, why in chosen.values()]
