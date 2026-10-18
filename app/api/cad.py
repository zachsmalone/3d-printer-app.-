"""CAD workspace API (original code). A CAD project is an ordinary edit project: every solid
feature is a history step (meshedit.OPS via app/core/cadops.py), so undo/redo, step editing with
replay, delete, exports, slicing and the plate editor are the existing machinery. This router adds:
  * POST /api/cad/new                 - start a project from its first feature (step 1, editable)
  * POST /api/cad/sketch/solve        - run the constraint solver on a sketch
  * POST /api/cad/sketch/regions      - closed profile regions (preview / click-to-pick)
  * POST /api/cad/sketch/offset|trim  - sketch editing helpers
  * GET  /api/cad/{bid}/bodies        - the bodies (connected solids) at the current step
  * PUT  /api/cad/{bid}/step/{i}/name - rename a history step
  * PUT  /api/cad/{bid}/appearance    - per-body colours / finish (display only, not in the mesh)
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from ..community import privacy, safety
from ..community.identity import Actor, get_actor
from ..core import cadops, meshedit
from ..core import sketch as sk
from ..services import editproj
from ..services.history import HistoryFull, store
from .builds import _safe_title, disk_guard, meta_for, summary
from .textcap import plain_text, text_in

router = APIRouter(prefix="/api/cad", tags=["cad"])
FIRST_OPS = ("sketch_extrude", "revolve")


def _sk(body: dict) -> dict:
    try:
        return sk.check(body.get("sketch") or {})
    except sk.SketchError as e:
        raise HTTPException(400, str(e))


@router.post("/sketch/solve")
def solve(body: dict):
    try:
        return sk.solve(_sk(body))
    except sk.SketchError as e:
        raise HTTPException(400, str(e))


@router.post("/sketch/regions")
def regions(body: dict):
    s = _sk(body)
    picks = body.get("picks") or None
    try:
        if picks:
            picks = [sk._pt(p, "pick") for p in picks[:64]]
        return {"regions": sk.region_rings(s, picks), "faces": sk.faces(s)}
    except sk.SketchError as e:
        raise HTTPException(400, str(e))


@router.post("/sketch/offset")
def offset(body: dict):
    s = _sk(body)
    try:
        return {"entity": sk.offset(s, str(body.get("id")), body.get("distance", 1))}
    except sk.SketchError as e:
        raise HTTPException(400, str(e))


@router.post("/sketch/trim")
def trim(body: dict):
    s = _sk(body)
    try:
        return {"replace": str(body.get("id")), "entities": sk.trim(s, str(body.get("id")), body.get("at"))}
    except sk.SketchError as e:
        raise HTTPException(400, str(e))


@router.post("/new")
def new_project(body: dict, actor: Actor = Depends(get_actor)):
    """Start a CAD project from its first solid feature (Extrude or Revolve of a sketch)."""
    try:
        title = plain_text(text_in(body.get("title") or "My design", 60, "Title"), "Title") or "My design"
        safety.filter_only(title, "Title")
    except safety.ChatBlocked as e:
        return JSONResponse(status_code=e.status, content=e.payload)
    except ValueError as e:
        raise HTTPException(400, str(e))
    op = body.get("op")
    params = body.get("params") or {}
    if op not in FIRST_OPS or not isinstance(params, dict):
        raise HTTPException(400, f"The first step must be one of {list(FIRST_OPS)}.")
    params = {**params, "replace": True, "mode": "new"}
    import trimesh
    try:
        mesh, rep = meshedit.apply(trimesh.Trimesh(), op, params)
    except meshedit.OpError as e:
        raise HTTPException(422, str(e))
    from trimesh.exchange import stl as _stl
    disk_guard()
    with store.lock:
        try:
            store.reserve(actor.sid, bool(body.get("auto_delete_oldest")))
        except HistoryFull:
            from .builds import full_response
            return full_response(actor)
        meta = None
        try:
            meta = editproj.create(actor.sid, privacy.default_level(actor), title=title, base={"type": "cad"},
                                   original=_stl.export_stl(mesh), original_ext="stl", mesh=mesh,
                                   beginner=bool(body.get("beginner", True)), warnings=[])
            editproj.add_op(meta["id"], op, params)
        except (meshedit.OpError, ValueError) as e:
            if meta:
                store.delete(meta["id"])
            raise HTTPException(422, str(e))
    return {**editproj.payload(meta["id"], rep), "bodies": cadops.body_info(editproj.mesh_at(meta["id"])),
            "history": [summary(m) for m in store.list(actor.sid)]}


def _edit(bid, actor, owner_only=False):
    meta = meta_for(bid, actor, owner_only=owner_only)
    if meta.get("kind") != "edit":
        raise HTTPException(404, "not an edit project")
    return meta


@router.get("/{bid}/bodies")
def bodies(bid: str, actor: Actor = Depends(get_actor)):
    meta = _edit(bid, actor)
    return {"bodies": cadops.body_info(editproj.mesh_at(bid, meta)), "appearance": meta.get("appearance") or {}}


@router.put("/{bid}/step/{i}/name")
def rename(bid: str, i: int, body: dict, actor: Actor = Depends(get_actor)):
    _edit(bid, actor, owner_only=True)
    try:
        name = plain_text(text_in(body.get("name") or "", 40, "Name"), "Name")
        if name:
            safety.filter_only(name, "Name")
        editproj.rename_step(bid, i, name)
    except safety.ChatBlocked as e:
        return JSONResponse(status_code=e.status, content=e.payload)
    except meshedit.OpError as e:
        raise HTTPException(422, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return editproj.payload(bid)


_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
FINISHES = ("matte", "satin", "gloss", "metal", "glass")


@router.put("/{bid}/appearance")
def appearance(bid: str, body: dict, actor: Actor = Depends(get_actor)):
    """{"bodies": {"0": {"color": "#aabbcc", "finish": "satin"}}} - display only (files stay single-colour)."""
    meta = _edit(bid, actor, owner_only=True)
    raw = body.get("bodies")
    if not isinstance(raw, dict) or len(raw) > 64:
        raise HTTPException(400, "bodies must be an object of up to 64 entries.")
    out = {}
    for k, v in raw.items():
        if not str(k).isdigit() or not isinstance(v, dict):
            raise HTTPException(400, "Use body numbers as keys.")
        c, f = v.get("color", "#9aa4b8"), v.get("finish", "satin")
        if not isinstance(c, str) or not _HEX.match(c) or f not in FINISHES:
            raise HTTPException(400, f"color must be #rrggbb and finish one of {list(FINISHES)}.")
        out[str(int(k))] = {"color": c.lower(), "finish": f}
    with store.lock:
        meta = store.get(bid)
        meta["appearance"] = out
        store.save(meta)
        store.cache.pop(bid, None)
    return {"appearance": out}


MAX_SCENE_FACES = 200_000


@router.get("/{bid}/scene")
def scene(bid: str, actor: Actor = Depends(get_actor)):
    """Per-body geometry for the workspace viewer (base64 float32 positions / uint32 indices) plus the
    sharp 'feature' edges (segments, for display and edge picking), the appearance and the history."""
    import base64

    import numpy as np
    meta = _edit(bid, actor)
    m = editproj.mesh_at(bid, meta)
    if len(m.faces) > MAX_SCENE_FACES:
        raise HTTPException(413, "This model is too detailed for the CAD workspace view; open it in the editor instead.")
    out = []
    for i, b in enumerate(cadops.bodies(m)):
        b = b.copy(); b.merge_vertices()
        ang = b.face_adjacency_angles
        e = b.face_adjacency_edges[ang > np.radians(25)]
        segs = b.vertices[e].reshape(-1, 6)
        out.append({"index": i, "name": f"Body {i + 1}",
                    "positions": base64.b64encode(b.vertices.astype("<f4").tobytes()).decode(),
                    "indices": base64.b64encode(b.faces.astype("<u4").tobytes()).decode(),
                    "edges": base64.b64encode(segs.astype("<f4").tobytes()).decode(),
                    "size": np.round(b.extents, 3).tolist(), "center": np.round(b.bounds.mean(axis=0), 3).tolist()})
    p = editproj.payload(bid)
    return {"id": bid, "title": meta.get("title"), "bodies": out, "appearance": meta.get("appearance") or {},
            "ops": p["ops"], "head": p["head"], "can_undo": p["can_undo"], "can_redo": p["can_redo"],
            "analysis": p["analysis"], "base": {k: v for k, v in (meta.get("base") or {}).items() if k in ("type", "format", "units", "photo_mode")}, "downloads": {e: f"/api/download/{bid}/{e}" for e in ("stl", "3mf", "obj")}}
