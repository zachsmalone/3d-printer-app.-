"""Print hand-off: slicer deep links, built-in slice, network printer send."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from .. import config
from ..services import handoff, printers, settings, slicer
from ..services.history import store
from ..community import badges, privacy
from ..community.identity import Actor, get_actor
from . import guards
from .builds import load_model, meta_for

router = APIRouter(prefix="/api")
files_router = APIRouter()


base_url = settings.base_url


FILE_NAMES = ("model.stl", "model.obj", "model.3mf", "thumb.png", "model.gcode")


def _send_file(bid: str, name: str):
    from ..services import editproj, quarantine
    if name not in FILE_NAMES or not bid.isalnum():
        raise HTTPException(404)
    quarantine.guard(bid)                        # quarantined builds are not served
    if name.startswith("model.") and name != "model.gcode":
        editproj.ensure_exports(bid)
    p = store.dir(bid) / name
    if not p.exists():
        raise HTTPException(404)
    ext = name.rsplit(".", 1)[-1].lower()
    media = {"stl": "model/stl", "obj": "model/obj", "3mf": "model/3mf", "gcode": "text/plain; charset=utf-8", "png": "image/png"}.get(ext)
    fname = None if name == "thumb.png" else f"photo3d_{bid}.{ext}"
    return FileResponse(p, media_type=media, filename=fname, headers={"Cache-Control": "no-store"})


@files_router.get("/files/{bid}/{name}")
def serve_file(bid: str, name: str, actor: Actor = Depends(get_actor)):
    """Stable, extension-terminated URLs. Needs access (owner / visibility) - private builds are 404 to others."""
    meta = meta_for(bid, actor)
    resp = _send_file(bid, name)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if actor.user and meta.get("owner_sid") == actor.sid and ext in badges.EXPORT_EXTS:
        badges.stamp(resp, actor, "export")
    return resp


@files_router.get("/f/{token}/{bid}/{name}")
def serve_file_token(token: str, bid: str, name: str):
    """Signed, short-lived (10 min) link used by slicer deep links so a PRIVATE build can be opened by the owner's
    slicer (which has no browser cookie). The token is bound to ONE build and ONE file name; useless for anything else."""
    if not privacy.check_token(bid, name, token):
        raise HTTPException(404)
    return _send_file(bid, name)


@router.get("/print/{bid}/links")
def print_links(bid: str, request: Request, actor: Actor = Depends(get_actor)):
    guards.require_links(request, actor)
    meta_for(bid, actor, owner_only=True)
    s = settings.load()
    # Shared server with no configured public address: the request's Host header is attacker-controlled and would end up
    # inside signed links, so no slicer deep links are offered until an admin sets the public base URL.
    no_base = config.MODE == "shared" and not (config.PUBLIC_BASE_URL or s.get("public_base_url"))
    user_pr = (actor.user.get("printer") or {}).get("printer_id") if actor.user else None
    return {"base_url": settings.trusted_base_url(request) or "", "default_slicer": s["default_slicer"], "effective_slicer": settings.effective_slicer(s, user_printer=user_pr),
            "slicers": [] if no_base else handoff.links(base_url(request), bid, lambda n: privacy.make_token(bid, n)),
            "slicer_links_disabled": ("Slicer links are off until the site's public address is set in Settings. You can still download the file." if no_base else ""),
            "printers": settings.public(s, redact=not guards.can_see_printer_urls(request, actor))["printers"], "printer_types": printers.TYPES,
            "printer_verification": printers.verification_tag(),
            "printer_honesty": printers.honesty_note(bool(s.get("printers"))),
            "direct_control": printers.direct_control_enabled(),
            "bambu_limits": printers.bambu_limits(),
            "builtin_slicer": slicer.status(),
            "hint": "Deep links need the slicer installed on the SAME computer as your browser, and the "
                    "file URL must be reachable from it (set 'Public base URL' in Settings if the server "
                    "is remote). Links are signed, work for one file only, and expire after 10 minutes, so a private build stays private."}


def _slice(bid, layer_height, fill_density, upright, supports, brim, bed, profile_ini=None, **chosen):
    from ..services import slicestats
    t0 = time.time()
    st = slicer.status()
    if not st["available"]:
        slicestats.record(False, "slicer unavailable")
        return st
    try:
        out = _slice_inner(bid, layer_height, fill_density, upright, supports, brim, bed, profile_ini, **chosen)
    except Exception as e:
        slicestats.record(False, str(e))
        raise
    slicestats.record(True)
    return out


def _slice_inner(bid, layer_height, fill_density, upright, supports, brim, bed, profile_ini=None, **chosen):
    st = slicer.status()
    if not st["available"]:
        return st
    try:
        model = load_model(bid)
    except KeyError:
        raise HTTPException(404, "unknown build")
    if chosen.get("printer_id") or chosen.get("opts"):
        return slicer.slice_model(model, store.dir(bid), layer_height, fill_density, upright, supports,
                                  brim, bed, profile_ini, **chosen)
    return slicer.slice_model(model, store.dir(bid), layer_height, fill_density, upright, supports,
                              brim, bed, profile_ini)


@router.post("/slice/{bid}")
def slice_build(bid: str, actor: Actor = Depends(get_actor), layer_height: float = Form(0.2), fill_density: int = Form(15),
                upright: bool = Form(False), supports: bool = Form(False), brim: float = Form(0.0), printer_id: str = Form(""),
                catalog_printer: str = Form(""), nozzle: str = Form("")):
    meta_for(bid, actor, owner_only=True)
    pr = settings.get_printer(printer_id) if printer_id else None      # same bed/profile the "Send" of that printer will use
    user_pr = (actor.user.get("printer") or {}) if actor.user else {}
    if not catalog_printer and not printer_id and user_pr.get("printer_id"):
        catalog_printer = user_pr["printer_id"]
        if not nozzle and user_pr.get("nozzle") is not None:
            nozzle = str(user_pr["nozzle"])
    chosen = {"printer_id": catalog_printer, "nozzle": nozzle} if catalog_printer else {}
    res = _slice(bid, layer_height, fill_density, upright, supports, brim, printers.bed_of(pr), printers.ini_of(pr), **chosen)
    if pr:
        res["bed"] = list(printers.bed_of(pr))
    elif catalog_printer:
        from app.services import print_setup as ps
        try:
            bx, by, _ = ps.bed_of(catalog_printer)
            res["bed"] = [bx, by]
        except Exception:
            res["bed"] = list(printers.bed_of(None))
    else:
        res["bed"] = list(printers.bed_of(None))
    if res.get("ok"):
        res["download"] = f"/files/{bid}/model.gcode"
        events = ["fdm_slice"]
        if supports:
            events.append("supports_slice")
        res = badges.merge(res, actor, *events)
    return JSONResponse(res)  # unavailable slicer -> 200 with available=false


@router.post("/send/{bid}")
def send_to_printer(bid: str, request: Request, actor: Actor = Depends(get_actor), printer_id: str = Form(...), start: bool = Form(False),
                    layer_height: float = Form(0.2), fill_density: int = Form(15),
                    upright: bool = Form(False), supports: bool = Form(False), brim: float = Form(0.0)):
    guards.require_send(request, actor)
    meta_for(bid, actor, owner_only=True)
    if not printers.direct_control_enabled():
        raise HTTPException(410, printers.DIRECT_OFF_MESSAGE)
    from ..services import quarantine
    quarantine.guard(bid)                        # quarantined builds are not printed either
    pr = settings.get_printer(printer_id)
    if not pr:
        raise HTTPException(404, "unknown printer")
    if pr["type"] not in printers.IMPLEMENTED:
        return JSONResponse(printers.send(pr, None, "", start))  # clear stub message
    res = _slice(bid, layer_height, fill_density, upright, supports, brim, printers.bed_of(pr), printers.ini_of(pr))
    if not res.get("ok"):
        return JSONResponse({"ok": False, "stage": "slice", **res})
    filament_g = None
    try:
        filament_g = (res.get("stats") or {}).get("filament_g")
    except Exception:
        pass
    spool = printers.spool_check(pr, filament_g)
    if spool.get("checked") and not spool.get("ok"):
        return JSONResponse({"ok": False, "stage": "spool", "spool": spool, "slice": res,
                             "message": spool.get("message"),
                             "verification": printers.verification_tag(pr.get("type"))})
    out = printers.send(pr, store.dir(bid) / "model.gcode", f"photo3d_{bid}.gcode", start)
    return JSONResponse({**out, "stage": "upload", "slice": res, "spool": spool})


@router.post("/printers/{printer_id}/test")
def test_printer(printer_id: str, request: Request, actor: Actor = Depends(get_actor)):
    """Connection test: read-only GET requests to the printer, NEVER a print or upload command. Same guard as /api/send, plus on a
    shared server only the owner/admin (the server connects to whatever address was saved: keep that to the person who saved it)."""
    guards.require_send(request, actor)
    if not printers.direct_control_enabled():
        raise HTTPException(410, printers.DIRECT_OFF_MESSAGE)
    if not guards.can_manage_printers(request, actor):
        raise HTTPException(403, "Only the person who manages this server can test printers.")
    pr = settings.get_printer(printer_id)
    if not pr:
        raise HTTPException(404, "unknown printer")
    return JSONResponse(printers.test(pr))


# ---- SEND-0: tiny sample files for the hidden /sharetest page (adults only; nothing from any user's data)
@router.get("/sharetest/file.{fmt}")
def sharetest_file(fmt: str, request: Request, actor: Actor = Depends(get_actor)):
    import io
    import trimesh
    from fastapi.responses import Response
    if not guards.send_caps(request, actor)["share"]:
        raise HTTPException(403, "The share test page is for adult accounts.")
    if fmt not in ("stl", "obj", "3mf"):
        raise HTTPException(404)
    data = trimesh.creation.box(extents=(20, 20, 20)).export(file_type={"stl": "stl", "obj": "obj", "3mf": "3mf"}[fmt])
    data = data.encode() if isinstance(data, str) else data
    return Response(data, media_type="application/octet-stream", headers={"Cache-Control": "no-store"})


# ---- Print-send10 upgrades (status, control, camera, board, alerts, queue, timelapse) ----

from fastapi.responses import Response

from ..services import print_queue, print_watch


def _require_printer(printer_id: str, request: Request, actor: Actor) -> dict:
    guards.require_send(request, actor)
    if not printers.direct_control_enabled():
        raise HTTPException(410, printers.DIRECT_OFF_MESSAGE)
    if not guards.can_manage_printers(request, actor):
        raise HTTPException(403, "Only the person who manages this server can control printers.")
    pr = settings.get_printer(printer_id)
    if not pr:
        raise HTTPException(404, "unknown printer")
    return pr


@router.get("/bambu/limits")
def get_bambu_limits():
    """Documented Bambu LAN / Developer Mode limits (no secrets)."""
    return printers.bambu_limits()


@router.get("/printers/board")
def printers_board(request: Request, actor: Actor = Depends(get_actor)):
    """Multi-printer status board (feature 8). Also runs opt-in alert/failure-watch side effects."""
    guards.require_send(request, actor)
    if not printers.direct_control_enabled():
        raise HTTPException(410, printers.DIRECT_OFF_MESSAGE)
    return JSONResponse(print_watch.board())


@router.get("/printers/alerts")
def printers_alerts(request: Request, actor: Actor = Depends(get_actor), drain: bool = False):
    guards.require_send(request, actor)
    if drain:
        return JSONResponse(print_watch.drain_alerts())
    return JSONResponse(print_watch.peek_alerts())


@router.get("/printers/{printer_id}/status")
def printer_status(printer_id: str, request: Request, actor: Actor = Depends(get_actor)):
    pr = _require_printer(printer_id, request, actor)
    return JSONResponse(printers.status(pr))


@router.post("/printers/{printer_id}/control")
def printer_control(printer_id: str, request: Request, actor: Actor = Depends(get_actor),
                    action: str = Form(...)):
    pr = _require_printer(printer_id, request, actor)
    return JSONResponse(printers.control(pr, action))


@router.get("/printers/{printer_id}/camera")
def printer_camera(printer_id: str, request: Request, actor: Actor = Depends(get_actor)):
    pr = _require_printer(printer_id, request, actor)
    snap = printers.camera_snapshot(pr)
    if not snap.get("ok"):
        return JSONResponse(snap, status_code=502 if snap.get("message") else 200)
    return Response(snap["data"], media_type=snap.get("content_type") or "image/jpeg",
                    headers={"Cache-Control": "no-store",
                             "X-ZEIM-Verification": printers.verification_tag(pr.get("type"))})


@router.post("/printers/{printer_id}/timelapse/start")
def timelapse_start(printer_id: str, request: Request, actor: Actor = Depends(get_actor)):
    _require_printer(printer_id, request, actor)
    return JSONResponse(print_watch.timelapse_start(printer_id))


@router.post("/printers/{printer_id}/timelapse/stop")
def timelapse_stop(printer_id: str, request: Request, actor: Actor = Depends(get_actor)):
    _require_printer(printer_id, request, actor)
    return JSONResponse(print_watch.timelapse_stop(printer_id))


@router.post("/printers/{printer_id}/timelapse/tick")
def timelapse_tick(printer_id: str, request: Request, actor: Actor = Depends(get_actor)):
    _require_printer(printer_id, request, actor)
    return JSONResponse(print_watch.timelapse_tick(printer_id))


@router.get("/print-queue")
def queue_list(request: Request, actor: Actor = Depends(get_actor)):
    guards.require_send(request, actor)
    return JSONResponse(print_queue.list_jobs())


@router.post("/print-queue")
def queue_add(request: Request, actor: Actor = Depends(get_actor),
              printer_id: str = Form(...), build_id: str = Form(...),
              name: str = Form(""), start_on_send: bool = Form(False)):
    guards.require_send(request, actor)
    meta_for(build_id, actor, owner_only=True)
    return JSONResponse(print_queue.enqueue(printer_id, build_id, name=name, start_on_send=start_on_send))


@router.delete("/print-queue/{job_id}")
def queue_del(job_id: str, request: Request, actor: Actor = Depends(get_actor)):
    guards.require_send(request, actor)
    return JSONResponse(print_queue.remove(job_id))


@router.post("/print-queue/{job_id}/start")
def queue_start(job_id: str, request: Request, actor: Actor = Depends(get_actor)):
    guards.require_send(request, actor)
    if not printers.direct_control_enabled():
        raise HTTPException(410, printers.DIRECT_OFF_MESSAGE)
    return JSONResponse(print_queue.start_job(job_id))
