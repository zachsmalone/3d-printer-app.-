"""Parts builder API (original code, new file — the protected edit.py is untouched).

A parts project is an ordinary edit project whose step 1 is the 'parts' op: the recipe
(primitive list) IS the model's source of truth, stored in the existing step history.
Creating: compose the recipe, admit it through the SAME ownership/history/disk gates as
every other project, then append the parts step. Editing the recipe goes through the SAME
parametric step-editing machinery (edit_step) — recomposition preserves any manual steps
added after it, and undo/redo work unchanged.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from ..community import privacy, safety
from ..community.identity import Actor, get_actor
from ..core import meshedit, parts
from ..services import editproj
from ..services.history import HistoryFull, store
from .builds import _safe_title, disk_guard, meta_for, summary
from .textcap import text_in

router = APIRouter(prefix="/api/parts", tags=["parts"])


def _full(actor: Actor):
    from .builds import full_response
    return full_response(actor)


def _recipe_of(bid: str, actor: Actor, owner_only: bool = True) -> dict:
    """Owner-checked: the recipe stored in step 1 of a parts project."""
    meta = meta_for(bid, actor, owner_only=owner_only)
    ops = meta.get("ops") or []
    if not ops or ops[0].get("op") != "parts":
        raise HTTPException(409, "This project was not made in the parts builder.")
    return meta, ops[0].get("params") or {}


@router.post("/new")
def new_parts_project(body: dict, actor: Actor = Depends(get_actor)):
    """Create a project from a recipe of primitives. The recipe becomes step 1 (editable,
    undoable); the composed mesh is the project's base + exports, so slicing / printing /
    sharing all work through the existing flow."""
    try:
        title = _safe_title(body.get("title") or "My parts build")
        safety.filter_only(title, "Title")
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        recipe = parts.check_recipe(body.get("recipe"))
        mesh, rep = parts.compose(recipe)                 # validate BEFORE touching history
    except parts.RecipeError as e:
        raise HTTPException(400, str(e))
    from trimesh.exchange import stl as _stl
    original = _stl.export_stl(mesh)                      # binary STL (mm) — public format
    disk_guard()
    with store.lock:
        try:
            store.reserve(actor.sid, bool(body.get("auto_delete_oldest")))
        except HistoryFull:
            return _full(actor)
        try:
            meta = editproj.create(actor.sid, privacy.default_level(actor), title=title,
                                   base={"type": "parts"}, original=original, original_ext="stl",
                                   mesh=mesh, beginner=bool(body.get("beginner", True)),
                                   warnings=["Built from primitives in the parts builder — edit the recipe any time."])
        except meshedit.OpError as e:
            raise HTTPException(422, str(e))
        # step 1 = the recipe itself (parametric: edit_step on it recomposes the model)
        try:
            editproj.add_op(meta["id"], "parts", recipe)
        except (meshedit.OpError, ValueError) as e:
            store.delete(meta["id"])
            raise HTTPException(422, str(e))
    out = editproj.payload(meta["id"], rep)
    return {**out, "recipe": recipe,
            "history": [summary(m) for m in store.list(actor.sid)]}


@router.get("/projects")
def my_parts_projects(actor: Actor = Depends(get_actor)):
    """The actor's parts builds, newest first — the saved-project picker on the builder
    page (a reachable 'edit recipe' path for existing projects; owner-scoped)."""
    out = []
    for meta in store.list(actor.sid):
        ops = meta.get("ops") or []
        if not ops or ops[0].get("op") != "parts":
            continue
        out.append({"id": meta["id"], "title": (meta.get("title") or "Untitled")[:60],
                    "created": meta.get("created"),
                    "triangles": (meta.get("stats") or {}).get("triangles")})
    out.sort(key=lambda p: p["created"] or "", reverse=True)
    return {"projects": out}


@router.get("/{bid}/recipe")
def get_recipe(bid: str, actor: Actor = Depends(get_actor)):
    _, recipe = _recipe_of(bid, actor)
    return {"id": bid, "recipe": recipe}


@router.put("/{bid}/recipe")
def put_recipe(bid: str, body: dict, actor: Actor = Depends(get_actor)):
    """Replace the recipe — parametric recomposition: step 1 is re-run with the new recipe
    and every later step replays on top (so manual edits made after the recipe survive)."""
    _, old = _recipe_of(bid, actor)
    try:
        recipe = parts.check_recipe(body.get("recipe"))
    except parts.RecipeError as e:
        raise HTTPException(400, str(e))
    try:
        editproj.edit_step(bid, 1, recipe)
    except meshedit.OpError as e:
        raise HTTPException(422, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except safety.ChatBlocked as e:
        return JSONResponse(status_code=e.status, content=e.payload)
    return {**editproj.payload(bid), "recipe": recipe}
