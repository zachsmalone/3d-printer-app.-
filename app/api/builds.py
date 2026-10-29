"""Build creation, history and downloads."""
from __future__ import annotations

import base64
import time
import uuid

import numpy as np
import trimesh
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from PIL import Image

from .. import config
from ..community import privacy, safety
from .textcap import text_in
from ..community.identity import Actor, get_actor
from ..config import MAX_BUILDS, MAX_UPLOAD, PREVIEW_RES
from ..core import autotune, exporters, geometry, imagesafe, litho_backing
from ..services import retention, uploadgate
from ..services.history import HistoryFull, store

router = APIRouter(prefix="/api")


def mesh_stats(model: geometry.Model) -> dict:
    bodies, ok = [], True
    for b in model.bodies:
        t = trimesh.Trimesh(b.vertices, b.faces, process=False)
        wt = bool(t.is_watertight and t.is_winding_consistent and t.volume > 0)
        ok &= wt
        bodies.append({"name": b.name, "triangles": int(len(b.faces)), "watertight": wt,
                       "volume_mm3": round(float(t.volume), 2)})
    v, f = model.solid()
    if model.single is not None:
        ts = trimesh.Trimesh(v, f, process=False)
        ok &= bool(ts.is_watertight and ts.is_winding_consistent and ts.volume > 0)
    return {"bodies": bodies, "watertight": bool(ok),
            "size_mm": (v.max(0) - v.min(0)).round(2).tolist(),
            "triangles": int(sum(len(b.faces) for b in model.bodies))}


def preview_payload(model: geometry.Model) -> dict:
    return {"bodies": [{
        "name": b.name, "color": b.color,
        "positions": base64.b64encode(b.vertices.astype("<f4").tobytes()).decode(),
        "indices": base64.b64encode(b.faces.astype("<u4").tobytes()).decode(),
    } for b in model.bodies]}


NO_STORE = {"Cache-Control": "no-store"}     # SEND-8: model files may be pictures of people; keep them out of shared/proxy caches


def summary(meta: dict) -> dict:
    """Metadata for history cards (no heavy data)."""
    bid = meta["id"]
    return {**{k: meta[k] for k in ("id", "created", "mode", "beginner", "title", "stats")},
            "kind": meta.get("kind", "photo"), "visibility": meta.get("visibility", "private"),
            "favorite": bool(meta.get("favorite")), "ai": bool(meta.get("ai")), "expires": retention.expires_at(meta),
            "file_name": meta.get("file_name") or "",
            "thumb": f"/files/{bid}/thumb.png",
            "downloads": {e: f"/files/{bid}/model.{e}" for e in exporters.WRITERS},
            "sizes": _sizes(bid)}


def _sizes(bid: str) -> dict:
    """Bytes of each export that exists on disk (the Send sheet shows them next to the file types; absent = not written yet)."""
    d = store.dir(bid)
    return {e: (d / f"model.{e}").stat().st_size for e in exporters.WRITERS if (d / f"model.{e}").exists()}


def model_from_3mf(path, mode: str) -> geometry.Model:
    """One body per 3MF object. Vertex positions are the ones written (parts stay where they were laid out)."""
    sc = trimesh.load(str(path), force="scene")
    return geometry.Model([
        geometry.Body(str(n), np.asarray(g.vertices, float), np.asarray(g.faces, np.int64))
        for n, g in sc.geometry.items()
    ], mode)


def load_model(bid: str) -> geometry.Model:
    """Model for a stored build (cached; rebuilt from source image + params after a restart)."""
    m = store.cache.get(bid)
    if m is None:
        meta = store.get(bid)
        if meta.get("mode") == "trace2d":
            from ..core import trace2d
            m = store.cache[bid] = trace2d.build((store.dir(bid) / meta["source"]).read_bytes(), None, meta["params"])
            return m
        if meta.get("kind") == "edit":
            from ..services import editproj
            m = store.cache[bid] = editproj.model(bid)
            return m
        if meta.get("mode") == "memorybox":         # no photo kept: reload the print parts (one body per 3MF object)
            m = model_from_3mf(store.dir(bid) / "model.3mf", "memorybox")
            m.info = meta.get("info") or {}
            store.cache[bid] = m
            return m
        im = geometry.load_image((store.dir(bid) / meta["source"]).read_bytes())
        m = geometry.build(im, meta["mode"], meta["params"])
        store.cache[bid] = m
    return m


def meta_for(bid: str, actor: Actor, owner_only: bool = False) -> dict:
    """Metadata of a build the actor may access; otherwise 404 (private builds look non-existent)."""
    try:
        meta = store.get(bid)
    except KeyError:
        raise HTTPException(404, "unknown build")
    if meta.get("owner_sid") == actor.sid:
        return meta
    if owner_only or not privacy.can_view(actor, meta.get("owner_sid"), meta.get("visibility", "private")):
        raise HTTPException(404, "unknown build")
    return meta


DEFAULT_PHOTO_TITLE = "My photo build"      # never derived from the uploaded file name (camera file names can hold a person's name)

# every form field of /api/generate — captured verbatim into a pending upload's context so
# /api/uploads/resume can replay the exact request once the malware scan clears
_GENERATE_FORM_FIELDS = ('mode', 'beginner', 'preset', 'auto_delete_oldest', 'title', 'width_mm', 'resolution', 'smooth', 'gamma', 'auto_contrast', 'invert', 'min_thickness', 'max_thickness', 'border_mm', 'material', 'shape', 'diameter_mm', 'height_mm', 'place_x', 'place_y', 'place_scale', 'place_rotation', 'hang', 'hole_d', 'inset_mm', 'spacing_mm', 'stand', 'stand_caps', 'frame_style', 'collage_layout', 'bend_deg', 'lip_mm', 'lip_taper', 'taper_deg', 'printer_id', 'backing', 'grey_method', 'brightness', 'contrast', 'sharpen', 'tile', 'mm_per_repeat', 'base_mm', 'relief_mm', 'base_style', 'base_margin', 'back_mm', 'levels', 'layer_mm', 'style', 'halftone_cell', 'multi_body', 'palette', 'photo_ack', 'trace', 'select')      # never derived from the uploaded file name (camera file names can hold a person's name)


def disk_guard():
    """Refuse a new heavy build, kindly, when the disk is nearly full and nothing but starred builds could be removed."""
    try:
        retention.check_disk()
    except retention.DiskLow as e:
        raise HTTPException(507, str(e))


def full_response(actor):
    """All build slots are starred: nothing is removed automatically. Ask the person to un-star or delete one."""
    return JSONResponse(status_code=409, content={
        "code": "history_full", "all_favorites": True, "max": MAX_BUILDS,
        "message": f"All {MAX_BUILDS} of your saved builds are starred ★, and starred builds are never removed by ZEIM. "
                   "Un-star or delete one to make room.",
        "builds": [summary(m) for m in store.list(actor.sid)]})


def _safe_title(derived: str) -> str:
    """A title made from the uploaded file's name: replaced by 'Untitled' if the name itself would not pass the language gate."""
    return derived if derived and not safety.scan(derived) else "Untitled"


@router.get("/builds")
def list_builds(actor: Actor = Depends(get_actor)):
    store.claim_unowned(actor.sid)
    return {"max": MAX_BUILDS, "keep_days": config.KEEP_UNSAVED_DAYS, "builds": [summary(m) for m in store.list(actor.sid)]}


@router.put("/builds/{bid}/visibility")
def build_visibility(bid: str, body: dict, actor: Actor = Depends(get_actor)):
    """Owner only. Effective immediately (checked on every file / API request)."""
    meta = meta_for(bid, actor, owner_only=True)
    try:
        meta["visibility"] = privacy.check_level(actor, body.get("visibility", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    store.save(meta)
    return summary(meta)


def memorybox_preview(bid: str, meta: dict) -> geometry.Model:
    """Assembled box for the viewer. The print file stays the separate parts."""
    path = store.dir(bid) / "assembled.3mf"
    if path.exists():
        m = model_from_3mf(path, "memorybox")
    else:
        m = load_model(bid)
    m.info = meta.get("info") or {}
    return m


@router.get("/builds/{bid}")
def get_build(bid: str, actor: Actor = Depends(get_actor)):
    meta = meta_for(bid, actor)
    if meta.get("kind") == "edit":
        from ..services import editproj
        return editproj.payload(bid)
    if meta.get("mode") == "memorybox":
        params = dict(meta.get("params") or {})
        params["shape"] = "memorybox"
        return {**summary(meta), "params": params, "auto_notes": meta.get("auto_notes", []),
                "info": meta.get("info", {}), "preview": preview_payload(memorybox_preview(bid, meta))}
    model = load_model(bid)
    prev = model
    if meta["params"].get("resolution", 0) > PREVIEW_RES:
        prev = geometry.build(geometry.load_image((store.dir(bid) / meta["source"]).read_bytes()),
                              meta["mode"], {**meta["params"], "resolution": PREVIEW_RES})
    return {**summary(meta), "params": meta["params"], "auto_notes": meta.get("auto_notes", []),
            "info": meta.get("info", {}), "preview": preview_payload(prev)}


@router.delete("/builds/{bid}")
def delete_build(bid: str, actor: Actor = Depends(get_actor)):
    """Delete one saved build. A Showcase post copied from it is a separate file and stays."""
    meta_for(bid, actor, owner_only=True)
    from ..services import filestore
    filestore.delete_build(bid)               # remote FIRST, durably recorded — raises => local survives
    store.delete(bid)
    return {"ok": True}


@router.post("/uploads/resume/{pid}")
def resume_pending(pid: str, actor: Actor = Depends(get_actor)):
    """Resume a pending upload (created when the malware scanner was down): re-scan the HELD
    original bytes; a clean scan re-runs the full generate pipeline (every check re-runs);
    an infected verdict discards it; a scanner still down keeps it pending. Owner only."""
    from ..services import quarantine
    if not pid.isalnum() or len(pid) != 12:
        raise HTTPException(404)
    ctx = quarantine.pending_context(pid)
    if ctx is None:
        raise HTTPException(404, "unknown pending upload")
    if ctx.get("sid") != actor.sid:
        raise HTTPException(404)                      # not yours: indistinguishable from missing
    verdict = quarantine.scan_pending(pid)
    if verdict == "infected":
        quarantine.discard_pending(pid, "infected on scan")
        raise HTTPException(422, "That file was flagged by the malware scanner. Nothing of it was kept.")
    if verdict != "clean":
        return JSONResponse(status_code=202, content={
            "status": "pending_scan", "pending_id": pid, "detail": quarantine.PENDING_MSG})
    # clean: replay the exact original request through the normal pipeline (the gate re-runs).
    # The pending record is consumed ONLY on success or a validated rejection — if generation
    # fails (history full, storage error), the upload is RETAINED and the user can retry.
    raw = quarantine.pending_bytes(pid)
    import io
    from starlette.datastructures import UploadFile as _SU
    up = _SU(file=io.BytesIO(raw), filename=ctx.get("filename") or "upload")
    form = ctx.get("form") or {}
    out = generate(actor=actor, file=up, **form)
    # consume the pending record ONLY when a build was really created — a 409 history-full
    # (or any non-build response, or an exception) RETAINS the upload so the user can retry
    if isinstance(out, dict) and out.get("id"):
        quarantine.discard_pending(pid, "resumed into a build")
    return out


@router.post("/builds/delete-oldest")
def delete_oldest(actor: Actor = Depends(get_actor)):
    with store.lock:
        items = [m for m in store.list(actor.sid)
                 if not (m.get("favorite") or m.get("saved"))]          # never a starred/saved build
        if not items:
            return {"ok": True, "deleted": None}
        from ..services import filestore
        filestore.delete_build(items[0]["id"])       # remote FIRST, durably recorded — raises => local survives
        store.delete(items[0]["id"])
        return {"ok": True, "deleted": items[0]["id"]}


@router.post("/builds/{bid}/favorite")
def favorite_build(bid: str, body: dict, actor: Actor = Depends(get_actor)):
    """Star / un-star a build. Starred builds are never removed by age, by the cap or by a low disk; only you deleting them does."""
    meta_for(bid, actor, owner_only=True)
    return summary(store.set_favorite(bid, bool(body.get("favorite"))))


@router.post("/generate")
def generate(
    actor: Actor = Depends(get_actor),
    file: UploadFile = File(...),
    mode: str = Form("lithophane"),
    beginner: bool = Form(False),
    preset: str = Form("standard"),          # beginner: thin | standard | thick
    auto_delete_oldest: bool = Form(False),  # confirm replacing oldest when history is full
    title: str = Form(""),
    width_mm: float = Form(100.0),
    resolution: int = Form(200),
    smooth: float = Form(0.8),
    gamma: float = Form(1.0),
    auto_contrast: bool = Form(True),
    invert: bool = Form(False),
    min_thickness: float = Form(0.8),
    max_thickness: float = Form(3.0),
    border_mm: float = Form(3.0),
    material: str = Form("filament"),       # lithophane printer type: filament | resin (beginner defaults only)
    shape: str = Form("rect"),               # lithophane outline: rect | flat (heart/circle/star/square/hexagon/diamond/oval/triangle/scallop) | globe | nightlight | cup | curve
    diameter_mm: float = Form(40.0),         # curved shapes: globe diameter / light diameter the night-light slips over
    height_mm: float = Form(60.0),           # curved shapes: height
    place_x: str = Form(""),                 # image placement inside the shape (see litho_shapes.check_place)
    place_y: str = Form(""),
    place_scale: str = Form(""),
    place_rotation: str = Form(""),
    hang: str = Form(""),                    # lithophane hanging holes: "" | top | two
    hole_d: float = Form(4.0),               # hanging hole diameter (mm)
    inset_mm: float = Form(6.0),             # hanging hole centre from the top edge (mm)
    spacing_mm: float = Form(40.0),          # distance between the two holes of hang=two (mm)
    stand: bool = Form(False),               # lithophane display stand as a second body (curved panel: built-in foot)
    stand_caps: bool = Form(False),          # friction-fit end-cap plugs for the U-channel stand (two extra bodies)
    frame_style: str = Form("plain"),        # flat rim style: plain | double | ledge
    collage_layout: str = Form(""),          # "" = single photo; hstrip | vstrip | grid = multi-photo collage
    extra: list[UploadFile] = File(None),    # extra photos for collage (with `file` = 2..6 total)
    backing: str = Form(""),               # lithophane backing / backlight colour: warm, cool, paper or #rrggbb (saved with the build)
    bend_deg: float = Form(90.0),            # curved panel: bend from flat (0) to half circle (180)
    lip_mm: str = Form(""),                   # sleeve / cup band height; "" = follow border_mm (older builds)
    lip_taper: str = Form("none"),            # none | outward | inward | both
    taper_deg: float = Form(45.0),            # slope from vertical, 20..45 (no supports)
    printer_id: str = Form(""),              # bed-fit check for shaped lithophanes ("" = the default printer)
    grey_method: str = Form("rec601"),       # lithophane grey: rec601 | rec709 | average | lightness | max
    brightness: float = Form(0.0),           # -1..1 manual brightness after auto-contrast
    contrast: float = Form(0.0),             # -1..1 manual contrast after auto-contrast
    sharpen: float = Form(0.0),              # 0..2 unsharp amount
    tile: bool = Form(False),                # seamless tile the photo across the plate / circumference
    mm_per_repeat: float = Form(40.0),       # physical width of one tile when tile=true
    base_mm: float = Form(2.0),
    relief_mm: float = Form(6.0),
    base_style: str = Form("round"),          # bust pedestal: round | rect | outline
    base_margin: float = Form(8.0),            # bust pedestal margin beyond footprint (mm)
    back_mm: float = Form(14.0),               # bust rounded-back depth (mm); 0 = flat back
    levels: int = Form(4),
    layer_mm: float = Form(1.0),
    style: str = Form("posterize"),
    halftone_cell: float = Form(6.0),
    multi_body: bool = Form(True),
    palette: str = Form(""),
    photo_ack: bool = Form(False),
    trace: str = Form(""),                   # mode=trace2d ('Logo & Drawing to 3D'): JSON of the trace2d options
    select: str = Form(""),                  # Select mode: JSON of the traced selection (app/core/selectmask.py); "" = whole photo
):
    if mode not in ("lithophane", "relief", "popart", "bust", "trace2d"):
        raise HTTPException(400, f"unknown mode {mode}")
    try:
        title = text_in(title, 80, "Title")
        if title:
            safety.filter_only(title, "Title")
    except ValueError as e:
        raise HTTPException(400, str(e))
    data = file.file.read(MAX_UPLOAD + 1)
    sample_title = imagesafe.builtin_title(data)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "image too large (max 25 MB)")
    try:
        checked = uploadgate.gate(data, actor.sid, source="generate")
    except uploadgate.GateError as e:
        raise HTTPException(e.status, e.message)
    if getattr(checked, "scan_state", "off") == "unscanned":
        # Scanner explicitly on but unreachable: the upload is NOT built — no artifacts, no
        # metadata, nothing cached or served. The original bytes + request context are parked
        # in restricted pending storage; resume (/api/uploads/resume/<pid>) runs the normal
        # pipeline once a scan clears them.
        from ..services import quarantine
        frame = dict(locals())          # snapshot BEFORE the comprehension (version-safe)
        ctx = {k: frame[k] for k in _GENERATE_FORM_FIELDS if k in frame}
        pid = quarantine.stage_pending(actor.sid, data, ctx, file.filename or "upload")
        return JSONResponse(status_code=202, content={
            "status": "pending_scan", "pending_id": pid,
            "detail": quarantine.PENDING_MSG,
        })
    from ..core import selectmask
    try:
        sel = selectmask.parse(select) if mode != "trace2d" else None
    except selectmask.SelectError as e:
        raise HTTPException(400, str(e))
    if mode == "trace2d":
        return _generate_trace(actor, data, photo_ack, trace, width_mm, title, sample_title, auto_delete_oldest)
    try:
        ack = imagesafe.check_ack(data, photo_ack)        # CR-5: "this is my photo / I have permission" (built-in sample exempt)
        data, src_ext, _ = imagesafe.sanitize(data)       # HEIC -> JPEG, rotation applied, EXIF/GPS dropped, extension from content
        im = geometry.load_image(data)
    except imagesafe.ImageRefused as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(400, imagesafe.UNREADABLE)
    collage_meta = None
    if not (5 <= width_mm <= 1000):
        raise HTTPException(400, "width_mm must be 5..1000")
    try:
        geometry.check_params(im, mode, {"width_mm": width_mm})          # extreme shapes are refused BEFORE a history slot is touched
    except ValueError as e:
        raise HTTPException(400, str(e))

    from ..core import litho_shapes
    if mode == "lithophane":
        if material not in autotune.LITHO_MATERIALS:
            raise HTTPException(400, "material must be filament or resin")
        if shape not in litho_shapes.SHAPES:
            raise HTTPException(400, "shape must be one of " + " | ".join(litho_shapes.SHAPES))
        if shape in litho_shapes.CURVED_SHAPES and not (10 <= diameter_mm <= 200 and 10 <= height_mm <= 240):
            raise HTTPException(400, "diameter_mm must be 10..200 and height_mm 10..240")
        try:
            backing = litho_backing.normalize(backing) if mode == "lithophane" else ""
        except ValueError as e:
            raise HTTPException(400, str(e))
        if shape in litho_shapes.PANEL_SHAPES and not (0 <= bend_deg <= litho_shapes.BEND_MAX_DEG):
            raise HTTPException(400, "bend_deg must be 0..180")
        lip = None
        if shape in ("nightlight", "cup") and str(lip_mm).strip() != "":
            try:
                lip = litho_shapes.check_lip(float(lip_mm), lip_taper, taper_deg)
            except ValueError as e:
                raise HTTPException(400, str(e))
    # Collage: compose 2–6 photos into one image, then the normal lithophane path.
    # Distinct from the memory box (no cube / light base). CMYK colour layers are out of scope.
    if mode == "lithophane" and str(collage_layout or "").strip():
        from ..core import litho_collage
        extras = [f for f in (extra or []) if getattr(f, "filename", "")]
        try:
            layout = litho_collage.check_layout(collage_layout)
        except ValueError as e:
            raise HTTPException(400, str(e))
        ims = [im]
        for up in extras:
            raw_e = up.file.read(MAX_UPLOAD + 1)
            if len(raw_e) > MAX_UPLOAD:
                raise HTTPException(413, "image too large (max 25 MB)")
            try:
                checked_e = uploadgate.gate(raw_e, actor.sid, source="generate")
            except uploadgate.GateError as e:
                raise HTTPException(e.status, e.message)
            if getattr(checked_e, "scan_state", "off") == "unscanned":
                raise HTTPException(503, "A collage photo is still waiting on the malware scan. Try again in a moment.")
            try:
                imagesafe.check_ack(raw_e, photo_ack)
                raw_e, _, _ = imagesafe.sanitize(raw_e)
                ims.append(geometry.load_image(raw_e))
            except imagesafe.ImageRefused as e:
                raise HTTPException(400, str(e))
            except Exception:
                raise HTTPException(400, imagesafe.UNREADABLE)
        try:
            litho_collage.check_count(len(ims))
            im = litho_collage.compose(ims, layout)
            collage_meta = litho_collage.info(len(ims), layout)
        except ValueError as e:
            raise HTTPException(400, str(e))

    place = None
    if mode == "lithophane" and shape not in ("rect",) + litho_shapes.PANEL_SHAPES:
        raw = {k: v for k, v in (("x", place_x), ("y", place_y), ("scale", place_scale), ("rotation", place_rotation))
               if str(v).strip() != ""}
        try:
            place = litho_shapes.check_place(raw)
        except ValueError as e:
            raise HTTPException(400, str(e))

    disk_guard()
    with store.lock:  # serialise so concurrent builds can't exceed the cap
        try:
            store.reserve(actor.sid, auto_delete_oldest)
        except HistoryFull:
            return full_response(actor)
        auto_notes = []
        if beginner:
            params, auto_notes = autotune.autotune(im, mode, width_mm, preset, material if mode == "lithophane" else "filament")
        else:
            params = dict(width_mm=width_mm, resolution=int(np.clip(resolution, 16, geometry.MAX_RES)),
                          smooth=smooth, gamma=gamma, auto_contrast=auto_contrast, invert=invert)
            params.update({
                "lithophane": dict(min_thickness=min_thickness, max_thickness=max_thickness, border_mm=border_mm),
                "relief": dict(base_mm=base_mm, relief_mm=relief_mm),
                "bust": dict(base_mm=base_mm if base_mm >= 0.2 else 12.0, relief_mm=relief_mm,
                             base_style=base_style if base_style in ("round", "rect", "outline") else "round",
                             base_margin=max(0.0, float(base_margin)),
                             back_mm=max(0.0, min(40.0, float(back_mm)))),
                "popart": dict(base_mm=base_mm, levels=levels, layer_mm=layer_mm, style=style,
                               halftone_cell=halftone_cell, multi_body=multi_body, palette=palette or None),
            }[mode])
        if sel:
            params["select"] = sel                 # kept in the saved build: every rebuild / re-open / Send-to applies it
        if mode == "lithophane":
            params.update(shape=shape)
            if shape in litho_shapes.CURVED_SHAPES:
                params.update(diameter_mm=diameter_mm, height_mm=height_mm)
                if lip:
                    params.update(lip_mm=lip[0], lip_taper=lip[1], taper_deg=lip[2])
            if shape in litho_shapes.PANEL_SHAPES:
                params.update(bend_deg=float(bend_deg))
            if backing:
                params.update(backing=backing)
            if place:
                params.update(place=place)
            from ..core import litho_image as LI
            try:
                tone = LI.check_tone(grey_method, brightness, contrast, sharpen)
                on, mm = LI.check_tile(tile, mm_per_repeat)
            except ValueError as e:
                raise HTTPException(400, str(e))
            params.update(grey_method=tone["grey_method"], brightness=tone["brightness"],
                          contrast=tone["contrast"], sharpen=tone["sharpen"])
            if on:
                params.update(tile=True, mm_per_repeat=mm)
            params.update(hang=hang, hole_d=hole_d, inset_mm=inset_mm, spacing_mm=spacing_mm, stand=stand)
            from ..core import litho_frame, litho_socket
            try:
                params.update(frame_style=litho_frame.check(frame_style))
            except ValueError as e:
                raise HTTPException(400, str(e))
            if litho_socket.check(stand_caps):
                params.update(stand_caps=True)
            if collage_meta:
                params.update(collage_layout=collage_meta["layout"], collage_photos=collage_meta["photos"])
        t0 = time.time()
        try:
            model = geometry.build(im, mode, params)
            if collage_meta:
                model.info = {**(model.info or {}), **collage_meta}
            prev = model
            if params["resolution"] > PREVIEW_RES:
                prev = geometry.build(im, mode, {**params, "resolution": PREVIEW_RES})
                if collage_meta:
                    prev.info = {**(prev.info or {}), **collage_meta}
        except ValueError as e:
            raise HTTPException(400, str(e))
        bid = uuid.uuid4().hex[:12]
        d = store.dir(bid)
        d.mkdir(parents=True)
        src = "source." + src_ext
        (d / src).write_bytes(data)
        for ext, fn in exporters.WRITERS.items():
            (d / f"model.{ext}").write_bytes(fn(model))
        Image.fromarray(model.thumb).save(d / "thumb.png")
        # object storage (when configured): the bucket is the durable copy of the artifacts;
        # local disk stays the slicer's/editor's working surface
        from ..services import filestore
        if filestore.enabled():
            filestore.put_build(bid, "source", data)      # stable key; ext does not matter to the bucket
            for ext in exporters.WRITERS:
                filestore.put_build(bid, f"model.{ext}", (d / f"model.{ext}").read_bytes())
            filestore.put_build(bid, "thumb.png", (d / "thumb.png").read_bytes(), "image/png")
        stats = mesh_stats(model)
        if mode == "lithophane" and params.get("shape", "rect") != "rect":
            from ..services import willprint            # same bed-fit check the Will-it-print box uses (default printer)
            model.info = {**(model.info or {}), "bed_fit": willprint.bed_fit(tuple(stats["size_mm"]), _bed_printer(printer_id))}
        meta = {"id": bid, "mode": mode, "beginner": beginner, "preset": preset if beginner else None,
                "title": title.strip() or sample_title or DEFAULT_PHOTO_TITLE,
                "source": src, "params": params, "auto_notes": auto_notes, "info": model.info,
                "stats": stats, "owner_sid": actor.sid, "visibility": privacy.default_level(actor), "photo_ack": ack}
        store.save(meta)
        store.cache[bid] = model
    return {**summary(meta), "params": params, "auto_notes": auto_notes, "info": model.info,
            "seconds": round(time.time() - t0, 2), "preview": preview_payload(prev),
            "history": [summary(m) for m in store.list(actor.sid)]}


# ---------------- 'Logo & Drawing to 3D' (trace2d) ----------------
def trace_input(data: bytes, photo_ack: bool, trace_json: str, width_mm: float):
    """Same upload safety as every photo: permission tick (CR-5) + sanitize (format sniffed, EXIF/GPS dropped, size caps).
    SVG is the one extra format: parsed as vectors with entities/network/DTDs off, embedded pictures refused, size capped.
    -> (clean bytes, ext, PIL image or None, params)."""
    import json
    from ..core import trace2d
    try:
        opts = json.loads(trace_json) if trace_json else {}
        if not isinstance(opts, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(400, "The drawing settings didn't come through. Please try again.")
    opts["width_mm"] = width_mm
    try:
        ack = imagesafe.check_ack(data, photo_ack)
        if trace2d.is_svg(data):
            trace2d.svg_to_geom(data)                     # refuses unsafe / unreadable SVG before anything is stored
            clean, ext, im = data, "svg", None
        else:
            clean, ext, _ = imagesafe.sanitize(data)
            im = geometry.load_image(clean)
            geometry.check_params(im, "trace2d", {"width_mm": width_mm})
        params = trace2d.clean_params(opts)
    except (imagesafe.ImageRefused, trace2d.TraceError) as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(400, imagesafe.UNREADABLE)
    return clean, ext, im, params, ack


def _bed_printer(printer_id: str) -> str:
    """The printer the user picked (Will-it-print / slicer picker) when it is in the catalog, else the default K1."""
    from ..services import print_setup as ps
    try:
        return ps.resolve(printer_id or None)[0]
    except Exception:
        return "creality_k1"


def _trace_notes(info: dict) -> list:
    """Notes for the result table (label / value / why), same shape as Beginner auto-notes."""
    rows = [{"label": "Tip", "value": "✔", "why": n} for n in info.get("notes", [])]
    for c in info.get("colour_changes", []):
        rows.append({"label": "Colour", "value": c["colour"], "why": f"from {c['from_mm']:g} mm to {c['to_mm']:g} mm"})
    if "wall_mm" in info:
        rows.append({"label": "Cutting wall", "value": f"{info['wall_mm']:g} mm", "why": "thin enough to cut, thick enough to print"})
    return rows


def _generate_trace(actor, data, photo_ack, trace_json, width_mm, title, sample_title, auto_delete_oldest):
    from ..core import trace2d
    from ..services import willprint
    clean, ext, im, params, ack = trace_input(data, photo_ack, trace_json, width_mm)
    disk_guard()
    with store.lock:
        try:
            store.reserve(actor.sid, auto_delete_oldest)
        except HistoryFull:
            return full_response(actor)
        t0 = time.time()
        try:
            model = trace2d.build(clean, im, params)
        except trace2d.TraceError as e:
            raise HTTPException(400, str(e))
        bid = uuid.uuid4().hex[:12]
        d = store.dir(bid)
        d.mkdir(parents=True)
        src = "source." + ext
        (d / src).write_bytes(clean)
        for e, fn in exporters.WRITERS.items():
            (d / f"model.{e}").write_bytes(fn(model))
        Image.fromarray(model.thumb).save(d / "thumb.png")
        from ..services import filestore
        if filestore.enabled():
            filestore.put_build(bid, "source", clean)
            for e in exporters.WRITERS:
                filestore.put_build(bid, f"model.{e}", (d / f"model.{e}").read_bytes())
            filestore.put_build(bid, "thumb.png", (d / "thumb.png").read_bytes(), "image/png")
        stats = mesh_stats(model)
        model.info = {**model.info, "bed_fit": willprint.bed_fit(tuple(stats["size_mm"]), "creality_k1")}
        meta = {"id": bid, "mode": "trace2d", "beginner": False, "preset": None,
                "title": title.strip() or sample_title or "My drawing build",
                "source": src, "params": params, "auto_notes": _trace_notes(model.info), "info": model.info,
                "stats": stats, "owner_sid": actor.sid, "visibility": privacy.default_level(actor), "photo_ack": ack}
        store.save(meta)
        store.cache[bid] = model
    return {**summary(meta), "params": params, "auto_notes": meta["auto_notes"], "info": model.info,
            "seconds": round(time.time() - t0, 2), "preview": preview_payload(model),
            "history": [summary(m) for m in store.list(actor.sid)]}


@router.post("/bust/auto-mask")
def bust_auto_mask(actor: Actor = Depends(get_actor), file: UploadFile = File(...),
                   photo_ack: bool = Form(False)):
    """Starting head-and-shoulders Select mask for Bust mode (editable; not a finished cut)."""
    from ..core import bust_detect
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "image too large (max 25 MB)")
    try:
        uploadgate.gate(data, actor.sid, source="bust-auto-mask")
    except uploadgate.GateError as e:
        raise HTTPException(e.status, e.message)
    try:
        imagesafe.check_ack(data, photo_ack)
        data, _, _ = imagesafe.sanitize(data)
        im = geometry.load_image(data)
    except imagesafe.ImageRefused as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(400, imagesafe.UNREADABLE)
    sel = bust_detect.auto_select(im)
    return {"select": sel, "tip": sel["tip"], "method": sel["method"]}


@router.post("/trace2d/preview")
def trace_preview(actor: Actor = Depends(get_actor), file: UploadFile = File(...), photo_ack: bool = Form(False),
                  trace: str = Form(""), width_mm: float = Form(80.0)):
    """Live 2D preview of the traced outline (nothing is stored). Same upload checks as a build."""
    from ..core import trace2d
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "image too large (max 25 MB)")
    if not (5 <= width_mm <= 400):
        raise HTTPException(400, "Width must be between 5 and 400 mm.")
    clean, ext, im, params, _ = trace_input(data, photo_ack, trace, width_mm)
    try:
        t = trace2d.trace(clean, im, params)
    except trace2d.TraceError as e:
        raise HTTPException(400, str(e))
    minx, miny, maxx, maxy = t["ink"].bounds
    return {"svg": trace2d.preview_svg(t), "holes": t["holes"], "pieces": t["pieces"], "threshold": t["threshold"],
            "size_mm": [round(maxx - minx, 1), round(maxy - miny, 1)], "warnings": t["warnings"], "notes": t["notes"],
            "thin": not t["thin"].is_empty, "colours": [t["bg"]] + [c for _, c in t["layers"]], "from_svg": t["svg"]}


@router.get("/download/{bid}/{ext}")
def download(bid: str, ext: str, actor: Actor = Depends(get_actor)):
    if ext not in exporters.WRITERS or not bid.isalnum():
        raise HTTPException(404)
    bmeta = meta_for(bid, actor)
    from ..services import quarantine
    quarantine.guard(bid)                        # quarantined builds are not served
    from ..services import editproj, filestore
    editproj.ensure_exports(bid)
    p = store.dir(bid) / f"model.{ext}"
    if not p.exists():
        raise HTTPException(404, "unknown build")
    # object storage (when configured): refresh the bucket copy (idempotent — also heals builds
    # created before S3 was switched on), then redirect to a presigned URL with a TTL
    if filestore.enabled():
        filestore.put_build(bid, f"model.{ext}", p.read_bytes())
        return RedirectResponse(filestore.signed_url(filestore.artifact_key(bid, f"model.{ext}"), ttl_s=900),
                                status_code=303)
    if ext == "3mf" and editproj.ai_lineage(bmeta):          # F8: AI-made provenance travels with the file
        from fastapi.responses import Response
        from ..community import protect
        return Response(protect.tag_3mf(p.read_bytes(), {editproj.AI_3MF_KEY: "true"}), media_type="model/3mf",
                        headers={**NO_STORE, "Content-Disposition": f'attachment; filename="photo3d_{bid}.3mf"'})
    return FileResponse(p, filename=f"photo3d_{bid}.{ext}", headers=NO_STORE)


@router.post("/memorybox")
def memorybox_build(actor: Actor = Depends(get_actor), files: list[UploadFile] = File(None), photo_ack: bool = Form(False),
                    fmt: str = Form("preview"), style: str = Form("frame"), panel_mm: float = Form(80.0),
                    material: str = Form("filament"), clearance_mm: str = Form(""), hole_shape: str = Form("round"),
                    hole_preset: str = Form("tealight"), hole_w: str = Form(""), hole_d: str = Form(""),
                    notch_mm: str = Form(""), lid: bool = Form(True), base: bool = Form(True), light_h: str = Form(""),
                    base_notch_mm: str = Form(""), fill_sample: bool = Form(True), save: bool = Form(True)):
    """Memory box (4 lithophane sides round a light, on a light base). Up to 4 photos; empty sides use the sample photo.
    fmt=preview -> assembled preview + part list, saved as a build (title 'Memory box') so the export picker can
    download it (3MF = one object per part); fmt=3mf -> one 3MF with every part as its own object; fmt=zip -> STLs."""
    from fastapi.responses import Response
    from ..core import memorybox
    if fmt not in ("preview", "3mf", "zip"):
        raise HTTPException(400, "fmt must be preview, 3mf or zip")
    files = [f for f in (files or []) if getattr(f, "filename", "")]
    if len(files) > 4:
        raise HTTPException(400, "A memory box takes up to 4 photos, one per side.")
    if len(files) < 4 and not fill_sample:
        raise HTTPException(400, "A memory box needs 4 photos, one per side (or let the sample photo fill empty sides).")
    params = dict(style=style, panel_mm=panel_mm, material=material, clearance_mm=clearance_mm, hole_shape=hole_shape,
                  hole_preset=hole_preset, hole_w=hole_w, hole_d=hole_d, notch_mm=notch_mm, lid=lid, base=base,
                  light_h=light_h, base_notch_mm=base_notch_mm)
    try:
        memorybox.check_params(params)              # refuse bad options before any upload is read or rate-counted
    except ValueError as e:
        raise HTTPException(400, str(e))
    ims = []
    for up in files:
        data = up.file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "image too large (max 25 MB)")
        sample = imagesafe.is_membox_sample(data)   # ZEIM's own sample-box photo: no rate count, no permission tick needed
        if not sample:
            try:
                checked = uploadgate.gate(data, actor.sid, source="memorybox")
            except uploadgate.GateError as e:
                raise HTTPException(e.status, e.message)
            if getattr(checked, "scan_state", "off") == "unscanned":
                raise HTTPException(503, "The photo safety check is unavailable right now. Nothing was saved; please try again soon.")
        try:
            if not sample:
                imagesafe.check_ack(data, photo_ack)
            ims.append(imagesafe.sanitize(data)[2])
        except imagesafe.ImageRefused as e:
            raise HTTPException(400, str(e))
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(400, imagesafe.UNREADABLE)
    try:
        ims, sample_sides = memorybox.fill_slots(ims, fill_sample)
        pm, view = memorybox.build(ims, params)
    except ValueError as e:
        raise HTTPException(400, str(e))
    pm.info["sample_sides"] = view.info["sample_sides"] = [i + 1 for i, s in enumerate(sample_sides) if s]
    pm.info["shape"] = view.info["shape"] = "memorybox"
    if fmt == "3mf":
        return Response(exporters.to_3mf(pm, "memory-box"), media_type="model/3mf",
                        headers={"Content-Disposition": 'attachment; filename="memory-box.3mf"'})
    if fmt == "zip":
        return Response(memorybox.stl_zip(pm), media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="memory-box-stls.zip"'})
    if save:
        saved = memorybox_save(actor, pm, view, params, photo_ack, ims[0])
        if saved.get("id"):
            meta = store.get(saved["id"])
            return {**summary(meta), "params": {**params, "shape": "memorybox"},
                    "auto_notes": meta.get("auto_notes", []), "info": meta.get("info") or view.info,
                    "preview": preview_payload(view), "saved": True}
        return {"mode": "memorybox", "saved": False, "save_note": saved.get("save_note", ""),
                "params": {**params, "shape": "memorybox"}, "info": view.info,
                "preview": preview_payload(view), "stats": mesh_stats(view)}
    return {"mode": "memorybox", "saved": False, "params": {**params, "shape": "memorybox"},
            "info": view.info, "preview": preview_payload(view), "stats": mesh_stats(view)}


MEMORYBOX_TITLE = "Memory box"


def memorybox_save(actor: Actor, pm, view, params: dict, ack: bool, thumb_im=None) -> dict:
    """Keep the memory box as a build so the normal export picker (STL, 3MF, OBJ, ...) and file names work.
    model.* is the separate parts, laid out to print. assembled.3mf is the box together, for the viewer only.
    No photo is kept. 3MF keeps one object per part."""
    disk_guard()
    with store.lock:
        try:
            store.reserve(actor.sid, False)
        except HistoryFull:
            return {"saved": False, "save_note": "History is full, so this box was not kept. Downloads below still work."}
        bid = uuid.uuid4().hex[:12]
        d = store.dir(bid)
        d.mkdir(parents=True)
        for ext, fn in exporters.WRITERS.items():
            (d / f"model.{ext}").write_bytes(fn(pm) if ext != "3mf" else exporters.to_3mf(pm, MEMORYBOX_TITLE))
        (d / "assembled.3mf").write_bytes(exporters.to_3mf(view, MEMORYBOX_TITLE))
        th = (thumb_im or Image.new("RGB", (8, 8), (200, 200, 200))).convert("L")
        th.thumbnail((256, 256)); th.save(d / "thumb.png")
        from ..services import filestore
        if filestore.enabled():
            for ext in exporters.WRITERS:
                filestore.put_build(bid, f"model.{ext}", (d / f"model.{ext}").read_bytes())
            filestore.put_build(bid, "thumb.png", (d / "thumb.png").read_bytes(), "image/png")
        stats = mesh_stats(view)
        meta = {"id": bid, "mode": "memorybox", "beginner": False, "preset": None, "title": MEMORYBOX_TITLE,
                "source": None, "params": {**params, "shape": "memorybox"}, "auto_notes": [], "info": pm.info, "stats": stats,
                "owner_sid": actor.sid, "visibility": "private", "photo_ack": ack}
        store.save(meta)
        store.cache[bid] = pm
    return {"id": bid, "saved": True}
