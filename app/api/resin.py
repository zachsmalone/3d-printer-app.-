"""TorchC0 (ZEIM's resin program) API.
GET  /api/resin/catalog   resin printers, presets, safety notes.
POST /api/resin/prepare   model_id (your build) or an uploaded STL/3MF/OBJ -> hollowed, tilted, supported STL + 3MF + report.
                          Optional island_supports / drains: JSON [[x,y,z],...] from a report's layer_check "at" values
                          (one-click "Add supports to islands" / "Add drain hole"). price empty = no cost (never guessed).
Heavy geometry runs in core/guard.py's memory-capped child. Files are kept for an hour."""
from __future__ import annotations

import json
import os
import time
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import config
from ..community import badges
from ..community.identity import Actor, get_actor
from ..core import guard, meshedit, resin
from ..services import editproj
from ..services import print_setup as ps

router = APIRouter(prefix="/api/resin", tags=["resin"])
KEEP_S = 3600


def _dir():
    d = config.DATA / "resin"; d.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for f in d.iterdir():
        try:
            if now - f.stat().st_mtime > KEEP_S:
                f.unlink()
        except OSError:
            pass
    return d


@router.get("/catalog")
def catalog():
    printers = [p for p in ps.public()["printers"] if p["technology"] == "Resin"]
    return {"program": resin.NAME, "printers": printers, "default_preset": resin.DEFAULT_PRESET,
            "default_material": resin.DEFAULT_MATERIAL, "materials": resin.public_materials(),
            "presets": [{"id": k, **v} for k, v in resin.PRESETS.items()], "limits": resin.LIMITS,
            "safety": resin.SAFETY, "default_price": resin.DEFAULT_PRICE, "default_price_unit": resin.DEFAULT_PRICE_UNIT, "test_note": resin.TEST_NOTE,
            "formats_note": "TorchC0 exports STL and 3MF for your printer's own resin slicer (CHITUBOX, Lychee, Photon Workshop, "
                            "VoxelDance Tango, PrusaSlicer, PreForm), which makes the layer file."}


def _points(raw: str, what: str):
    """JSON list of [x, y, z] points sent back from a report's "at" values; [] if empty."""
    if not raw:
        return []
    try:
        v = json.loads(raw)
        pts = [[float(a), float(b), float(c)] for a, b, c in v]
    except (ValueError, TypeError):
        raise HTTPException(400, f"{what} must be a list of [x, y, z] points.")
    if len(pts) > 200 or any(abs(x) > 1e5 or x != x for p in pts for x in p):
        raise HTTPException(400, f"Too many or bad {what}.")
    return pts


# Address-space budget for one TorchC0 prepare child. Hollow + supports + layer checks on an ordinary ~9 MB STL
# (~180k triangles) peak around 1.4 GB resident, which the shared 1.5 GB default could not hold (422 / crash).
RESIN_MEM_MB = int(os.environ.get("ZEIM_RESIN_MEM_MB", "2500"))


# Hollowing, supports and the layer checks grow with triangle count (trimesh ray/section queries): a 545k-triangle
# model (an ordinary ~8 MB 3MF) peaked near 2.8 GB. Above this, prepare works on a simplified copy; on smooth or
# finely meshed models the change is far below the 0.05 mm layer height.
RESIN_MAX_FACES = int(os.environ.get("ZEIM_RESIN_MAX_FACES", "200000"))


def _fit_faces(m):
    n0 = len(m.faces)
    if n0 <= RESIN_MAX_FACES:
        return m, ""
    try:
        lo, r = meshedit.op_simplify(m, {"keep_ratio": max(0.02, RESIN_MAX_FACES / n0)})
    except meshedit.OpError:
        return m, ""
    if len(lo.faces) >= n0 or not lo.is_watertight and m.is_watertight:
        return m, ""
    return lo, (f"This model has {n0:,} triangles, so TorchC0 prepared a simplified copy with {len(lo.faces):,} "
                "(the shape change is far smaller than a print layer).")


def _to_stl(data):
    m, _ = meshedit.load_mesh(data, "3mf")
    return m.export(file_type="stl")


def _work(data, ext, s, bed, isl=None, drains=None):
    m, _ = meshedit.load_mesh(data, ext)
    m, note = _fit_faces(m)
    out, rep = resin.prepare(m, s, bed, island_supports=isl, drains=drains)
    if note:
        rep.setdefault("notes", []).insert(0, note)
    return out.export(file_type="stl"), out.export(file_type="3mf"), rep


@router.post("/prepare")
def prepare(model_id: str = Form(""), printer_id: str = Form(""), material: str = Form(""), preset: str = Form(""), layer_mm: str = Form(""),
            exposure_s: str = Form(""), bottom_exposure_s: str = Form(""), bottom_layers: str = Form(""),
            lift_mm: str = Form(""), lift_speed_mm_min: str = Form(""), tilt_deg: str = Form(""), hollow: str = Form("true"),
            wall_mm: str = Form(""), drain_mm: str = Form(""), supports: str = Form("true"), support_spacing_mm: str = Form(""),
            base_lift_mm: str = Form(""), price: str = Form(""), price_unit: str = Form(""), island_supports: str = Form(""), drains: str = Form(""), file: UploadFile | None = File(None), actor: Actor = Depends(get_actor)):
    try:
        s = resin.settings({k: v for k, v in locals().items() if k in (
            "material", "preset", "layer_mm", "exposure_s", "bottom_exposure_s", "bottom_layers", "lift_mm", "lift_speed_mm_min", "tilt_deg",
            "hollow", "wall_mm", "drain_mm", "supports", "support_spacing_mm", "base_lift_mm", "price", "price_unit")})
    except resin.ResinError as e:
        raise HTTPException(400, str(e))
    isl, drn = _points(island_supports, "Island supports"), _points(drains, "Drain holes")
    bed, pname = None, None
    if printer_id:
        try:
            pid, _ = ps.resolve(printer_id, None)
        except ps.SetupError as e:
            raise HTTPException(400, str(e))
        p = ps.printer_public(pid)
        if p["technology"] != "Resin":
            raise HTTPException(400, f"The {p['name']} is a filament printer. Use the Slicer for it; TorchC0 is for resin printers.")
        bed, pname = p["bed_mm"], p["name"]
    if file is not None and file.filename:
        limit = editproj.MAX_UPLOAD_EDIT
        data = file.file.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(413, f"File too large (max {limit // 2**20} MB).")
        if not data:
            raise HTTPException(400, "The file is empty.")
        ext = meshedit.guess_model_ext(file.filename, data, getattr(file, "content_type", "") or "")
        if ext not in meshedit.ALLOWED:
            raise HTTPException(415, "TorchC0 takes .stl, .3mf or .obj files.")
        bad = meshedit.sniff(data, ext)
        if bad:
            raise HTTPException(415, bad)
        from ..services import uploadgate
        try:
            uploadgate.gate(data, actor.sid, source="edit", max_bytes=limit)
        except uploadgate.GateError as e:
            raise HTTPException(e.status, e.message)
    elif model_id:
        from .slice import resolve_model
        data, ext = resolve_model(model_id, actor).read_bytes(), "stl"
    else:
        raise HTTPException(400, "Choose a model or upload an STL, 3MF or OBJ file.")
    try:
        if ext == "3mf":
            # Parse the 3MF in its own short-lived child and hand the work child plain STL bytes: the XML parse leaves
            # ~800 MB of address space behind, which pushed ordinary 8 MB 3MFs over the work child's budget (422).
            data, ext = guard.run(_to_stl, data, timeout=120), "stl"
        stl, tmf, rep = guard.run(_work, data, ext, s, bed, isl, drn, timeout=240, mem_mb=RESIN_MEM_MB)
    except meshedit.OpError as e:
        raise HTTPException(422, str(e))
    except guard.Busy:
        raise HTTPException(503, "TorchC0 is busy. Try again in a moment.")
    except guard.Tripped:
        raise HTTPException(422, "This model is too big or complex for TorchC0 here. Simplify it, or turn hollowing off.")
    rid = uuid.uuid4().hex
    d = _dir()
    (d / f"{rid}.stl").write_bytes(stl); (d / f"{rid}.3mf").write_bytes(tmf)
    from ..services import filenames as fnames
    src = (file.filename.rsplit(".", 1)[0] if file is not None and file.filename else "") or "TorchC0 model"
    stem = fnames.default_stem(src, pname, s.get("layer_mm") if isinstance(s, dict) else None)
    (d / f"{rid}.json").write_text(json.dumps({"sid": actor.sid, "name": stem}))
    rep["downloads"] = {"stl": f"/api/resin/{rid}/torchc0.stl", "3mf": f"/api/resin/{rid}/torchc0.3mf"}
    rep["export"] = {"rid": rid, "name": stem, "formats": [f"/api/resin/{rid}/torchc0.{k}" for k in RESIN_FORMATS]}
    return badges.merge(rep, actor, "resin_slice")


RESIN_FORMATS = ("stl", "3mf", "obj", "ply", "glb", "amf")


@router.get("/{rid}/torchc0.{fmt}")
def download(rid: str, fmt: str, name: str = "", actor: Actor = Depends(get_actor)):
    """The prepared resin model in any picker format, under 'Title - Printer - 0.05mm' or the chosen name."""
    from fastapi import Response
    from ..services import filenames as fnames
    from ..services import universal_export as ue
    if fmt not in RESIN_FORMATS or len(rid) != 32 or any(c not in "0123456789abcdef" for c in rid) or len(name) > 400:
        raise HTTPException(404, "Not found")
    d = config.DATA / "resin"
    try:
        info = json.loads((d / f"{rid}.json").read_text())
        owner = info["sid"]
    except (OSError, ValueError, KeyError):
        raise HTTPException(404, "That file has expired. Prepare it again.")
    if owner != actor.sid or not (d / f"{rid}.stl").is_file():
        raise HTTPException(404, "That file has expired. Prepare it again.")
    fname = fnames.file_name(name or info.get("name") or "torchc0", fmt)
    if fmt in ("stl", "3mf") and (d / f"{rid}.{fmt}").is_file():
        data = (d / f"{rid}.{fmt}").read_bytes()
    else:
        import trimesh
        m = trimesh.load(str(d / f"{rid}.stl"), file_type="stl", force="mesh")
        data, _ext, _mt = ue.export_mesh_data(m, force_format=fmt)
    resp = Response(content=data, media_type=ue.FORMATS[fmt]["mime"],
                    headers={"Content-Disposition": fnames.disposition(fname), "Cache-Control": "no-store"})
    if fmt in badges.EXPORT_EXTS:
        badges.stamp(resp, actor, "export")
    return resp
