"""Edit workspace API: upload STL/OBJ/3MF (or a photo, or a ZEIM build) → non-destructive edit → export / slice / print."""
from __future__ import annotations

import numpy as np
import trimesh
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ..community import privacy, safety
from ..community.identity import Actor, get_actor
from ..config import MAX_BUILDS
from ..core import autotune, exporters, geometry, imagesafe, meshedit
from ..services import editproj
from ..services.history import HistoryFull, store
from .builds import _safe_title, load_model, meta_for, summary
from .textcap import text_in

router = APIRouter(prefix="/api/edit")


def _edit_meta(bid: str, actor: Actor, owner_only=False) -> dict:
    meta = meta_for(bid, actor, owner_only=owner_only)
    if meta.get("kind") != "edit":
        raise HTTPException(404, "not an edit project")
    return meta


@router.get("/capabilities")
def capabilities():
    return editproj.capabilities()


def _full(actor):
    return JSONResponse(status_code=409, content={
        "code": "history_full", "max": MAX_BUILDS,
        "message": f"Build history is full ({MAX_BUILDS}/{MAX_BUILDS}). Delete a build or auto-delete the oldest to continue.",
        "builds": [summary(m) for m in store.list(actor.sid)]})


@router.post("/new")
def new_project(
    actor: Actor = Depends(get_actor),
    file: UploadFile | None = File(None),
    from_build: str = Form(""),
    title: str = Form(""),
    units: str = Form("mm"),
    beginner: bool = Form(True),
    auto_delete_oldest: bool = Form(False),
    photo_mode: str = Form("lithophane"),
    width_mm: float = Form(100.0),
):
    """Start an edit project from an uploaded mesh, an uploaded photo (lithophane/relief base) or an existing build."""
    try:
        title = text_in(title, 80, "Title")
        if title:
            safety.filter_only(title, "Title")
    except ValueError as e:
        raise HTTPException(400, str(e))
    if units not in meshedit.UNIT_MM:
        raise HTTPException(400, f"units must be one of {list(meshedit.UNIT_MM)}")
    warnings: list[str] = []
    source_image = None
    scale, base = 1.0, {}
    if from_build:                                              # ---- bring a ZEIM build into the editor
        meta = meta_for(from_build, actor, owner_only=True)
        if meta.get("kind") == "edit":
            editproj.ensure_exports(from_build)
        v, f = load_model(from_build).solid()
        mesh = trimesh.Trimesh(v, f, process=False)
        original, ext = exporters.to_stl(load_model(from_build)), "stl"
        base = {"type": "build", "from_build": from_build, "from_mode": meta.get("mode")}
        title = title or meta["title"]
        warnings.append("Colours / separate colour bodies of the original build are merged into one mesh in the editor.")
    elif file is not None and file.filename:                    # ---- upload
        name = file.filename
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        limit = editproj.MAX_UPLOAD_EDIT
        data = file.file.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(413, f"File too large (max {limit // 2**20} MB).")
        if not data:
            raise HTTPException(400, "The file is empty.")
        if ext in meshedit.ALLOWED:
            bad = meshedit.sniff(data, ext)
            if bad:
                raise HTTPException(415, bad)
            try:
                mesh, w = meshedit.load_mesh(data, ext)
            except meshedit.OpError as e:
                raise HTTPException(422, str(e))
            warnings += w
            original = data
            if ext != "3mf":
                scale = meshedit.UNIT_MM[units]
            base = {"type": "upload", "filename": name[:120], "format": ext, "units": units if ext != "3mf" else "from file"}
        elif ext in meshedit.IMAGE_EXT:                         # photo / lithophane base
            if len(data) > 25 * 2**20:
                raise HTTPException(413, "Photo too large (max 25 MB).")
            if photo_mode not in ("lithophane", "relief"):
                raise HTTPException(400, "photo_mode must be lithophane | relief")
            if not (20 <= width_mm <= 500):
                raise HTTPException(400, "width_mm must be 20..500")
            try:
                data, src_ext, _ = imagesafe.sanitize(data)
                im = geometry.load_image(data)
            except imagesafe.ImageRefused as e:
                raise HTTPException(415, str(e))
            except Exception:
                raise HTTPException(415, imagesafe.UNREADABLE)
            params, _ = autotune.autotune(im, photo_mode, width_mm, "standard")
            params["resolution"] = min(params.get("resolution", 200), 220)
            mdl = geometry.build(im, photo_mode, params)
            v, f = mdl.solid()
            mesh = trimesh.Trimesh(v, f, process=False)
            original, ext_o = exporters.to_stl(mdl), "stl"
            source_image = (data, src_ext)
            base = {"type": "photo", "photo_mode": photo_mode, "width_mm": width_mm, "filename": name[:120], "params": params}
            ext = ext_o
            warnings.append(f"Photo converted to a {photo_mode} base mesh; edit it like any other model.")
        else:
            raise HTTPException(415, "Unsupported file type. Upload .stl, .obj or .3mf (or a .png/.jpg photo).")
        title = title or _safe_title(name.rsplit(".", 1)[0][:80])
    else:
        raise HTTPException(400, "Choose a file to upload or a build to edit.")

    with store.lock:
        try:
            store.reserve(actor.sid, auto_delete_oldest)
        except HistoryFull:
            return _full(actor)
        try:
            meta = editproj.create(actor.sid, privacy.default_level(actor), title=title.strip(), base=base,
                                   original=original, original_ext=ext, mesh=mesh, beginner=beginner,
                                   warnings=warnings, import_scale=scale, import_units=units, source_image=source_image)
        except meshedit.OpError as e:
            raise HTTPException(422, str(e))
    return {**editproj.payload(meta["id"]), "history": [summary(m) for m in store.list(actor.sid)]}


@router.get("/{bid}")
def get_project(bid: str, actor: Actor = Depends(get_actor)):
    _edit_meta(bid, actor)
    return editproj.payload(bid)


def _act(bid, actor, fn):
    _edit_meta(bid, actor, owner_only=True)
    try:
        rep = fn()
    except meshedit.OpError as e:
        raise HTTPException(422, str(e))
    except safety.ChatBlocked as e:
        return JSONResponse(status_code=e.status, content=e.payload)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return editproj.payload(bid, rep)


@router.post("/{bid}/op")
def apply_op(bid: str, body: dict, actor: Actor = Depends(get_actor)):
    op = body.get("op")
    if op not in meshedit.OPS:
        raise HTTPException(400, f"unknown operation; choose from {sorted(meshedit.OPS)}")
    params = body.get("params") or {}
    if not isinstance(params, dict):
        raise HTTPException(400, "params must be an object")
    return _act(bid, actor, lambda: editproj.add_op(bid, op, params))


@router.post("/{bid}/undo")
def undo(bid: str, actor: Actor = Depends(get_actor)):
    return _act(bid, actor, lambda: editproj.undo(bid))


@router.post("/{bid}/redo")
def redo(bid: str, actor: Actor = Depends(get_actor)):
    return _act(bid, actor, lambda: editproj.redo(bid))


@router.post("/{bid}/goto")
def goto(bid: str, body: dict, actor: Actor = Depends(get_actor)):
    try:
        h = int(body.get("head"))
    except (TypeError, ValueError):
        raise HTTPException(400, "head must be an integer")
    return _act(bid, actor, lambda: editproj.goto(bid, h))


@router.get("/{bid}/original")
def original(bid: str, actor: Actor = Depends(get_actor)):
    """The upload exactly as received (never modified)."""
    _edit_meta(bid, actor)
    f = next(store.dir(bid).glob("original.*"), None)
    if not f:
        raise HTTPException(404)
    return FileResponse(f, filename=f"original_{bid}{f.suffix}", headers={"Cache-Control": "no-store"})
