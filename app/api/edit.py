"""Edit workspace API: upload STL/OBJ/3MF (or a photo, or a ZEIM build) → non-destructive edit → export / slice / print."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

import base64
import json

from ..community import badges, privacy, safety
from ..community.identity import Actor, get_actor
from ..config import MAX_BUILDS
from ..core import autotune, exporters, geometry, imagesafe, meshedit, meshparts
from ..core import features as features_mod
from ..core import printcheck as printcheck_mod
from ..core import volcost as volcost_mod
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


def _fdm_lean(data: bytes):
    """(data, note): a very big binary STL from the FDM tab simplified in a fresh, memory-capped interpreter, else unchanged."""
    from ..core import fdmlean
    if not fdmlean.faces_if_big(data):
        return data, ""
    try:
        out, n, k = fdmlean.shrink_isolated(data)
    except fdmlean.Busy:
        raise HTTPException(503, "The server is busy with another big model. Try again in a minute.")
    except fdmlean.TooBig:
        raise HTTPException(413, "This model is too big for the server to simplify. Try a smaller or simplified file.")
    except meshedit.OpError as e:
        raise HTTPException(422, str(e))
    return out, (f"This model has {n:,} triangles, so the slicer uses a simplified copy with {k:,} "
                 "(the shape change is far smaller than a print layer).")


def _scale_preview(preview: dict, factor: float) -> dict:
    """Scale encoded view positions into millimetres. No positions (the browser drew its own) is a no-op."""
    bodies = preview.get("bodies") or []
    if factor == 1.0 or not bodies or not bodies[0].get("positions"):
        return preview
    raw = base64.b64decode(bodies[0]["positions"])
    arr = np.frombuffer(raw, dtype="<f4").copy() * np.float32(factor)
    bodies[0]["positions"] = base64.b64encode(np.ascontiguousarray(arr.astype("<f4")).tobytes()).decode()
    return preview


def _open_large_stl(data: bytes, actor: Actor, title: str, beginner: bool, auto_delete_oldest: bool,
                    base: dict, warnings: list, scale: float, units: str, stream: bool, background: BackgroundTasks,
                    client_view: bool = False):
    """Show a lighter view quickly. The original STL is stored unchanged. Slice waits for the full check.

    The full file and the mesh check are a background task that runs after this response is finished.
    Starting them earlier holds the preview behind the disk write and the mesh load.

    `client_view` means the browser already drew a sample from the file. The response then omits the
    sampled triangles (several megabytes of base64). The preview file is still written after that
    line, for a later reload. Slice still uses the original bytes.
    """
    from .builds import disk_guard

    def commit(preview: dict, size_mm: list, triangles: int, *, persist_preview: bool, bounds: dict | None = None):
        preview = _scale_preview(preview, scale)
        if scale != 1.0:
            size_mm = [round(float(v) * scale, 3) for v in size_mm]
            if bounds:
                bounds = {k: [round(float(v) * scale, 3) for v in vals] for k, vals in bounds.items()}
        # The small record is written here so a slice that arrives with the view already sees slice_ready false.
        # The preview file, the history scan, and the disk sweep are not on this side of the yield.
        meta = editproj.create_pending_stl(
            actor.sid, privacy.default_level(actor), title=title, base=base, original=None,
            beginner=beginner, warnings=warnings, preview=preview if persist_preview else None,
            size_mm=size_mm, triangles=triangles,
            import_scale=scale, import_units=units, write_preview=persist_preview, bounds=bounds)
        background.add_task(editproj.store_original_and_check, meta["id"], data)
        body = {**editproj.quick_payload(meta, preview), "history": None}
        return meta["id"], body

    def bookkeeping():
        try:
            disk_guard()
            with store.lock:
                store.reserve(actor.sid, auto_delete_oldest)
        except HistoryFull:
            pass

    def store_view_file(bid: str):
        """Sampled preview for a reload. Failure leaves the project; the open view is already on screen."""
        ready = {}
        for ev in editproj.iter_binary_stl_preview(data):
            if ev.get("phase") == "preview_ready":
                ready = ev
        if ready:
            editproj.write_preview(bid, _scale_preview(ready["preview"], scale))

    if not stream:
        disk_guard()
        with store.lock:
            try:
                store.reserve(actor.sid, auto_delete_oldest)
            except HistoryFull:
                return _full(actor)
        if client_view:
            triangles, bounds = editproj.binary_stl_bounds(data)
            _bid, project = commit(editproj.slim_preview(triangles > editproj.MAX_PREVIEW_FACES),
                                   bounds["size_mm"], triangles, persist_preview=False, bounds=bounds)
            store_view_file(_bid)
        else:
            ready = {}
            for ev in editproj.iter_binary_stl_preview(data):
                if ev.get("phase") == "preview_ready":
                    ready = ev
            _bid, project = commit(ready["preview"], ready["size_mm"], ready["triangles"],
                                   persist_preview=True, bounds=ready.get("bounds"))
        project["history"] = [summary(m) for m in store.list(actor.sid)]
        return project

    def body():
        try:
            if client_view:
                triangles, bounds = editproj.binary_stl_bounds(data)
                yield json.dumps({"phase": "view", "done": triangles, "total": triangles, "unit": "triangles"}) + "\n"
                bid, project = commit(editproj.slim_preview(triangles > editproj.MAX_PREVIEW_FACES),
                                      bounds["size_mm"], triangles, persist_preview=False, bounds=bounds)
                yield json.dumps({"phase": "interactive", "slice_ready": False, "project": project}) + "\n"
                try:
                    store_view_file(bid)
                except Exception:
                    import logging
                    logging.getLogger("zeim.import").exception("preview file was not stored")
                bookkeeping()
                return
            ready = {}
            for ev in editproj.iter_binary_stl_preview(data):
                if ev.get("phase") == "preview_ready":
                    ready = ev
                else:
                    yield json.dumps(ev) + "\n"
            bid, project = commit(ready["preview"], ready["size_mm"], ready["triangles"],
                                  persist_preview=False, bounds=ready.get("bounds"))
            yield json.dumps({"phase": "interactive", "slice_ready": False, "project": project}) + "\n"
            # After the view line: capacity sweep and the preview file. A slow disk stays behind the line.
            bookkeeping()
            editproj.write_preview(bid, ready["preview"])
        except Exception:
            import logging
            logging.getLogger("zeim.import").exception("large STL view failed")
            yield json.dumps({"phase": "error", "message": "The model could not be opened. Nothing was simplified."}) + "\n"

    return StreamingResponse(body(), media_type="application/x-ndjson", headers={
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
    })


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
    background: BackgroundTasks,
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
    fdm_big: bool = Form(False),                # FDM tab still sends this. Large STLs are no longer replaced with a simpler mesh.
    progress: str = Form(""),                   # "1": newline JSON phases while the view is built
    client_view: str = Form(""),                # "1": the browser already drew a sample; do not send those triangles back
    select: str = Form(""),                     # Select mode: traced selection for a photo base (app/core/selectmask.py)
    mtl: UploadFile | None = File(None),        # optional OBJ material library (Kd colours)
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
    build_parts = None
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
        src_origin = meta.get("origin") or (meta.get("base") or {}).get("origin")
        if src_origin == "lithophane" or meta.get("kind", "photo") == "photo":
            base["origin"] = "lithophane"
        # A build whose printable mesh is the bodies themselves keeps those bodies as parts.
        # Pop-art (and anything else with a separate solid) is still one heightfield, so the colours really are gone.
        build_parts = None if mdl.single is not None else meshparts.from_bodies(mdl.bodies, len(mesh.faces))
        if build_parts is None and len({(b.color or "").lower() for b in mdl.bodies}) > 1:
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
            if fdm_big:
                from ..core import memtrim
                background.add_task(memtrim.trim)                # FDM tab: give the big upload's heap back afterwards
            from ..core import fdmlean
            if ext == "stl" and fdmlean.faces_if_big(data):
                _gate(data, actor)
                scale = meshedit.UNIT_MM.get(units, 1.0)
                base = {"type": "upload", "format": "stl", "units": units}
                fast_title = title or sample_title or "My model"
                return _open_large_stl(data, actor, fast_title, beginner, auto_delete_oldest, base, warnings,
                                       scale, units, progress == "1", background, client_view == "1")
            _gate(data, actor)
            mtl_bytes = None
            if mtl is not None and mtl.filename and ext == "obj":
                mtl_bytes = mtl.file.read(2 * 1024 * 1024)
            try:
                mesh, build_parts, w = meshedit.load_document(
                    data, ext, units_scale=meshedit.UNIT_MM[units], mtl=mtl_bytes, split_shells=True)
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
            from ..core import selectmask
            try:
                sel = selectmask.parse(select)
            except selectmask.SelectError as e:
                raise HTTPException(400, str(e))
            if sel:
                params["select"] = sel
            mdl = geometry.build(im, photo_mode, params)
            v, f = mdl.solid()
            mesh = trimesh.Trimesh(v, f, process=False)
            original, ext_o = exporters.to_stl(mdl), "stl"
            build_parts = None if mdl.single is not None else meshparts.from_bodies(mdl.bodies, len(mesh.faces))
            source_image = (data, src_ext)
            base = {"type": "photo", "origin": "lithophane", "photo_mode": photo_mode, "width_mm": width_mm, "params": params}
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
                                   warnings=warnings, import_scale=scale, import_units=units, source_image=source_image,
                                   parent_build=from_build or "", parts=build_parts)
        except meshedit.OpError as e:
            raise HTTPException(422, str(e))
        if ack is not None:
            meta["photo_ack"] = ack; store.save(meta)
    return {**editproj.payload(meta["id"]), "history": [summary(m) for m in store.list(actor.sid)]}


@router.get("/{bid}")
def get_project(bid: str, brief: int = 0, actor: Actor = Depends(get_actor)):
    _edit_meta(bid, actor)
    # brief=1 is the "is the full check done yet" poll. It must not ship the sampled view again.
    return editproj.payload(bid, include_preview=not brief)


@router.post("/{bid}/parts/detect")
def detect_parts(bid: str, actor: Actor = Depends(get_actor)):
    """Split disconnected shells into parts. The printable mesh stays one mesh."""
    meta = _edit_meta(bid, actor, owner_only=True)
    blocked = editproj.not_ready(meta)
    if blocked:
        raise HTTPException(409, blocked)
    mesh = editproj.mesh_at(bid, meta)
    try:
        parts = meshparts.detect(mesh, meta.get("parts"))
    except meshparts.PartsError as e:
        raise HTTPException(422, str(e))
    editproj.save_parts(bid, parts)
    return editproj.payload(bid)


@router.put("/{bid}/support-paint")
def put_support_paint(bid: str, body: dict, actor: Actor = Depends(get_actor)):
    """Remember paint-on support strokes for this shape. The mesh is not modified."""
    from ..services.support_paint import PaintError, parse_strokes
    _edit_meta(bid, actor, owner_only=True)
    try:
        strokes = parse_strokes(body.get("strokes") if isinstance(body, dict) else None)
    except PaintError as e:
        raise HTTPException(400, str(e))
    return editproj.save_support_paint(bid, strokes)


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




@router.get("/{bid}/volcost")
def volcost(bid: str, material: str = "PLA", price_per_kg: float | None = None,
            infill_pct: float = 20.0, wall_factor: float = 1.15, actor: Actor = Depends(get_actor)):
    """Material grams and cost estimate from mesh volume (not from G-code)."""
    meta = _edit_meta(bid, actor)
    try:
        return volcost_mod.estimate(editproj.mesh_at(bid, meta), material, price_per_kg, infill_pct, wall_factor)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/{bid}/fonts")
async def upload_font(bid: str, file: UploadFile = File(...), actor: Actor = Depends(get_actor)):
    """Upload a custom TTF/OTF for text ops in this bot's shared font library (data/fonts/)."""
    _edit_meta(bid, actor, owner_only=True)
    name = (file.filename or "font.ttf").rsplit("/", 1)[-1]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ("ttf", "otf"):
        raise HTTPException(400, "Only .ttf or .otf font files are accepted.")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Font file is too large (max 5 MB).")
    if len(data) < 100:
        raise HTTPException(400, "That does not look like a font file.")
    # Safe stem
    import re
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", name.rsplit(".", 1)[0]).strip("-").lower() or "custom"
    dest_dir = Path(__file__).resolve().parents[2] / "data" / "fonts"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{stem}.{ext}"
    dest.write_bytes(data)
    return {"ok": True, "font": stem, "fonts": meshedit.list_fonts(), "message": f"Saved font “{stem}”."}


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
    if op in ("hollow", "boolean", "text", "base", "smart_split", "on_face", "thread"):                      # the heavy ones write big new meshes
        from .builds import disk_guard
        disk_guard()
    out = _act(bid, actor, lambda: editproj.add_op(bid, op, params))
    if isinstance(out, dict) and op == "smart_split":
        return badges.merge(out, actor, "smart_split")
    if isinstance(out, dict) and op == "round_edges":
        return badges.merge(out, actor, "fillet")
    return out


@router.post("/{bid}/plate/split")
def split_plate(bid: str, body: dict | None = None, actor: Actor = Depends(get_actor)):
    """Objects that don't fit the bed after Auto-arrange go onto a new plate project (offered, never forced)."""
    body = body or {}
    meta = _edit_meta(bid, actor, owner_only=True)
    from .builds import disk_guard
    disk_guard()
    try:
        out = editproj.split_plate(bid, actor.sid, meta.get("visibility") or privacy.default_level(actor), body,
                                   auto_delete_oldest=bool(body.get("auto_delete_oldest")))
    except HistoryFull:
        return _full(actor)
    except meshedit.OpError as e:
        raise HTTPException(422, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {**out, "project": editproj.payload(bid)}


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


@router.get("/{bid}/versions")
def list_versions(bid: str, actor: Actor = Depends(get_actor)):
    _edit_meta(bid, actor, owner_only=True)
    from ..services import versions
    return {"versions": versions.list_versions(bid), "max": versions.MAX_VERSIONS}


@router.post("/{bid}/versions")
def save_version(bid: str, body: dict, actor: Actor = Depends(get_actor)):
    from ..services import versions
    _edit_meta(bid, actor, owner_only=True)
    try:
        v = versions.save(bid, str((body or {}).get("label") or ""))
    except safety.ChatBlocked as e:
        return JSONResponse(status_code=e.status, content=e.payload)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"version": v, "versions": versions.list_versions(bid)}


@router.post("/{bid}/versions/{n}/restore")
def restore_version(bid: str, n: int, actor: Actor = Depends(get_actor)):
    from ..services import versions
    return _act(bid, actor, lambda: versions.restore(bid, n) and None)


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
            mesh, file_parts, w = meshedit.load_document(
                data, ext, units_scale=meshedit.UNIT_MM[units], split_shells=True)
        except meshedit.OpError as e:
            raise HTTPException(422, f"File {n}: {e}")
        scale = meshedit.UNIT_MM[units] if ext != "3mf" else 1.0
        loaded.append({"n": n, "data": data, "ext": ext, "mesh": mesh, "warnings": w, "scale": scale, "parts": file_parts})

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
            for x in loaded:
                if len(x.get("parts") or []) > 1:
                    warnings.append(f"{len(x['parts'])} objects in file {x['n']} were merged into one mesh (colours/materials are not kept).")
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
                                       warnings=warnings, import_scale=1.0, import_units="mm",
                                       ai=any(x["ext"] == "3mf" and editproj.ai_in_3mf(x["data"]) for x in loaded))
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
                                           warnings=x["warnings"], import_scale=x["scale"], import_units=units,
                                           ai=x["ext"] == "3mf" and editproj.ai_in_3mf(x["data"]), parts=x.get("parts"))
                except meshedit.OpError as e:
                    raise HTTPException(422, f"File {x['n']}: {e}")
                made.append(meta["id"])
            out = {"mode": "separate", "projects": made, "project": editproj.payload(made[0])}
    return {**out, "history": [summary(m) for m in store.list(actor.sid)]}
