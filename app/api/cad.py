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

import base64
import re

import numpy as np
import trimesh
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
FIRST_OPS = ("sketch_extrude", "revolve", "cad_text", "cad_shape", "cad_joint")


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
    if op == "cad_text":   # same length cap + language / contact filter as every other model text
        try:
            params = editproj.check_op_text(op, params)
        except safety.ChatBlocked as e:
            return JSONResponse(status_code=e.status, content=e.payload)
        except ValueError as e:
            raise HTTPException(400, str(e))
    params = {**params, "target": "plate", "replace": True} if op == "cad_text" else {**params, "replace": True, "mode": "new"}
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
    mesh = editproj.mesh_at(bid, meta)
    return {"bodies": cadops.body_info(mesh),
            "appearance": cadops.appearance_for_viewer(meta.get("appearance") or {}, mesh)}


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
        key = str(k)
        if not (key.isdigit() or cadops._BODY_ID.match(key)) or not isinstance(v, dict):
            raise HTTPException(400, "Use a body id or a body number.")
        c, f = v.get("color", "#9aa4b8"), v.get("finish", "satin")
        if not isinstance(c, str) or not _HEX.match(c) or f not in FINISHES:
            raise HTTPException(400, f"color must be #rrggbb and finish one of {list(FINISHES)}.")
        out[key if not key.isdigit() else str(int(key))] = {"color": c.lower(), "finish": f}
    with store.lock:
        meta = store.get(bid)
        mesh = editproj.mesh_at(bid, meta)
        try:
            stored = cadops.bind_appearance(out, mesh, strict=True)
        except meshedit.OpError as e:
            raise HTTPException(400, str(e))
        meta["appearance"] = stored
        store.save(meta)
        store.cache.pop(bid, None)
    return {"appearance": cadops.appearance_for_viewer(stored, mesh)}


MAX_SCENE_FACES = 200_000
MAX_SCENE_EDGE_SEGS = 80_000   # a lithophane crease set can be one segment per face; cap the display buffer


def _too_big(n: int) -> HTTPException:
    """Decimation failed: keep the undoable simplified-copy offer. The stored mesh is unchanged."""
    return HTTPException(413, {"message": f"This model has {n:,} triangles, more than the CAD workspace can show ({MAX_SCENE_FACES:,}). "
                                          "You can open a simplified copy here (the original stays in History), or edit it in the editor.",
                               "triangles": n, "limit": MAX_SCENE_FACES,
                               "keep_ratio": round(max(0.02, min(0.98, (MAX_SCENE_FACES * 0.95) / max(n, 1))), 4)})


def _display_mesh(m: trimesh.Trimesh):
    """A viewer copy at or under the face limit. Does not write history or replace the stored mesh."""
    n = int(len(m.faces))
    if n <= MAX_SCENE_FACES:
        return m, False
    target = max(1000, int(MAX_SCENE_FACES * 0.95))
    try:
        import fast_simplification  # optional accelerator; face subsample below is the fallback
        v, f = fast_simplification.simplify(
            np.ascontiguousarray(m.vertices, dtype=np.float32),
            np.ascontiguousarray(m.faces, dtype=np.int32),
            target_count=target)
        dm = trimesh.Trimesh(np.asarray(v), np.asarray(f), process=False)
        if 0 < len(dm.faces) <= MAX_SCENE_FACES:
            return dm, True
    except Exception:
        pass
    idx = np.linspace(0, n - 1, target).astype(int)
    dm = trimesh.Trimesh(m.vertices, m.faces[idx], process=False)
    if len(dm.faces) == 0 or len(dm.faces) > MAX_SCENE_FACES:
        return None, False
    return dm, True


def _scene_body(i: int, b: trimesh.Trimesh) -> tuple[dict, int]:
    pid = cadops.body_id_of(b)
    b = b.copy()
    b.merge_vertices()
    try:
        ang = b.face_adjacency_angles
        e = b.face_adjacency_edges[ang > np.radians(25)]
        segs = b.vertices[e].reshape(-1, 6)
        if len(segs) > MAX_SCENE_EDGE_SEGS:
            segs = segs[np.linspace(0, len(segs) - 1, MAX_SCENE_EDGE_SEGS).astype(int)]
    except Exception:
        segs = np.zeros((0, 6), np.float64)
    nfaces = int(len(b.faces))
    return {"index": i, "id": cadops.public_id(pid) if pid else None, "name": f"Body {i + 1}",
            "positions": base64.b64encode(b.vertices.astype("<f4").tobytes()).decode(),
            "indices": base64.b64encode(b.faces.astype("<u4").tobytes()).decode(),
            "edges": base64.b64encode(np.asarray(segs).astype("<f4").tobytes()).decode(),
            "size": np.round(b.extents, 3).tolist(), "center": np.round(b.bounds.mean(axis=0), 3).tolist()}, nfaces


@router.get("/{bid}/scene")
def scene(bid: str, actor: Actor = Depends(get_actor)):
    """Per-body geometry for the workspace viewer (base64 float32 positions / uint32 indices) plus the
    sharp 'feature' edges (segments, for display and edge picking), the appearance and the history.

    Meshes over MAX_SCENE_FACES are shown from a display-only decimation. Downloads, the slicer and
    history keep the full mesh. A 413 (simplified-copy offer) is only returned when that copy cannot be built.
    """
    meta = _edit(bid, actor)
    m = editproj.mesh_at(bid, meta)
    real_n = int(len(m.faces))
    view, simplified = _display_mesh(m)
    if view is None:
        raise _too_big(real_n)
    try:
        parts = cadops.bodies(view)
    except Exception:
        if not simplified:
            raise
        parts = []
    if not parts and (simplified or real_n > MAX_SCENE_FACES):
        raise _too_big(real_n)
    out, shown = [], 0
    for i, b in enumerate(parts):
        packed, nfaces = _scene_body(i, b)
        shown += nfaces
        out.append(packed)
    if simplified and shown > MAX_SCENE_FACES:
        raise _too_big(real_n)
    p = editproj.payload(bid)
    return {"id": bid, "title": meta.get("title"), "bodies": out,
            "appearance": cadops.appearance_for_viewer(meta.get("appearance") or {}, m),
            "ops": p["ops"], "head": p["head"], "can_undo": p["can_undo"], "can_redo": p["can_redo"],
            "analysis": p["analysis"], "base": {k: v for k, v in (meta.get("base") or {}).items() if k in ("type", "format", "units", "photo_mode")},
            "downloads": {e: f"/api/download/{bid}/{e}" for e in ("stl", "3mf", "obj")},
            "display_simplified": simplified, "triangles": real_n, "display_triangles": shown}
