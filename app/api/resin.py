"""TorchC0 (ZEIM's resin program) API.
GET  /api/resin/catalog   resin printers, presets, safety notes.
POST /api/resin/prepare   model_id (your build) or an uploaded STL/3MF/OBJ -> hollowed, tilted, supported STL + 3MF + report.
                          Optional island_supports / drains: JSON [[x,y,z],...] from a report's layer_check "at" values
                          (one-click "Add supports to islands" / "Add drain hole"). price empty = no cost (never guessed).
Heavy geometry runs in core/guard.py's memory-capped child. Files are kept for an hour."""
from __future__ import annotations

import json
import os
import threading
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
# One visitor's preview + prepare run back to back; waiting only 20 s for a slot answered "busy" to a Prepare
# pressed while a big model was still loading.
ONE_WAIT_S = float(os.environ.get("ZEIM_RESIN_WAIT_S", "150"))
_one = threading.BoundedSemaphore(1)      # one prepare at a time: two 2.5 GB children would not fit the 3 GB container


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


def _lean_binary_stl(data):
    """A big binary STL welded and simplified straight from its bytes, or None when it is not one.

    trimesh's load + merge + simplify of a 2.1M-triangle STL peaks near 1.8 GB, which does not fit next to the
    server (about 1.3 GB resident) inside the 3 GB container: the kernel killed the child and the user saw
    "busy" then "too big, turn hollowing off". numpy + fast-simplification does the same job in about 1 GB."""
    if len(data) < 84:
        return None
    n = int.from_bytes(data[80:84], "little")
    if n <= RESIN_MAX_FACES or len(data) != 84 + 50 * n or n > meshedit.MAX_FACES:
        return None
    import numpy as np
    import fast_simplification as fs
    rec = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    tri = np.ascontiguousarray(np.frombuffer(data, rec, count=n, offset=84)["v"].reshape(-1, 3))
    if not np.isfinite(tri).all():
        raise meshedit.OpError("File contains invalid coordinates.")
    u, inv = np.unique(tri.view(np.dtype((np.void, 12))).ravel(), return_inverse=True)
    del tri
    v, f = u.view("<f4").reshape(-1, 3).astype(np.float64), inv.reshape(-1, 3).astype(np.int64)
    del u, inv
    f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
    if len(f) > RESIN_MAX_FACES:
        v, f = fs.simplify(v, f, target_reduction=1 - RESIN_MAX_FACES / len(f), agg=7)
    m = meshedit._new(v, f)
    m.remove_unreferenced_vertices()
    return m, n, (f"This model has {n:,} triangles, so TorchC0 prepared a simplified copy with {len(m.faces):,} "
                  "(the shape change is far smaller than a print layer).")


def _load_fit(data, ext):
    """(mesh with at most ~RESIN_MAX_FACES triangles, original triangle count, note)."""
    lean = _lean_binary_stl(data) if ext == "stl" else None
    if lean:
        return lean
    m, _ = meshedit.load_mesh(data, ext)
    n = len(m.faces)
    m, note = _fit_faces(m)
    return m, n, note


def _to_stl(data):
    m, _ = meshedit.load_mesh(data, "3mf")
    return m.export(file_type="stl")


def _work(data, ext, s, bed, isl=None, drains=None, note=""):
    m, _n, fit_note = _load_fit(data, ext)
    note = note or fit_note
    out, rep = resin.prepare(m, s, bed, island_supports=isl, drains=drains)
    if note:
        rep.setdefault("notes", []).insert(0, note)
    return out.export(file_type="stl"), out.export(file_type="3mf"), rep


PREVIEW_FACES = int(os.environ.get("ZEIM_RESIN_PREVIEW_FACES", "150000"))


def _preview(data, ext):
    """The model as prepare will use it (<= RESIN_MAX_FACES), for the view AND for prepare (see /preview)."""
    m, n, note = _load_fit(data, ext)
    return m.export(file_type="stl"), n, note


def _read_upload(file, actor):
    """Read + check one uploaded model the same way prepare does. Returns (bytes, ext)."""
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
    from ..services import uploadgate, uploadsafe
    try:
        # STL stores 3 corners per triangle unwelded, so its "vertex" count is always 3x the faces: a 2.1M-triangle
        # pre-supported resin STL counted 6.3M and was refused as a wrong file type (415). The face cap still applies.
        uploadgate.gate(data, actor.sid, source="edit", max_bytes=limit, max_vertices=3 * uploadsafe.MAX_FACES)
    except uploadgate.GateError as e:
        raise HTTPException(e.status, e.message)
    return data, ext


@router.post("/preview")
def preview(file: UploadFile = File(...), actor: Actor = Depends(get_actor)):
    """Load a picked model for the TorchC0 view right away (any STL/3MF/OBJ -> binary STL, simplified for display)."""
    from fastapi import Response
    data, ext = _read_upload(file, actor)
    try:
        # same budget + one-at-a-time slot as prepare: a 2.1M-triangle STL needs ~2 GB to load and simplify
        if not _one.acquire(timeout=ONE_WAIT_S):
            raise guard.Busy()
        try:
            stl, n, note = guard.run(_preview, data, ext, timeout=180, mem_mb=RESIN_MEM_MB)
        finally:
            _one.release()
    except meshedit.OpError as e:
        raise HTTPException(422, str(e))
    except guard.Busy:
        raise HTTPException(503, "TorchC0 is busy. Try again in a moment.")
    except guard.Tripped:
        raise HTTPException(422, "This model is too big or complex to load here. Simplify it first.")
    # Keep the loaded copy so Prepare sends its id instead of uploading (and re-reading) a 100 MB file again.
    uid = uuid.uuid4().hex
    d = _dir()
    (d / f"up{uid}.stl").write_bytes(stl)
    (d / f"up{uid}.json").write_text(json.dumps({"sid": actor.sid, "note": note}))
    return Response(stl, media_type="model/stl", headers={"X-Zeim-Faces": str(n), "X-Zeim-Upload": uid, "Cache-Control": "no-store"})


def _picked(uid, actor):
    """(stl bytes, note) of a model loaded by /preview for this visitor, or 410 when it expired / is not theirs."""
    if not (len(uid) == 32 and all(c in "0123456789abcdef" for c in uid)):
        raise HTTPException(400, "Bad upload id.")
    d = _dir()
    try:
        meta = json.loads((d / f"up{uid}.json").read_text())
        if meta.get("sid") != actor.sid:
            raise FileNotFoundError
        return (d / f"up{uid}.stl").read_bytes(), meta.get("note", "")
    except (OSError, ValueError):
        raise HTTPException(410, "That loaded model has expired. Choose the file again.")


@router.post("/prepare")
def prepare(model_id: str = Form(""), printer_id: str = Form(""), material: str = Form(""), preset: str = Form(""), layer_mm: str = Form(""),
            exposure_s: str = Form(""), bottom_exposure_s: str = Form(""), bottom_layers: str = Form(""),
            lift_mm: str = Form(""), lift_speed_mm_min: str = Form(""), tilt_deg: str = Form(""), hollow: str = Form("true"),
            wall_mm: str = Form(""), drain_mm: str = Form(""), supports: str = Form("true"), support_spacing_mm: str = Form(""),
            base_lift_mm: str = Form(""), price: str = Form(""), price_unit: str = Form(""), upload_id: str = Form(""), file_name: str = Form(""), island_supports: str = Form(""), drains: str = Form(""), file: UploadFile | None = File(None), actor: Actor = Depends(get_actor)):
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
    note = ""
    if upload_id:
        data, note = _picked(upload_id, actor)
        ext = "stl"
    elif file is not None and file.filename:
        data, ext = _read_upload(file, actor)
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
        if not _one.acquire(timeout=ONE_WAIT_S):
            raise guard.Busy()
        try:
            stl, tmf, rep = guard.run(_work, data, ext, s, bed, isl, drn, note, timeout=240, mem_mb=RESIN_MEM_MB)
        finally:
            _one.release()
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
    src = ((file.filename if file is not None and file.filename else file_name).rsplit(".", 1)[0]) or "TorchC0 model"
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
