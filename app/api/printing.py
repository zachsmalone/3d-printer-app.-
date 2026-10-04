"""Print hand-off: slicer deep links, built-in slice, network printer send."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from ..services import handoff, printers, settings, slicer
from ..services.history import store
from ..community import privacy
from ..community.identity import Actor, get_actor
from .builds import load_model, meta_for

router = APIRouter(prefix="/api")
files_router = APIRouter()


def base_url(request: Request) -> str:
    return settings.load().get("public_base_url") or str(request.base_url).rstrip("/")


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
    return FileResponse(p, filename=f"photo3d_{bid}.{name.split('.')[-1]}" if name != "thumb.png" else None)


@files_router.get("/files/{bid}/{name}")
def serve_file(bid: str, name: str, actor: Actor = Depends(get_actor)):
    """Stable, extension-terminated URLs. Needs access (owner / visibility) - private builds are 404 to others."""
    meta_for(bid, actor)
    return _send_file(bid, name)


@files_router.get("/f/{token}/{bid}/{name}")
def serve_file_token(token: str, bid: str, name: str):
    """Signed, expiring (2 h) link used by slicer deep links so a PRIVATE build can be opened by the owner's
    slicer (which has no browser cookie). Token is bound to one build id; useless for any other build."""
    if not privacy.check_token(bid, token):
        raise HTTPException(404)
    return _send_file(bid, name)


@router.get("/print/{bid}/links")
def print_links(bid: str, request: Request, actor: Actor = Depends(get_actor)):
    meta_for(bid, actor, owner_only=True)
    s = settings.load()
    return {"base_url": base_url(request), "default_slicer": s["default_slicer"],
            "slicers": handoff.links(base_url(request), bid, privacy.make_token(bid)),
            "printers": settings.public(s)["printers"], "printer_types": printers.TYPES,
            "builtin_slicer": slicer.status(),
            "hint": "Deep links need the slicer installed on the SAME computer as your browser, and the "
                    "file URL must be reachable from it (set 'Public base URL' in Settings if the server "
                    "is remote). Links are signed and expire after 2 hours, so a private build stays private."}


def _slice(bid, layer_height, fill_density, upright, supports, brim, bed):
    st = slicer.status()
    if not st["available"]:
        return st
    try:
        model = load_model(bid)
    except KeyError:
        raise HTTPException(404, "unknown build")
    return slicer.slice_model(model, store.dir(bid), layer_height, fill_density, upright, supports,
                              brim, bed)


@router.post("/slice/{bid}")
def slice_build(bid: str, actor: Actor = Depends(get_actor), layer_height: float = Form(0.2), fill_density: int = Form(15),
                upright: bool = Form(False), supports: bool = Form(False), brim: float = Form(0.0)):
    meta_for(bid, actor, owner_only=True)
    res = _slice(bid, layer_height, fill_density, upright, supports, brim, (250, 210))
    if res.get("ok"):
        res["download"] = f"/files/{bid}/model.gcode"
    return JSONResponse(res)  # unavailable slicer -> 200 with available=false


@router.post("/send/{bid}")
def send_to_printer(bid: str, actor: Actor = Depends(get_actor), printer_id: str = Form(...), start: bool = Form(False),
                    layer_height: float = Form(0.2), fill_density: int = Form(15),
                    upright: bool = Form(False), supports: bool = Form(False), brim: float = Form(0.0)):
    meta_for(bid, actor, owner_only=True)
    pr = settings.get_printer(printer_id)
    if not pr:
        raise HTTPException(404, "unknown printer")
    if pr["type"] not in printers.IMPLEMENTED:
        return JSONResponse(printers.send(pr, None, "", start))  # clear stub message
    res = _slice(bid, layer_height, fill_density, upright, supports, brim,
                 (pr.get("bed_x") or 250, pr.get("bed_y") or 210))
    if not res.get("ok"):
        return JSONResponse({"ok": False, "stage": "slice", **res})
    out = printers.send(pr, store.dir(bid) / "model.gcode", f"photo3d_{bid}.gcode", start)
    return JSONResponse({**out, "stage": "upload", "slice": res})
