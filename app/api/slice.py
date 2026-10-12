"""POST /api/slice  (upload an STL or give a model id)  ->  G-code + print time + filament grams."""
from __future__ import annotations

import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import config
from app.community.identity import Actor, get_actor
from app.services import slice_engine as eng

router = APIRouter(prefix="/api/slice", tags=["slice"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
KEEP_SECONDS = 24 * 3600
_MODEL_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SLICE_ID = re.compile(r"^[0-9a-f]{32}$")
_slots = threading.BoundedSemaphore(int(os.environ.get("PHOTO3D_SLICE_CONCURRENCY", "2")))


def _fail(status: int, code: str, message: str):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


def slices_root() -> Path:
    # Under DATA, NOT the builds folder: build clean-up sweeps OUT sub-folders.
    return config.DATA / "slices"


def resolve_model(model_id: str, actor: Actor) -> Path:
    """STL of an existing build the actor OWNS (store.dir(<id>)/model.stl, same as /files/<id>/model.stl).

    Owner-only, like POST /api/slice/{bid} and /api/print/{bid}/links: other people's builds (even public ones) are 404.
    """
    from app.api.builds import meta_for
    from app.services import editproj
    from app.services.history import store
    if not _MODEL_ID.match(model_id) or not model_id.isalnum():
        _fail(400, "bad_model_id", "That model id isn't valid.")
    try:
        meta_for(model_id, actor, owner_only=True)
    except HTTPException:
        _fail(404, "model_not_found", "We couldn't find that model. It may have expired. Please rebuild it.")
    editproj.ensure_exports(model_id)  # edit-workspace builds write model.stl lazily
    stl = store.dir(model_id) / "model.stl"
    if not stl.is_file():
        _fail(404, "model_not_found", "That build has no STL file to slice.")
    return stl


def _prune(root: Path) -> None:
    if not root.is_dir():
        return
    cutoff = time.time() - KEEP_SECONDS
    for d in root.iterdir():
        try:
            if d.is_dir() and _SLICE_ID.match(d.name) and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


@router.get("/profiles")
def list_profiles():
    return {"default": eng.DEFAULT_PROFILE, "profiles": [p.public() for p in eng.PROFILES.values()]}


@router.post("")
def slice_model(
    file: Optional[UploadFile] = File(None),
    model_id: Optional[str] = Form(None),
    profile: str = Form(eng.DEFAULT_PROFILE),
    actor: Actor = Depends(get_actor),
):
    if bool(file) == bool(model_id):
        _fail(400, "bad_request", "Send either an STL file or a model id (not both, not neither).")
    try:
        prof = eng.get_profile(profile)
    except eng.SliceError as e:
        _fail(e.status, e.code, e.message)

    root = slices_root()
    _prune(root)
    slice_id = uuid.uuid4().hex
    work = root / slice_id
    work.mkdir(parents=True, exist_ok=True)

    if not _slots.acquire(blocking=False):
        shutil.rmtree(work, ignore_errors=True)
        _fail(503, "busy", "The slicer is busy right now. Please try again in a minute.")
    try:
        if file is not None:
            if not (file.filename or "").lower().endswith(".stl"):
                _fail(400, "bad_model", "Please upload an .stl file.")
            stl = work / "input.stl"
            written = 0
            with open(stl, "wb") as out:
                while chunk := file.file.read(1024 * 1024):
                    written += len(chunk)
                    if written > MAX_UPLOAD_BYTES:
                        _fail(413, "too_large", "That file is over the 50 MB limit.")
                    out.write(chunk)
        else:
            stl = resolve_model(model_id, actor)  # type: ignore[arg-type]

        res = eng.slice_stl(stl, prof, work / "model.gcode")
    except eng.SliceError as e:
        shutil.rmtree(work, ignore_errors=True)
        _fail(e.status, e.code, e.message)
    except HTTPException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    finally:
        _slots.release()
        if file is not None:
            (work / "input.stl").unlink(missing_ok=True)

    return {
        "slice_id": slice_id,
        "profile": prof.id,
        "gcode_url": f"/api/slice/{slice_id}/gcode",
        "print_time_seconds": res.print_time_seconds,
        "print_time_human": eng.humanize(res.print_time_seconds),
        "filament_grams": res.filament_grams,
        "model_size_mm": [round(v, 2) for v in res.size_mm],
    }


@router.get("/{slice_id}/gcode")
def download_gcode(slice_id: str):
    # The id is an unguessable uuid4 (acts as a capability); format-checked against path tricks.
    if not _SLICE_ID.match(slice_id):
        _fail(404, "not_found", "G-code not found.")
    path = slices_root() / slice_id / "model.gcode"
    if not path.is_file():
        _fail(404, "not_found", "That G-code has expired. Please slice again.")
    return FileResponse(path, media_type="text/plain", filename="model.gcode")
