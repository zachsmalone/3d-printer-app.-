"""2D->3D tab: an AI figure or bust from one photo (engine: TripoSR worker, see workers/ai3d/README.md).

GET  /api/ai3d/status         engine state + what this account may do (cap / cooldown / plan)
POST /api/ai3d/jobs           photo + mode (figure|bust) -> job id (the engine can take minutes on a CPU)
GET  /api/ai3d/jobs/{id}      running | done (build summary + preview) | error
Results are ordinary ZEIM builds (mode 'ai3d', marked ai=True, always private) so the existing auto-repair,
export picker and file names ('Title - Printer - 0.2mm') apply. Warnings are returned, never block.
"""
from __future__ import annotations

import threading
import time
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image

from .. import config
from ..community import safety
from ..community.identity import Actor, get_actor
from ..config import MAX_UPLOAD
from ..core import ai3d_mesh, exporters, imagesafe
from ..services import ai3d, uploadgate
from ..services.history import HistoryFull, store
from .builds import disk_guard, mesh_stats, preview_payload, summary
from .textcap import text_in

router = APIRouter(prefix="/api/ai3d")
AI_LABEL = "AI-made"
ENGINE = {"name": "TripoSR", "by": "Stability AI and Tripo AI", "licence": "MIT (code and weights)",
          "links": ["https://github.com/VAST-AI-Research/TripoSR/blob/main/LICENSE", "https://huggingface.co/stabilityai/TripoSR"]}


@router.get("/status")
def status(actor: Actor = Depends(get_actor)):
    return {"engine": {**ai3d.engine_status(), **ENGINE}, "plan": ai3d.plan(actor), "ai_label": AI_LABEL,
            "modes": {k: {"label": v["label"], "height_mm": v["height_mm"]} for k, v in ai3d_mesh.MODES.items()}}


def _refuse(p: dict):
    if p.get("reason") == "pro":
        raise HTTPException(403, {"code": "pro", "message": "2D to 3D is part of Pro."})
    if p.get("reason") == "cap":
        raise HTTPException(429, {"code": "cap", "message": f"That is today's {p['cap']} test models. More tomorrow.", **p})
    if p.get("reason") == "cooldown":
        raise HTTPException(429, {"code": "cooldown", "message": "A short pause between models.", **p})


@router.post("/jobs")
def start(actor: Actor = Depends(get_actor), file: UploadFile = File(...), mode: str = Form("figure"),
          photo_ack: bool = Form(False), title: str = Form(""), height_mm: float = Form(0),
          auto_delete_oldest: bool = Form(False)):
    if mode not in ai3d_mesh.MODES:
        raise HTTPException(400, "Pick Figure or Bust.")
    try:
        title = text_in(title, 80, "Title")
        if title:
            safety.filter_only(title, "Title")
    except ValueError as e:
        raise HTTPException(400, str(e))
    st = ai3d.engine_status()
    if not st["installed"]:
        raise HTTPException(503, {"code": "engine_missing", "message": "The 2D to 3D engine is not installed on this server yet."})
    _refuse(ai3d.plan(actor))
    if ai3d.busy(actor.sid):
        raise HTTPException(409, {"code": "busy", "message": "Your last photo is still being turned into a model."})
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "image too large (max 25 MB)")
    sample_title = imagesafe.builtin_title(data)
    try:
        checked = uploadgate.gate(data, actor.sid, source="generate")
    except uploadgate.GateError as e:
        raise HTTPException(e.status, e.message)
    if getattr(checked, "scan_state", "off") == "unscanned":
        raise HTTPException(503, "The upload check is not available right now. Please try again shortly.")
    try:
        ack = imagesafe.check_ack(data, photo_ack)
        clean, ext, _ = imagesafe.sanitize(data)          # EXIF/GPS dropped before the engine sees it
    except imagesafe.ImageRefused as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(400, imagesafe.UNREADABLE)
    with store.lock:                                       # check the history slot BEFORE the long run
        try:
            store.reserve(actor.sid, auto_delete_oldest)
        except HistoryFull:
            raise HTTPException(409, {"code": "history_full", "message": "Your history is full. Delete a build or allow replacing the oldest."})
    disk_guard()
    job = ai3d.new_job(actor.sid)
    args = (job, actor, clean, ext, mode, height_mm or None, title.strip() or (f"{sample_title} {ai3d_mesh.MODES[mode]['label']}" if sample_title else ""), ack, auto_delete_oldest)
    threading.Thread(target=_run, args=args, daemon=True).start()
    return {"job": job["id"], "state": "running"}


def _run(job, actor, clean, ext, mode, height_mm, title, ack, auto_delete_oldest):
    t0 = time.time()
    try:
        raw = ai3d_mesh.load(ai3d.engine_call(clean, mode))
        model, rep = ai3d_mesh.finish(raw, mode, height_mm)
        ai3d.mark_done(actor)                              # cooldown starts when the model is finished; tweaks never count
        job["result"] = _save(actor, model, rep, clean, ext, mode, title, ack, auto_delete_oldest, time.time() - t0)
        job["state"] = "done"
    except (ai3d.EngineMissing, ai3d.EngineError, ai3d_mesh.MeshError) as e:
        job["error"] = str(e); job["state"] = "error"
    except HistoryFull:
        job["error"] = "Your history is full. Delete a build or allow replacing the oldest."; job["state"] = "error"
    except Exception as e:
        job["error"] = f"Something went wrong while making the model ({type(e).__name__})."; job["state"] = "error"


def _save(actor, model, rep, clean, ext, mode, title, ack, auto_delete_oldest, seconds):
    from ..services import filestore, willprint
    with store.lock:
        store.reserve(actor.sid, auto_delete_oldest)
        bid = uuid.uuid4().hex[:12]
        d = store.dir(bid); d.mkdir(parents=True)
        src = "source." + ext
        (d / src).write_bytes(clean)
        for e, fn in exporters.WRITERS.items():
            (d / f"model.{e}").write_bytes(fn(model))
        Image.fromarray(model.thumb).save(d / "thumb.png")
        if filestore.enabled():
            filestore.put_build(bid, "source", clean)
            for e in exporters.WRITERS:
                filestore.put_build(bid, f"model.{e}", (d / f"model.{e}").read_bytes())
            filestore.put_build(bid, "thumb.png", (d / "thumb.png").read_bytes(), "image/png")
        stats = mesh_stats(model)
        model.info = {**model.info, "bed_fit": willprint.bed_fit(tuple(stats["size_mm"]), "creality_k1"), "ai3d": rep}
        label = ai3d_mesh.MODES[mode]["label"]
        notes = [{"label": "Made with", "value": AI_LABEL, "why": "TripoSR, an open AI model, guessed the hidden sides from one photo."}]
        notes += [{"label": "Repair", "value": "done", "why": n} for n in rep["notes"]]
        notes += [{"label": "Note", "value": "check", "why": w} for w in rep["warnings"]]
        meta = {"id": bid, "mode": "ai3d", "kind": "ai3d", "ai": True, "ai_label": AI_LABEL, "beginner": False, "preset": None,
                "title": title or f"My AI {label.lower()}", "source": src, "params": {"mode": mode, "height_mm": rep["height_mm"]},
                "auto_notes": notes, "info": model.info, "stats": stats, "owner_sid": actor.sid,
                "visibility": "private",                   # uploaded photos and what is made from them stay private
                "photo_ack": ack}
        store.save(meta)
        store.cache[bid] = model
    return {**summary(meta), "ai": True, "ai_label": AI_LABEL, "auto_notes": notes, "report": rep,
            "seconds": round(seconds, 1), "preview": preview_payload(model)}


@router.get("/jobs/{jid}")
def job(jid: str, actor: Actor = Depends(get_actor)):
    j = ai3d.JOBS.get(jid)
    if not j or j["sid"] != actor.sid:
        raise HTTPException(404, "not found")
    out = {"job": jid, "state": j["state"], "elapsed_s": round(time.time() - j["started"])}
    if j["state"] == "done":
        out["result"] = j["result"]; out["plan"] = ai3d.plan(actor)
    if j["state"] == "error":
        out["error"] = j["error"]
    return out
