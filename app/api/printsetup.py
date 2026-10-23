"""Printer + nozzle choice, 'Will it print?' checks, open-in-slicer instructions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api import guards
from app.community import catalog
from app.community.identity import Actor, get_actor
from app.community.store import USERS
from app.services import print_setup as ps
from app.services import willprint

router = APIRouter(tags=["printer-setup"])

# "Open in" targets. Only documented URL schemes would be used, and none of these works for a file hosted on ZEIM:
# PrusaSlicer documents prusaslicer://open?file= but only downloads from printables.com, thingiverse.com and cults3d.com;
# Bambu Studio's bambustudio:// handler is not publicly documented (MakerWorld only); Creality Print, ELEGOO
# SatelLite/ElegooSlicer and Anycubic Slicer Next document no URL scheme. So every button downloads the right file
# and says exactly how to open it. No cloud accounts are linked.
OPEN_IN = [
    {"id": "creality", "label": "Creality Print", "format": "3mf", "scheme": None,
     "steps": "Open Creality Print, choose File > Import (or drag the file onto the plate), then pick your printer and Slice."},
    {"id": "bambu", "label": "Bambu Studio", "format": "3mf", "scheme": None,
     "steps": "Open Bambu Studio, choose File > Import > Import 3MF/STL (or drag the file in), then Slice plate."},
    {"id": "prusa", "label": "PrusaSlicer", "format": "3mf", "scheme": None,
     "steps": "Open PrusaSlicer, choose File > Import > Import STL/3MF (Ctrl+I), check the printer at the top right, then Slice now."},
    {"id": "elegoo", "label": "ELEGOO slicer", "format": "stl", "scheme": None,
     "steps": "FDM (Neptune): open ElegooSlicer, File > Import. Resin (Mars/Saturn): open CHITUBOX or VoxelDance Tango and drag the STL in."},
    {"id": "anycubic", "label": "Anycubic slicer", "format": "stl", "scheme": None,
     "steps": "FDM (Kobra): open Anycubic Slicer Next, File > Import. Resin (Photon): open Anycubic Photon Workshop and open the STL."},
    # Every other brand (Longer, Raise3D, UltiMaker, Flashforge, Qidi, Sovol, Voron, Two Trees, Kingroon, Tronxy, BIQU, ...)
    {"id": "other3mf", "label": "another slicer (3MF)", "format": "3mf", "scheme": None,
     "steps": "OrcaSlicer, UltiMaker Cura, ideaMaker, QIDI Studio, Flashforge Orca and most current slicers: File > Import/Open, pick your printer, then Slice."},
    {"id": "otherstl", "label": "any slicer (STL)", "format": "stl", "scheme": None,
     "steps": "Older or resin slicers (Longerware, CHITUBOX, Lychee, Photon Workshop, Simplify3D): open or drag in the STL, pick your printer, then slice."},
]


@router.get("/api/printers/catalog")
def printer_catalog():
    return {**ps.public(), "open_in": OPEN_IN,
            "open_in_note": "These buttons download the file; your slicer opens it from there. No account linking."}


def _pref(actor: Actor) -> dict:
    u = actor.user or {}
    pr = u.get("printer") or {}
    try:
        pid, n = ps.resolve(pr.get("printer_id"), pr.get("nozzle"))
    except ps.SetupError:
        pid, n = ps.resolve()
    return {"printer_id": pid, "nozzle": n}


def save_pref(sid: str, printer_id, nozzle) -> dict:
    pid, n = ps.resolve(printer_id, nozzle)
    USERS.update(lambda d: d[sid].__setitem__("printer", {"printer_id": pid, "nozzle": n}) if sid in d else None)
    return {"printer_id": pid, "nozzle": n}


@router.get("/api/me/printer")
def get_my_printer(actor: Actor = Depends(get_actor)):
    return {"signed_up": bool(actor.user), "stored": "profile" if actor.user else "browser", **_pref(actor)}


@router.put("/api/me/printer")
def put_my_printer(body: dict, actor: Actor = Depends(get_actor)):
    try:
        pid, n = ps.resolve(body.get("printer_id"), body.get("nozzle"))
    except ps.SetupError as e:
        raise HTTPException(400, str(e))
    if not actor.user:                         # anonymous: validated here, kept in the browser (localStorage) by the page
        return {"signed_up": False, "stored": "browser", "printer_id": pid, "nozzle": n}
    return {"signed_up": True, "stored": "profile", **save_pref(actor.sid, pid, n)}


@router.get("/api/me/printer-kind")
def get_my_printer_kind(actor: Actor = Depends(get_actor)):
    k = (actor.user or {}).get("printer_kind")
    return {"signed_up": bool(actor.user), "kind": k if k in ("fdm", "resin") else None}


@router.put("/api/me/printer-kind")
def put_my_printer_kind(body: dict, actor: Actor = Depends(get_actor)):
    k = body.get("kind")
    if k not in ("fdm", "resin"):
        raise HTTPException(400, "kind must be fdm or resin")
    if actor.user:
        USERS.update(lambda d: d[actor.sid].__setitem__("printer_kind", k) if actor.sid in d else None)
    return {"signed_up": bool(actor.user), "stored": "profile" if actor.user else "browser", "kind": k}


@router.get("/api/me/adult")
def get_my_adult(actor: Actor = Depends(get_actor)):
    """First-visit 18+ confirmation. Only a 'yes' is ever stored (and only on an account); a 'no' is never recorded."""
    return {"signed_up": bool(actor.user), "confirmed": bool((actor.user or {}).get("adult_confirmed_at"))}


@router.put("/api/me/adult")
def put_my_adult(body: dict, actor: Actor = Depends(get_actor)):
    if body.get("adult") is not True:
        raise HTTPException(400, "Only a yes is recorded.")
    if actor.user:
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        USERS.update(lambda d: d[actor.sid].__setitem__("adult_confirmed_at", ts) if actor.sid in d else None)
    return {"signed_up": bool(actor.user), "stored": "profile" if actor.user else "browser", "confirmed": True}


def slice_check(mesh_path, printer_id, nozzle):
    """Real PrusaSlicer run (Standard preset) for the 'slices OK' check, cached per file + printer + nozzle."""
    import hashlib, json, tempfile
    from pathlib import Path
    from app import config
    from app.services import slice_engine as eng
    st = Path(mesh_path).stat()
    key = hashlib.sha256(f"{mesh_path}|{st.st_size}|{st.st_mtime_ns}|{printer_id}|{nozzle}".encode()).hexdigest()[:32]
    cache = config.DATA / "willprint" / (key + ".json")
    if cache.is_file():
        return tuple(json.loads(cache.read_text()))
    try:
        prof, _s = eng.profile_for(printer_id, nozzle, {})
        with tempfile.TemporaryDirectory(prefix="zeim-wp-") as td:
            src = Path(td) / "m.stl"
            import trimesh
            m = trimesh.load(str(mesh_path), force="mesh")
            m.apply_translation(-m.bounds[0]); src.write_bytes(m.export(file_type="stl"))
            eng.slice_stl(src, prof, Path(td) / "m.gcode")
        res = (True, "")
    except eng.SliceError as e:
        if e.code in ("slicer_unavailable", "slice_timeout"):
            return (None, e.message)                       # not a verdict on the model: don't cache
        res = (False, e.message)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(res))
    return res


async def _ck(mesh_path, printer_id, nozzle, run_slice=False):
    from starlette.concurrency import run_in_threadpool
    try:
        ok, msg = (None, "")
        ps.resolve(printer_id, nozzle)
        if run_slice:
            pid, n = ps.resolve(printer_id, nozzle)
            if n is not None:
                ok, msg = await run_in_threadpool(slice_check, mesh_path, pid, n)
        return await willprint.check_file_async(mesh_path, printer_id, nozzle, slices_ok=ok, slice_message=msg)
    except ps.SetupError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(400, "We couldn't read that model.")


@router.get("/api/willprint/build/{bid}")
async def willprint_build(bid: str, printer_id: str = "", nozzle: str = "", slice: bool = False, actor: Actor = Depends(get_actor)):
    from app.api.slice import resolve_model
    from starlette.concurrency import run_in_threadpool
    return await _ck(await run_in_threadpool(resolve_model, bid, actor), printer_id or None, nozzle or None, slice)


@router.get("/api/showcase/{iid}/willprint")
async def willprint_showcase(iid: str, printer_id: str = "", nozzle: str = "", slice: bool = False, actor: Actor = Depends(get_actor)):
    from starlette.concurrency import run_in_threadpool
    guards.showcase_gate(actor)
    try:
        i = await run_in_threadpool(catalog.get, iid, actor)
    except catalog.Denied as e:
        raise HTTPException(e.status if hasattr(e, "status") else 404, "not found")
    stls = [f["name"] for f in i.get("files", []) if f["name"].lower().endswith((".stl", ".3mf", ".obj"))]
    paths = [p for p in (catalog.file_path(i, n) for n in stls) if p]
    if not paths:
        return {"verdict": "unknown", "label": "No model file to check", "checks": {}, "tips": []}
    plates = [await _ck(p, printer_id or None, nozzle or None, slice) for p in paths[:6]]
    worst = min(plates, key=lambda r: ["no", "maybe", "unchecked", "likely", "yes"].index(r["verdict"]))
    return {**worst, "plates": len(plates)}
