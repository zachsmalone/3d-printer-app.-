"""Print hand-off: slicer deep links, built-in slice, network printer send."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from .. import config
from ..services import handoff, printers, settings, slicer
from ..services.history import store
from ..community import privacy
from ..community.identity import Actor, get_actor
from . import guards
from .builds import load_model, meta_for

router = APIRouter(prefix="/api")
files_router = APIRouter()


base_url = settings.base_url


FILE_NAMES = ("model.stl", "model.obj", "model.3mf", "thumb.png", "model.gcode")


def _send_file(bid: str, name: str):
    from ..services import editproj
    if name not in FILE_NAMES or not bid.isalnum():
        raise HTTPException(404)
    if name.startswith("model.") and name != "model.gcode":
        editproj.ensure_exports(bid)
    p = store.dir(bid) / name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, filename=f"photo3d_{bid}.{name.split('.')[-1]}" if name != "thumb.png" else None, headers={"Cache-Control": "no-store"})


@files_router.get("/files/{bid}/{name}")
def serve_file(bid: str, name: str, actor: Actor = Depends(get_actor)):
    """Stable, extension-terminated URLs. Needs access (owner / visibility) - private builds are 404 to others."""
    meta_for(bid, actor)
    return _send_file(bid, name)


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
    return {"base_url": settings.trusted_base_url(request) or "", "default_slicer": s["default_slicer"], "effective_slicer": settings.effective_slicer(s),
            "slicers": [] if no_base else handoff.links(base_url(request), bid, lambda n: privacy.make_token(bid, n)),
            "slicer_links_disabled": ("Slicer links are off until the site's public address is set in Settings. You can still download the file." if no_base else ""),
            "printers": settings.public(s, redact=not guards.can_see_printer_urls(request, actor))["printers"], "printer_types": printers.TYPES,
            "builtin_slicer": slicer.status(),
            "hint": "Deep links need the slicer installed on the SAME computer as your browser, and the "
                    "file URL must be reachable from it (set 'Public base URL' in Settings if the server "
                    "is remote). Links are signed, work for one file only, and expire after 10 minutes, so a private build stays private."}


def _slice(bid, layer_height, fill_density, upright, supports, brim, bed, profile_ini=None, **chosen):
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
    chosen = {"printer_id": catalog_printer, "nozzle": nozzle} if catalog_printer else {}
    res = _slice(bid, layer_height, fill_density, upright, supports, brim, printers.bed_of(pr), printers.ini_of(pr), **chosen)
    res["bed"] = list(printers.bed_of(pr))
    if res.get("ok"):
        res["download"] = f"/files/{bid}/model.gcode"
    return JSONResponse(res)  # unavailable slicer -> 200 with available=false


@router.post("/send/{bid}")
def send_to_printer(bid: str, request: Request, actor: Actor = Depends(get_actor), printer_id: str = Form(...), start: bool = Form(False),
                    layer_height: float = Form(0.2), fill_density: int = Form(15),
                    upright: bool = Form(False), supports: bool = Form(False), brim: float = Form(0.0)):
    guards.require_send(request, actor)
    meta_for(bid, actor, owner_only=True)
    pr = settings.get_printer(printer_id)
    if not pr:
        raise HTTPException(404, "unknown printer")
    if pr["type"] not in printers.IMPLEMENTED:
        return JSONResponse(printers.send(pr, None, "", start))  # clear stub message
    res = _slice(bid, layer_height, fill_density, upright, supports, brim, printers.bed_of(pr), printers.ini_of(pr))
    if not res.get("ok"):
        return JSONResponse({"ok": False, "stage": "slice", **res})
    out = printers.send(pr, store.dir(bid) / "model.gcode", f"photo3d_{bid}.gcode", start)
    return JSONResponse({**out, "stage": "upload", "slice": res})


@router.post("/printers/{printer_id}/test")
def test_printer(printer_id: str, request: Request, actor: Actor = Depends(get_actor)):
    """Connection test: read-only GET requests to the printer, NEVER a print or upload command. Same guard as /api/send, plus on a
    shared server only the owner/admin (the server connects to whatever address was saved: keep that to the person who saved it)."""
    guards.require_send(request, actor)
    if not guards.can_see_printer_urls(request, actor):
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
