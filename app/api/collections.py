"""Showcase collections API: creators group their own models; public adults browse them.

Routes live under /api. Ownership of every listed model is enforced server-side: you can
only add projects you published. Hidden / private projects drop out of other people's
views automatically (catalog.get).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from ..community import catalog, collections as cols, privacy, safety
from ..community import identity as idn
from ..community.identity import Actor, get_actor
from ..core import ratelimit
from . import guards
from .textcap import text_in

router = APIRouter(prefix="/api")


def _member(actor: Actor):
    if not actor.user:
        raise HTTPException(401, "Make a free account first.")
    if not actor.is_adult:
        raise HTTPException(403, "This account can't do that right now.")


def _err(e: Exception):
    if isinstance(e, safety.ChatBlocked):
        return JSONResponse(status_code=e.status, content=e.payload)
    raise HTTPException(400, str(e))


def _name(actor: Actor, body: dict) -> str:
    v = text_in(body.get("name"), cols.NAME_MAX, "Name")
    return safety.gate(actor, v, "collections:name", False) if v else ""


def _pub(c: dict, actor: Actor, *, with_items: bool = False) -> dict:
    mine = c["owner_sid"] == actor.sid
    out = {"id": c["id"], "name": c["name"], "public": bool(c.get("public")),
           "count": len(c.get("items") or []), "mine": mine,
           "updated": c.get("updated"), "created": c.get("created"),
           "share_url": f"/api/collections/{c['id']}"}
    if with_items:
        items = []
        for iid in c.get("items") or []:
            try:
                items.append(catalog.public(catalog.get(iid, actor), actor))
            except catalog.Denied:
                continue
        out["items"] = items
        # viewers only see the count of models still visible to them
        if not mine:
            out["count"] = len(items)
    return out


@router.get("/me/collections")
def my_collections(item: str = "", actor: Actor = Depends(get_actor)):
    guards.showcase_gate(actor)
    if not actor.user:
        return {"collections": [], "holding": []}
    return {"collections": [_pub(c, actor) for c in cols.of_owner(actor.sid)],
            "holding": cols.holding(actor.sid, item[:40]) if item else []}


@router.post("/me/collections")
def new_collection(body: dict, actor: Actor = Depends(get_actor)):
    guards.showcase_gate(actor)
    _member(actor)
    if not ratelimit.hit("col:" + actor.sid, 60, 3600):
        raise HTTPException(429, "That's a lot of new collections. Please wait a little.")
    try:
        name = _name(actor, body or {})
        c = cols.create(actor.sid, actor.user["id"], name, public=bool((body or {}).get("public", True)))
    except (ValueError, safety.ChatBlocked) as e:
        return _err(e)
    return _pub(c, actor)


@router.put("/me/collections/{cid}")
def edit_collection(cid: str, body: dict, actor: Actor = Depends(get_actor)):
    """Rename and/or set public. Partial: only send the fields you want to change."""
    guards.showcase_gate(actor)
    _member(actor)
    body = body or {}
    try:
        c = None
        if "name" in body:
            c = cols.rename(actor.sid, cid, _name(actor, body))
        if "public" in body:
            c = cols.set_public(actor.sid, cid, bool(body.get("public")))
        if c is None:
            c = cols.get(cid)
            if not c or c["owner_sid"] != actor.sid:
                raise KeyError(cid)
    except KeyError:
        raise HTTPException(404, "not found")
    except (ValueError, safety.ChatBlocked) as e:
        return _err(e)
    return _pub(c, actor)


@router.delete("/me/collections/{cid}")
def remove_collection(cid: str, actor: Actor = Depends(get_actor)):
    guards.showcase_gate(actor)
    if not actor.user or not cols.delete(actor.sid, cid):
        raise HTTPException(404, "not found")
    return {"ok": True}


@router.post("/me/collections/{cid}/items")
def collection_item(cid: str, body: dict, actor: Actor = Depends(get_actor)):
    """{"item_id": str, "on": bool}. Only projects YOU published can be added."""
    guards.showcase_gate(actor)
    _member(actor)
    body = body or {}
    iid = str(body.get("item_id", ""))[:40]
    on = bool(body.get("on", True))
    if on:
        try:
            i = catalog.get(iid, actor)
        except catalog.Denied as e:
            raise HTTPException(e.status, e.msg)
        if i.get("owner_sid") != actor.sid or i.get("example"):
            raise HTTPException(403, "You can only add your own Showcase projects to a collection.")
    if not ratelimit.hit("colitem:" + actor.sid, 600, 3600):
        raise HTTPException(429, "That's a lot of taps. Please wait a little.")
    try:
        c = cols.set_item(actor.sid, cid, iid, on)
    except KeyError:
        raise HTTPException(404, "not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {**_pub(c, actor), "on": on}


@router.get("/collections/{cid}")
def get_collection(cid: str, actor: Actor = Depends(get_actor)):
    guards.showcase_gate(actor)
    c = cols.get(cid[:40])
    if not c or not (c.get("public") or c["owner_sid"] == actor.sid):
        raise HTTPException(404, "not found")
    _, u = idn.user_by_id(c.get("uid", ""))
    if c["owner_sid"] != actor.sid:
        if not u or u.get("suspended") or not privacy.can_view_profile(actor, c.get("uid", "")):
            raise HTTPException(404, "not found")
    out = _pub(c, actor, with_items=True)
    out["by"] = "@" + u["username"] if u and u.get("username") else "a ZEIM maker"
    out["creator_id"] = c.get("uid")
    return out


@router.get("/users/{uid}/collections")
def user_collections(uid: str, actor: Actor = Depends(get_actor)):
    guards.showcase_gate(actor)
    _, u = idn.user_by_id(uid)
    if not u or u.get("suspended") or not privacy.can_view_profile(actor, uid):
        raise HTTPException(404, "unknown user")
    return {"collections": [_pub(c, actor) for c in cols.public_of(uid)]}
