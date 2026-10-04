"""Build creation, history and downloads."""
from __future__ import annotations

import base64
import time
import uuid

import numpy as np
import trimesh
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image

from ..community import privacy, safety
from .textcap import text_in
from ..community.identity import Actor, get_actor
from ..config import MAX_BUILDS, MAX_UPLOAD, PREVIEW_RES
from ..core import autotune, exporters, geometry, imagesafe
from ..services.history import HistoryFull, store

router = APIRouter(prefix="/api")


def mesh_stats(model: geometry.Model) -> dict:
    bodies, ok = [], True
    for b in model.bodies:
        t = trimesh.Trimesh(b.vertices, b.faces, process=False)
        wt = bool(t.is_watertight and t.is_winding_consistent and t.volume > 0)
        ok &= wt
        bodies.append({"name": b.name, "triangles": int(len(b.faces)), "watertight": wt,
                       "volume_mm3": round(float(t.volume), 2)})
    v, f = model.solid()
    if model.single is not None:
        ts = trimesh.Trimesh(v, f, process=False)
        ok &= bool(ts.is_watertight and ts.is_winding_consistent and ts.volume > 0)
    return {"bodies": bodies, "watertight": bool(ok),
            "size_mm": (v.max(0) - v.min(0)).round(2).tolist(),
            "triangles": int(sum(len(b.faces) for b in model.bodies))}


def preview_payload(model: geometry.Model) -> dict:
    return {"bodies": [{
        "name": b.name, "color": b.color,
        "positions": base64.b64encode(b.vertices.astype("<f4").tobytes()).decode(),
        "indices": base64.b64encode(b.faces.astype("<u4").tobytes()).decode(),
    } for b in model.bodies]}


def summary(meta: dict) -> dict:
    """Metadata for history cards (no heavy data)."""
    bid = meta["id"]
    return {**{k: meta[k] for k in ("id", "created", "mode", "beginner", "title", "stats")},
            "kind": meta.get("kind", "photo"), "visibility": meta.get("visibility", "private"),
            "thumb": f"/files/{bid}/thumb.png",
            "downloads": {e: f"/files/{bid}/model.{e}" for e in exporters.WRITERS}}


def load_model(bid: str) -> geometry.Model:
    """Model for a stored build (cached; rebuilt from source image + params after a restart)."""
    m = store.cache.get(bid)
    if m is None:
        meta = store.get(bid)
        if meta.get("kind") == "edit":
            from ..services import editproj
            m = store.cache[bid] = editproj.model(bid)
            return m
        im = geometry.load_image((store.dir(bid) / meta["source"]).read_bytes())
        m = geometry.build(im, meta["mode"], meta["params"])
        store.cache[bid] = m
    return m


def meta_for(bid: str, actor: Actor, owner_only: bool = False) -> dict:
    """Metadata of a build the actor may access; otherwise 404 (private builds look non-existent)."""
    try:
        meta = store.get(bid)
    except KeyError:
        raise HTTPException(404, "unknown build")
    if meta.get("owner_sid") == actor.sid:
        return meta
    if owner_only or not privacy.can_view(actor, meta.get("owner_sid"), meta.get("visibility", "private")):
        raise HTTPException(404, "unknown build")
    return meta


def _safe_title(derived: str) -> str:
    """A title made from the uploaded file's name: replaced by 'Untitled' if the name itself would not pass the language gate."""
    return derived if derived and not safety.scan(derived) else "Untitled"


@router.get("/builds")
def list_builds(actor: Actor = Depends(get_actor)):
    store.claim_unowned(actor.sid)
    return {"max": MAX_BUILDS, "builds": [summary(m) for m in store.list(actor.sid)]}


@router.put("/builds/{bid}/visibility")
def build_visibility(bid: str, body: dict, actor: Actor = Depends(get_actor)):
    """Owner only. Effective immediately (checked on every file / API request)."""
    meta = meta_for(bid, actor, owner_only=True)
    try:
        meta["visibility"] = privacy.check_level(actor, body.get("visibility", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    store.save(meta)
    return summary(meta)


@router.get("/builds/{bid}")
def get_build(bid: str, actor: Actor = Depends(get_actor)):
    meta = meta_for(bid, actor)
    if meta.get("kind") == "edit":
        from ..services import editproj
        return editproj.payload(bid)
    model = load_model(bid)
    prev = model
    if meta["params"].get("resolution", 0) > PREVIEW_RES:
        prev = geometry.build(geometry.load_image((store.dir(bid) / meta["source"]).read_bytes()),
                              meta["mode"], {**meta["params"], "resolution": PREVIEW_RES})
    return {**summary(meta), "params": meta["params"], "auto_notes": meta.get("auto_notes", []),
            "info": meta.get("info", {}), "preview": preview_payload(prev)}


@router.delete("/builds/{bid}")
def delete_build(bid: str, actor: Actor = Depends(get_actor)):
    meta_for(bid, actor, owner_only=True)
    store.delete(bid)
    return {"ok": True}


@router.post("/builds/delete-oldest")
def delete_oldest(actor: Actor = Depends(get_actor)):
    with store.lock:
        items = store.list(actor.sid)
        if not items:
            return {"ok": True, "deleted": None}
        store.delete(items[0]["id"])
        return {"ok": True, "deleted": items[0]["id"]}


@router.post("/generate")
def generate(
    actor: Actor = Depends(get_actor),
    file: UploadFile = File(...),
    mode: str = Form("lithophane"),
    beginner: bool = Form(False),
    preset: str = Form("standard"),          # beginner: thin | standard | thick
    auto_delete_oldest: bool = Form(False),  # confirm replacing oldest when history is full
    title: str = Form(""),
    width_mm: float = Form(100.0),
    resolution: int = Form(200),
    smooth: float = Form(0.8),
    gamma: float = Form(1.0),
    auto_contrast: bool = Form(True),
    invert: bool = Form(False),
    min_thickness: float = Form(0.8),
    max_thickness: float = Form(3.0),
    border_mm: float = Form(3.0),
    base_mm: float = Form(2.0),
    relief_mm: float = Form(6.0),
    levels: int = Form(4),
    layer_mm: float = Form(1.0),
    style: str = Form("posterize"),
    halftone_cell: float = Form(6.0),
    multi_body: bool = Form(True),
    palette: str = Form(""),
):
    if mode not in ("lithophane", "relief", "popart"):
        raise HTTPException(400, f"unknown mode {mode}")
    try:
        title = text_in(title, 80, "Title")
        if title:
            safety.filter_only(title, "Title")
    except ValueError as e:
        raise HTTPException(400, str(e))
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "image too large (max 25 MB)")
    try:
        data, src_ext, _ = imagesafe.sanitize(data)       # HEIC -> JPEG, rotation applied, EXIF/GPS dropped, extension from content
        im = geometry.load_image(data)
    except imagesafe.ImageRefused as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(400, imagesafe.UNREADABLE)
    if not (5 <= width_mm <= 1000):
        raise HTTPException(400, "width_mm must be 5..1000")

    with store.lock:  # serialise so concurrent builds can't exceed the cap
        try:
            store.reserve(actor.sid, auto_delete_oldest)
        except HistoryFull:
            return JSONResponse(status_code=409, content={
                "code": "history_full", "max": MAX_BUILDS,
                "message": f"Build history is full ({MAX_BUILDS}/{MAX_BUILDS}). Delete a build or "
                           "auto-delete the oldest to continue.",
                "builds": [summary(m) for m in store.list(actor.sid)]})
        auto_notes = []
        if beginner:
            params, auto_notes = autotune.autotune(im, mode, width_mm, preset)
        else:
            params = dict(width_mm=width_mm, resolution=int(np.clip(resolution, 16, geometry.MAX_RES)),
                          smooth=smooth, gamma=gamma, auto_contrast=auto_contrast, invert=invert)
            params.update({
                "lithophane": dict(min_thickness=min_thickness, max_thickness=max_thickness, border_mm=border_mm),
                "relief": dict(base_mm=base_mm, relief_mm=relief_mm),
                "popart": dict(base_mm=base_mm, levels=levels, layer_mm=layer_mm, style=style,
                               halftone_cell=halftone_cell, multi_body=multi_body, palette=palette or None),
            }[mode])
        t0 = time.time()
        try:
            model = geometry.build(im, mode, params)
            prev = model
            if params["resolution"] > PREVIEW_RES:
                prev = geometry.build(im, mode, {**params, "resolution": PREVIEW_RES})
        except ValueError as e:
            raise HTTPException(400, str(e))
        bid = uuid.uuid4().hex[:12]
        d = store.dir(bid)
        d.mkdir(parents=True)
        src = "source." + src_ext
        (d / src).write_bytes(data)
        for ext, fn in exporters.WRITERS.items():
            (d / f"model.{ext}").write_bytes(fn(model))
        Image.fromarray(model.thumb).save(d / "thumb.png")
        stats = mesh_stats(model)
        meta = {"id": bid, "mode": mode, "beginner": beginner, "preset": preset if beginner else None,
                "title": title.strip() or _safe_title((file.filename or "Untitled").rsplit(".", 1)[0][:40]),
                "source": src, "params": params, "auto_notes": auto_notes, "info": model.info,
                "stats": stats, "owner_sid": actor.sid, "visibility": privacy.default_level(actor)}
        store.save(meta)
        store.cache[bid] = model
    return {**summary(meta), "params": params, "auto_notes": auto_notes, "info": model.info,
            "seconds": round(time.time() - t0, 2), "preview": preview_payload(prev),
            "history": [summary(m) for m in store.list(actor.sid)]}


@router.get("/download/{bid}/{ext}")
def download(bid: str, ext: str, actor: Actor = Depends(get_actor)):
    if ext not in exporters.WRITERS or not bid.isalnum():
        raise HTTPException(404)
    meta_for(bid, actor)
    from ..services import editproj
    editproj.ensure_exports(bid)
    p = store.dir(bid) / f"model.{ext}"
    if not p.exists():
        raise HTTPException(404, "unknown build")
    return FileResponse(p, filename=f"photo3d_{bid}.{ext}")
