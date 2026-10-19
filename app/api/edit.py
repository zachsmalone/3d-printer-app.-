"""Edit workspace API: upload STL/OBJ/3MF (or a photo, or a ZEIM build) → non-destructive edit → export / slice / print."""
from __future__ import annotations

import numpy as np
import trimesh
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ..community import privacy, safety
from ..community.identity import Actor, get_actor
from ..config import MAX_BUILDS
from ..core import autotune, exporters, geometry, imagesafe, meshedit
from ..core import features as features_mod
from ..core import printcheck as printcheck_mod
from ..core import thickness as thickness_mod
from ..services import editproj
from ..services.history import HistoryFull, store
from .builds import _safe_title, load_model, meta_for, summary
from .textcap import plain_text, text_in

router = APIRouter(prefix="/api/edit")


def _gate(data: bytes, actor: Actor):
    """The shared upload gate (rate limit + content check + audit + optional malware scan), same as photo uploads."""
    from ..services import uploadgate
    try:
        uploadgate.gate(data, actor.sid, source="edit", max_bytes=editproj.MAX_UPLOAD_EDIT)
    except uploadgate.GateError as e:
        raise HTTPException(e.status, e.message)


def _edit_meta(bid: str, actor: Actor, owner_only=False) -> dict:
    meta = meta_for(bid, actor, owner_only=owner_only)
    if meta.get("kind") != "edit":
        raise HTTPException(404, "not an edit project")
    return meta


@router.get("/tolerance")
def tolerance(process: str = "fdm", fit: str = "normal", nominal: float = 6.0, kind: str = "hole"):
    """Suggested hole/peg size for a fit (starting point, not measured)."""
    try:
        return printcheck_mod.tolerance(process, fit, nominal, kind)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/capabilities")
def capabilities():
    return editproj.capabilities()


def _full(actor):
    from .builds import full_response
    return full_response(actor)


@router.post("/new")
def new_project(
    actor: Actor = Depends(get_actor),
    file: UploadFile | None = File(None),
    from_build: str = Form(""),
    title: str = Form(""),
    units: str = Form("mm"),
    beginner: bool = Form(True),
    auto_delete_oldest: bool = Form(False),
    photo_mode: str = Form("lithophane"),
    width_mm: float = Form(100.0),
    photo_ack: bool = Form(False),
    keep_history: bool = Form(True),
):
    """Start an edit project from an uploaded mesh, an uploaded photo (lithophane/relief base) or an existing build."""
    try:
        title = text_in(title, 80, "Title")
        plain_text(title, "Title")
        if title:
            safety.filter_only(title, "Title")
    except ValueError as e:
        raise HTTPException(400, str(e))
    if units not in meshedit.UNIT_MM:
        raise HTTPException(400, f"units must be one of {list(meshedit.UNIT_MM)}")
    warnings: list[str] = []
    source_image = None
    ack = None
    scale, base = 1.0, {}
    if from_build:                                              # ---- bring a ZEIM build into the editor
        meta = meta_for(from_build, actor, owner_only=True)
        title = title or meta["title"]
        if meta.get("kind") == "edit" and keep_history:         # 'Save as a new version': keep every step editable (B12)
            from .builds import disk_guard
            disk_guard()
            with store.lock:
                try:
                    store.reserve(actor.sid, auto_delete_oldest)
                except HistoryFull:
                    return _full(actor)
                try:
                    new = editproj.clone(actor.sid, privacy.default_level(actor), from_build, title=title.strip(), beginner=beginner)
                except meshedit.OpError as e:
                    raise HTTPException(422, str(e))
            return {**editproj.payload(new["id"]), "history": [summary(m) for m in store.list(actor.sid)]}
        if meta.get("kind") == "edit":
            editproj.ensure_exports(from_build)
        mdl = load_model(from_build)
        v, f = mdl.solid()
        mesh = trimesh.Trimesh(v, f, process=False)
        original, ext = exporters.to_stl(mdl), "stl"
        base = {"type": "build", "from_build": from_build, "from_mode": meta.get("mode")}
        if len({(b.color or "").lower() for b in mdl.bodies}) > 1:          # only when colours are really lost (B12)
            warnings.append("Colours / separate colour bodies of the original build are merged into one mesh in the editor.")
    elif file is not None and file.filename:                    # ---- upload
        name = file.filename
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        limit = editproj.MAX_UPLOAD_EDIT
        data = file.file.read(limit + 1)
        sample_title = imagesafe.builtin_title(data)
        if len(data) > limit:
            raise HTTPException(413, f"File too large (max {limit // 2**20} MB).")
        if not data:
            raise HTTPException(400, "The file is empty.")
        if ext not in meshedit.IMAGE_EXT:
            ext = meshedit.guess_model_ext(name, data, getattr(file, "content_type", "") or "") or ext
        if ext in meshedit.ALLOWED:
            bad = meshedit.sniff(data, ext)
            if bad:
                raise HTTPException(415, bad)
            _gate(data, actor)
            try:
                mesh, w = meshedit.load_mesh(data, ext, units_scale=meshedit.UNIT_MM[units])     # warn on the converted size (B9)
            except meshedit.OpError as e:
                raise HTTPException(422, str(e))
            warnings += w
            original = data
            if ext != "3mf":
                scale = meshedit.UNIT_MM[units]
            base = {"type": "upload", "format": ext, "units": units if ext != "3mf" else "from file"}
        elif ext in meshedit.IMAGE_EXT:                         # photo / lithophane base
            if len(data) > 25 * 2**20:
                raise HTTPException(413, "Photo too large (max 25 MB).")
            if photo_mode not in ("lithophane", "relief"):
                raise HTTPException(400, "photo_mode must be lithophane | relief")
            if not (20 <= width_mm <= 500):
                raise HTTPException(400, "width_mm must be 20..500")
            try:
                ack = imagesafe.check_ack(data, photo_ack)      # CR-5
                data, src_ext, _ = imagesafe.sanitize(data)
                im = geometry.load_image(data)
            except imagesafe.ImageRefused as e:
                raise HTTPException(415, str(e))
            except Exception:
                raise HTTPException(415, imagesafe.UNREADABLE)
            params, _ = autotune.autotune(im, photo_mode, width_mm, "standard")
            params["resolution"] = min(params.get("resolution", 200), 220)
            mdl = geometry.build(im, photo_mode, params)
            v, f = mdl.solid()
            mesh = trimesh.Trimesh(v, f, process=False)
            original, ext_o = exporters.to_stl(mdl), "stl"
            source_image = (data, src_ext)
            base = {"type": "photo", "photo_mode": photo_mode, "width_mm": width_mm, "params": params}
            ext = ext_o
            warnings.append(f"Photo converted to a {photo_mode} base mesh; edit it like any other model.")
        else:
            raise HTTPException(415, "Unsupported file type. Upload .stl, .obj or .3mf (or a .png/.jpg photo).")
        title = title or sample_title or ("My photo build" if base.get("type") == "photo" else "My model")      # never from the file name
    else:
        raise HTTPException(400, "Choose a file to upload or a build to edit.")

    from .builds import disk_guard
    disk_guard()
    with store.lock:
        try:
            store.reserve(actor.sid, auto_delete_oldest)
        except HistoryFull:
            return _full(actor)
        try:
            meta = editproj.create(actor.sid, privacy.default_level(actor), title=title.strip(), base=base,
                                   original=original, original_ext=ext, mesh=mesh, beginner=beginner,
                                   warnings=warnings, import_scale=scale, import_units=units, source_image=source_image)
        except meshedit.OpError as e:
            raise HTTPException(422, str(e))
        if ack is not None:
            meta["photo_ack"] = ack; store.save(meta)
    return {**editproj.payload(meta["id"]), "history": [summary(m) for m in store.list(actor.sid)]}


@router.get("/{bid}")
def get_project(bid: str, actor: Actor = Depends(get_actor)):
    _edit_meta(bid, actor)
    return editproj.payload(bid)


@router.get("/{bid}/thickness")
def thickness(bid: str, min_wall: float = 0.8, actor: Actor = Depends(get_actor)):
    """Where the model is thinner than `min_wall` mm (read-only, sampled estimate)."""
    meta = _edit_meta(bid, actor)
    try:
        return thickness_mod.analyze(editproj.mesh_at(bid, meta), min_wall)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{bid}/printcheck")
def printcheck(bid: str, process: str = "fdm", min_wall: float | None = None, actor: Actor = Depends(get_actor)):
    """Bed fit + overhang + thin walls in one read-only, approximate report (uses this project's bed)."""
    meta = _edit_meta(bid, actor)
    try:
        return printcheck_mod.run(editproj.mesh_at(bid, meta), editproj.bed_of(meta), process, min_wall)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{bid}/features")
def features(bid: str, actor: Actor = Depends(get_actor)):
    """Flat faces, cylinders and holes found in the current mesh (read-only, approximate)."""
    meta = _edit_meta(bid, actor)
    return features_mod.detect(editproj.mesh_at(bid, meta))


def _act(bid, actor, fn):
    _edit_meta(bid, actor, owner_only=True)
    try:
        rep = fn()
    except meshedit.OpError as e:
        raise HTTPException(422, str(e))
    except safety.ChatBlocked as e:
        return JSONResponse(status_code=e.status, content=e.payload)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return editproj.payload(bid, rep)


@router.post("/{bid}/op")
def apply_op(bid: str, body: dict, actor: Actor = Depends(get_actor)):
    op = body.get("op")
    if op not in meshedit.OPS:
        raise HTTPException(400, f"unknown operation; choose from {sorted(meshedit.OPS)}")
    params = body.get("params") or {}
    if not isinstance(params, dict):
        raise HTTPException(400, "params must be an object")
    if op in ("hollow", "boolean", "text", "base", "smart_split", "on_face"):                      # the heavy ones write big new meshes
        from .builds import disk_guard
        disk_guard()
    return _act(bid, actor, lambda: editproj.add_op(bid, op, params))


@router.put("/{bid}/step/{i}")
def edit_step(bid: str, i: int, body: dict, actor: Actor = Depends(get_actor)):
    """Change one step's parameters; every later step is replayed (all-or-nothing)."""
    params = body.get("params")
    if not isinstance(params, dict):
        raise HTTPException(400, "params must be an object")
    return _act(bid, actor, lambda: editproj.edit_step(bid, i, params))


@router.put("/{bid}/dims")
def set_dims(bid: str, body: dict, actor: Actor = Depends(get_actor)):
    """Replace the named dimensions ({"dims": {"wall": 2.4}}); steps using "$wall" are replayed (all-or-nothing)."""
    return _act(bid, actor, lambda: editproj.set_dims(bid, body.get("dims")))


@router.delete("/{bid}/step/{i}")
def delete_step(bid: str, i: int, actor: Actor = Depends(get_actor)):
    return _act(bid, actor, lambda: editproj.delete_step(bid, i))


@router.post("/{bid}/undo")
def undo(bid: str, actor: Actor = Depends(get_actor)):
    return _act(bid, actor, lambda: editproj.undo(bid))


@router.post("/{bid}/redo")
def redo(bid: str, actor: Actor = Depends(get_actor)):
    return _act(bid, actor, lambda: editproj.redo(bid))


@router.post("/{bid}/goto")
def goto(bid: str, body: dict, actor: Actor = Depends(get_actor)):
    try:
        h = int(body.get("head"))
    except (TypeError, ValueError):
        raise HTTPException(400, "head must be an integer")
    return _act(bid, actor, lambda: editproj.goto(bid, h))


@router.get("/{bid}/original")
def original(bid: str, actor: Actor = Depends(get_actor)):
    """The upload exactly as received (never modified)."""
    _edit_meta(bid, actor)
    f = next(store.dir(bid).glob("original.*"), None)
    if not f:
        raise HTTPException(404)
    return FileResponse(f, filename=f"original_{bid}{f.suffix}", headers={"Cache-Control": "no-store"})


MAX_MULTI_FILES = 12


@router.post("/multi")
def new_multi(
    actor: Actor = Depends(get_actor),
    files: list[UploadFile] = File(...),
    mode: str = Form("plate"),
    units: str = Form("mm"),
    beginner: bool = Form(True),
    auto_delete_oldest: bool = Form(False),
    bed_x: float = Form(220.0),
    bed_y: float = Form(220.0),
    bed_z: float = Form(250.0),
    gap_mm: float = Form(5.0),
    printer_id: str = Form(""),
):
    """Several STL / OBJ / 3MF files at once. mode=plate: 'Parts of one print' (auto-spaced on one plate + bed-fit check, one project);
    mode=separate: 'Separate prints' (one project each)."""
    from ..core import orient
    if mode not in ("plate", "separate"):
        raise HTTPException(400, "mode must be plate | separate")
    if units not in meshedit.UNIT_MM:
        raise HTTPException(400, f"units must be one of {list(meshedit.UNIT_MM)}")
    files = [f for f in files if f is not None and f.filename]
    if not files:
        raise HTTPException(400, "Choose at least one 3D file.")
    if len(files) > MAX_MULTI_FILES:
        raise HTTPException(400, f"Up to {MAX_MULTI_FILES} files at a time.")
    if printer_id:                                   # the chosen catalog printer's bed wins over the generic default
        from ..services import print_setup as ps
        try:
            bed_x, bed_y, bed_z = ps.bed_of(ps.resolve(printer_id)[0])
        except ps.SetupError as e:
            raise HTTPException(400, str(e))
    if not (20 <= bed_x <= 2000 and 20 <= bed_y <= 2000 and 20 <= bed_z <= 2000 and 0 <= gap_mm <= 50):
        raise HTTPException(400, "Bed size must be 20..2000 mm and the gap 0..50 mm.")
    loaded, total = [], 0
    for n, f in enumerate(files, 1):
        data = f.file.read(editproj.MAX_UPLOAD_EDIT + 1)
        total += len(data)
        if len(data) > editproj.MAX_UPLOAD_EDIT or total > 2 * editproj.MAX_UPLOAD_EDIT:
            raise HTTPException(413, f"Files too large (max {editproj.MAX_UPLOAD_EDIT // 2**20} MB each).")
        if not data:
            raise HTTPException(400, f"File {n} is empty.")
        name = f.filename
        ext = meshedit.guess_model_ext(name, data, getattr(f, "content_type", "") or "") or (name.rsplit(".", 1)[-1].lower() if "." in name else "")
        if ext not in meshedit.ALLOWED:
            raise HTTPException(415, f"File {n} is not an STL, OBJ or 3MF file.")
        bad = meshedit.sniff(data, ext)
        if bad:
            raise HTTPException(415, f"File {n}: {bad}")
        _gate(data, actor)
        try:
            mesh, w = meshedit.load_mesh(data, ext, units_scale=meshedit.UNIT_MM[units])       # warn on the converted size (B9)
        except meshedit.OpError as e:
            raise HTTPException(422, f"File {n}: {e}")
        scale = meshedit.UNIT_MM[units] if ext != "3mf" else 1.0
        loaded.append({"n": n, "data": data, "ext": ext, "mesh": mesh, "warnings": w, "scale": scale})

    from .builds import disk_guard
    disk_guard()
    made = []
    with store.lock:
        if mode == "plate":
            meshes = []
            for x in loaded:
                m = x["mesh"].copy()
                if x["scale"] != 1.0:
                    m.apply_scale(x["scale"])
                meshes.append(m)
            combined, plate = orient.arrange(meshes, (bed_x, bed_y), gap_mm, bed_z)
            warnings = [w for x in loaded for w in x["warnings"]]
            warnings.append(f"{len(loaded)} parts arranged on one plate, {gap_mm:g} mm apart.")
            if not plate["fits"]:
                warnings.append(f"The parts don't fit on a {bed_x:g} × {bed_y:g} mm bed together "
                                f"(they need {plate['footprint_mm'][0]:g} × {plate['footprint_mm'][1]:g} mm). Try 'Separate prints' or scale them down.")
            try:
                store.reserve(actor.sid, auto_delete_oldest)
            except HistoryFull:
                return _full(actor)
            try:
                meta = editproj.create(actor.sid, privacy.default_level(actor), title=f"Plate of {len(loaded)} parts",
                                       base={"type": "plate", "parts": len(loaded), "units": units, "plate": plate},
                                       original=combined.export(file_type="stl"), original_ext="stl", mesh=combined, beginner=beginner,
                                       warnings=warnings, import_scale=1.0, import_units="mm")
            except meshedit.OpError as e:
                raise HTTPException(422, str(e))
            made.append(meta["id"])
            out = {"mode": "plate", "plate": plate, "projects": made, "project": editproj.payload(meta["id"])}
        else:
            if len(store.list(actor.sid)) + len(loaded) > MAX_BUILDS and not auto_delete_oldest:
                return _full(actor)
            for x in loaded:
                try:
                    store.reserve(actor.sid, auto_delete_oldest)
                except HistoryFull:
                    return _full(actor)
                try:
                    meta = editproj.create(actor.sid, privacy.default_level(actor), title=f"Part {x['n']} of {len(loaded)}",
                                           base={"type": "upload", "format": x["ext"], "units": units if x["ext"] != "3mf" else "from file"},
                                           original=x["data"], original_ext=x["ext"], mesh=x["mesh"], beginner=beginner,
                                           warnings=x["warnings"], import_scale=x["scale"], import_units=units)
                except meshedit.OpError as e:
                    raise HTTPException(422, f"File {x['n']}: {e}")
                made.append(meta["id"])
            out = {"mode": "separate", "projects": made, "project": editproj.payload(made[0])}
    return {**out, "history": [summary(m) for m in store.list(actor.sid)]}
