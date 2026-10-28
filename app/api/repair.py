"""POST /api/repair: upload a broken STL / 3MF / OBJ, get a before/after report and the fixed file in the same format.
POST /api/repair/{id}/slicer opens that repaired file as an FDM Slicer project on the server.
No account (the anonymous cookie session is enough), no paywall. Same 500 MB limit and upload gate as the editor;
the repair itself runs in core/guard.py's memory-capped child, so a huge file is refused cleanly, never a 500."""
from __future__ import annotations

import json
import re
import threading
import time
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import config
from ..community import privacy
from ..community.identity import Actor, get_actor
from ..core import guard, imagesafe, meshedit, stlrepair
from ..services import editproj
from ..services.history import HistoryFull, store
from .builds import disk_guard, full_response

router = APIRouter(prefix="/api/repair")
KEEP_S = 3600                                       # fixed files are kept for an hour, then deleted
_EDIT_ID = re.compile(r"[0-9a-f]{12}")
_GONE = "That repaired file has expired. Repair it again."
_RID_GUARD = threading.Lock()
_RID_LOCKS: dict[str, threading.Lock] = {}


def _dir():
    d = config.DATA / "repair"; d.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for f in d.iterdir():                           # cheap housekeeping on every request
        try:
            if now - f.stat().st_mtime > KEEP_S:
                f.unlink()
        except OSError:
            pass
    return d


@router.post("")
def repair(file: UploadFile | None = File(None), actor: Actor = Depends(get_actor)):
    if file is None or not file.filename:
        raise HTTPException(400, "Choose an STL, 3MF or OBJ file to repair.")
    name = file.filename
    limit = editproj.MAX_UPLOAD_EDIT
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File too large (max {limit // 2**20} MB).")
    if not data:
        raise HTTPException(400, "The file is empty.")
    ext = meshedit.guess_model_ext(name, data, getattr(file, "content_type", "") or "")
    if ext not in meshedit.ALLOWED:
        raise HTTPException(415, "Unsupported file type. Repair takes .stl, .3mf or .obj files.")
    bad = meshedit.sniff(data, ext)
    if bad:
        raise HTTPException(415, bad)
    from ..services import uploadgate
    try:
        uploadgate.gate(data, actor.sid, source="edit", max_bytes=limit)
    except uploadgate.GateError as e:
        raise HTTPException(e.status, e.message)
    try:
        blob, rep = guard.run(stlrepair.repair_bytes, data, ext, timeout=180)
    except meshedit.OpError as e:
        raise HTTPException(422, str(e))
    except guard.Busy:
        raise HTTPException(503, "The repair service is busy. Try again in a minute.")
    except guard.Tripped:
        raise HTTPException(422, "This file needs more memory or time than one repair may use. "
                                 "Try simplifying it first, or split it into parts.")
    except Exception:
        raise HTTPException(422, "We couldn't read or repair that file. Check that it's a complete STL, 3MF or OBJ.")
    rid = uuid.uuid4().hex[:16]
    d = _dir()
    (d / f"{rid}.{ext}").write_bytes(blob)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", name.rsplit(".", 1)[0])[:40].strip("_") or "model"
    (d / f"{rid}.json").write_text(json.dumps({"sid": actor.sid, "ext": ext, "name": f"{stem}_repaired.{ext}"}))
    return {**rep, "id": rid, "download_url": f"/api/repair/{rid}", "filename": f"{stem}_repaired.{ext}", "bytes": len(blob)}


@router.get("/{rid}")
def download(rid: str, actor: Actor = Depends(get_actor)):
    if not re.fullmatch(r"[0-9a-f]{16}", rid):
        raise HTTPException(404)
    d = config.DATA / "repair"
    try:
        meta = json.loads((d / f"{rid}.json").read_text())
    except (OSError, ValueError):
        raise HTTPException(404, "That repaired file has expired. Repair it again.")
    f = d / f"{rid}.{meta['ext']}"
    if meta.get("sid") != actor.sid or not f.is_file():
        raise HTTPException(404, "That repaired file has expired. Repair it again.")
    mt = {"stl": "model/stl", "3mf": "model/3mf", "obj": "model/obj"}[meta["ext"]]
    return FileResponse(f, media_type=mt, filename=meta["name"], headers={"Cache-Control": "no-store"})


def _rid_lock(rid: str) -> threading.Lock:
    with _RID_GUARD:
        lock = _RID_LOCKS.get(rid)
        if lock is None:
            lock = threading.Lock()
            _RID_LOCKS[rid] = lock
        return lock


def _repair_record(rid: str, actor: Actor):
    """The repaired bytes for this session, or 404. The id is not a guessable path."""
    if not re.fullmatch(r"[0-9a-f]{16}", rid):
        raise HTTPException(404, _GONE)
    d = config.DATA / "repair"
    meta_path = d / f"{rid}.json"
    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, ValueError):
        raise HTTPException(404, _GONE)
    ext = meta.get("ext")
    blob = d / f"{rid}.{ext}" if ext in meshedit.ALLOWED else None
    if meta.get("sid") != actor.sid or blob is None or not blob.is_file():
        raise HTTPException(404, _GONE)
    return meta, meta_path, blob


def _owned_from_repair(bid: str, actor: Actor, rid: str) -> dict | None:
    """An edit project this person owns that was made from this repair. Anything else is left alone."""
    if not _EDIT_ID.fullmatch(bid or ""):
        return None
    try:
        meta = store.get(bid)
    except KeyError:
        return None
    base = meta.get("base") or {}
    if meta.get("owner_sid") != actor.sid or meta.get("kind") != "edit":
        return None
    if base.get("type") != "repair" or base.get("from_repair") != rid:
        return None
    return meta


def _stamp(meta_path, meta: dict, edit_id: str) -> dict:
    meta = {**meta, "edit_id": edit_id}
    meta_path.write_text(json.dumps(meta))
    return meta


def _handoff(edit_id: str, *, created: bool, reused: bool, requested: str) -> dict:
    return {
        "id": edit_id,
        "created": created,
        "reused": reused,
        "same": bool(requested) and requested == edit_id,
        "url": f"/?edit={edit_id}#slicer",
    }


@router.post("/{rid}/slicer")
def open_in_slicer(rid: str, actor: Actor = Depends(get_actor), edit: str = Form(""), beginner: bool = Form(True)):
    """Open the repaired mesh in the FDM Slicer without the browser uploading the file again.

    One project per repair. If this repair already has a project, that id is returned.
    `edit` is used only when it is that project. A different saved project is not changed.
    """
    if not re.fullmatch(r"[0-9a-f]{16}", rid):
        raise HTTPException(404, _GONE)
    requested = edit if _EDIT_ID.fullmatch(edit or "") else ""
    with _rid_lock(rid):
        meta, meta_path, blob_path = _repair_record(rid, actor)
        current = _owned_from_repair(str(meta.get("edit_id") or ""), actor, rid)
        if current is None and requested:
            adopted = _owned_from_repair(requested, actor, rid)
            if adopted is not None:
                current = adopted
                meta = _stamp(meta_path, meta, current["id"])
        if current is not None:
            return _handoff(current["id"], created=False, reused=True, requested=requested)
        blob = blob_path.read_bytes()
        if not blob:
            raise HTTPException(404, _GONE)
        try:
            mesh, warnings = meshedit.load_mesh(blob, meta["ext"], units_scale=1.0)
        except meshedit.OpError as e:
            raise HTTPException(422, str(e))
        title = imagesafe.builtin_title(blob) or "Repaired model"
        base = {"type": "repair", "from_repair": rid, "format": meta["ext"], "units": "mm"}
        disk_guard()
        with store.lock:
            try:
                fresh = json.loads(meta_path.read_text())
            except (OSError, ValueError):
                raise HTTPException(404, _GONE)
            current = _owned_from_repair(str(fresh.get("edit_id") or ""), actor, rid)
            if current is not None:
                return _handoff(current["id"], created=False, reused=True, requested=requested)
            try:
                store.reserve(actor.sid, False)
            except HistoryFull:
                return full_response(actor)
            try:
                made = editproj.create(
                    actor.sid, privacy.default_level(actor), title=title, base=base,
                    original=blob, original_ext=meta["ext"], mesh=mesh, beginner=bool(beginner),
                    warnings=list(warnings), import_scale=1.0, import_units="mm",
                )
            except meshedit.OpError as e:
                raise HTTPException(422, str(e))
            _stamp(meta_path, fresh, made["id"])
        return _handoff(made["id"], created=True, reused=False, requested=requested)
