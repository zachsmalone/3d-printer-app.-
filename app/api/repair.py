"""POST /api/repair: upload a broken STL / 3MF / OBJ, get a before/after report and the fixed file in the same format.
No account (the anonymous cookie session is enough), no paywall. Same 500 MB limit and upload gate as the editor;
the repair itself runs in core/guard.py's memory-capped child, so a huge file is refused cleanly, never a 500."""
from __future__ import annotations

import json
import re
import time
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import config
from ..community.identity import Actor, get_actor
from ..core import guard, meshedit, stlrepair
from ..services import editproj

router = APIRouter(prefix="/api/repair")
KEEP_S = 3600                                       # fixed files are kept for an hour, then deleted


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
