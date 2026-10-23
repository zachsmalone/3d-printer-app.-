"""POST /api/slice  (upload an STL or give a model id)  ->  G-code + print time + filament grams."""
from __future__ import annotations

import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response

from app import config
from app.community.identity import Actor, get_actor
from app.services import slice_engine as eng

router = APIRouter(prefix="/api/slice", tags=["slice"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
KEEP_SECONDS = 24 * 3600
_MODEL_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SLICE_ID = re.compile(r"^[0-9a-f]{32}$")
_slots = threading.BoundedSemaphore(int(os.environ.get("PHOTO3D_SLICE_CONCURRENCY", "2")))


def _fail(status: int, code: str, message: str):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


def slices_root() -> Path:
    # Under DATA, NOT the builds folder: build clean-up sweeps OUT sub-folders.
    return config.DATA / "slices"


def resolve_model(model_id: str, actor: Actor) -> Path:
    """STL of an existing build the actor OWNS (store.dir(<id>)/model.stl, same as /files/<id>/model.stl).

    Owner-only, like POST /api/slice/{bid} and /api/print/{bid}/links: other people's builds (even public ones) are 404.
    """
    from app.api.builds import meta_for
    from app.services import editproj
    from app.services.history import store
    if not _MODEL_ID.match(model_id) or not model_id.isalnum():
        _fail(400, "bad_model_id", "That model id isn't valid.")
    try:
        meta_for(model_id, actor, owner_only=True)
    except HTTPException:
        _fail(404, "model_not_found", "We couldn't find that model. It may have expired. Please rebuild it.")
    editproj.ensure_exports(model_id)  # edit-workspace builds write model.stl lazily
    stl = store.dir(model_id) / "model.stl"
    if not stl.is_file():
        _fail(404, "model_not_found", "That build has no STL file to slice.")
    return stl


def _prune(root: Path) -> None:
    if not root.is_dir():
        return
    cutoff = time.time() - KEEP_SECONDS
    for d in root.iterdir():
        try:
            if d.is_dir() and _SLICE_ID.match(d.name) and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


@router.get("/profiles")
def list_profiles():
    return {"default": eng.DEFAULT_PROFILE, "profiles": [p.public() for p in eng.PROFILES.values()]}


@router.post("")
def slice_model(
    file: Optional[UploadFile] = File(None),
    model_id: Optional[str] = Form(None),
    profile: str = Form(eng.DEFAULT_PROFILE),
    printer_id: Optional[str] = Form(None),
    nozzle: Optional[str] = Form(None),
    preset: Optional[str] = Form(None),
    layer_height: Optional[str] = Form(None),
    walls: Optional[str] = Form(None),
    top_bottom: Optional[str] = Form(None),
    infill: Optional[str] = Form(None),
    infill_pattern: Optional[str] = Form(None),
    supports: Optional[str] = Form(None),
    brim: Optional[str] = Form(None),
    speed: Optional[str] = Form(None),
    nozzle_temp: Optional[str] = Form(None),
    bed_temp: Optional[str] = Form(None),
    material: Optional[str] = Form(None),
    scale_to_fit: bool = Form(False),
    fit: bool = Form(False),
    ventilation_ok: bool = Form(False),
    support_paint: Optional[str] = Form(None),
    slots: Optional[str] = Form(None),
    actor: Actor = Depends(get_actor),
):
    from app.services import filament_slots as fslots
    try:
        slot_plan = fslots.plan([], fslots.parse_slots(slots))   # the slicer gets one merged STL: one material, first picked slot
    except ValueError as e:
        _fail(400, "bad_slots", str(e))
    plate_objs, skipped = None, []
    if bool(file) == bool(model_id):
        _fail(400, "bad_request", "Send either an STL file or a model id (not both, not neither).")
    opts = {"preset": preset, "layer_height": layer_height, "walls": walls, "top_bottom": top_bottom, "infill": infill,
            "infill_pattern": infill_pattern, "supports": supports, "brim": brim, "speed": speed,
            "nozzle_temp": nozzle_temp, "bed_temp": bed_temp, "material": material}
    try:
        eng.get_profile(profile)                     # legacy field: still validated (only creality_k1)
        prof, chosen = eng.profile_for(printer_id or profile, nozzle, opts)
    except eng.SliceError as e:
        _fail(e.status, e.code, e.message)
    warn = chosen.get("material_warning")
    if warn and not ventilation_ok:
        # Warn, then allow: ABS / ASA / PC (significant fumes) need the maker to read the ventilation + enclosure note once.
        # Resend with ventilation_ok=true to slice. Nothing is written before this point.
        raise HTTPException(status_code=409, detail={"code": "ventilation_check", "message": warn["title"] + ". " + warn["message"],
                                                     "warning": warn})

    root = slices_root()
    _prune(root)
    slice_id = uuid.uuid4().hex
    work = root / slice_id
    work.mkdir(parents=True, exist_ok=True)

    if not _slots.acquire(blocking=False):
        shutil.rmtree(work, ignore_errors=True)
        _fail(503, "busy", "The slicer is busy right now. Please try again in a minute.")
    try:
        if file is not None:
            stl = work / "input.stl"
            data = file.file.read(MAX_UPLOAD_BYTES + 1)
            if len(data) > MAX_UPLOAD_BYTES:
                _fail(413, "too_large", "That file is over the 50 MB limit.")
            from app.core import meshedit
            ext = meshedit.guess_model_ext(file.filename or "", data, file.content_type or "")
            if not ext:
                _fail(400, "bad_model", "Please upload an .stl, .obj or .3mf file.")
            if ext == "stl":
                stl.write_bytes(data)
            else:                                   # 3MF / OBJ: parse (units → mm) and hand the slicer a binary STL
                if meshedit.sniff(data, ext):
                    _fail(400, "bad_model", meshedit.sniff(data, ext))
                try:
                    mesh, _w = meshedit.load_mesh(data, ext)
                except meshedit.OpError as e:
                    _fail(400, "bad_model", str(e))
                stl.write_bytes(mesh.export(file_type="stl"))
        else:
            shutil.copyfile(resolve_model(model_id, actor), work / "input.stl")  # type: ignore[arg-type]
            stl = work / "input.stl"
            plate_objs, skipped = plate_on_bed(model_id, prof)
            if skipped and plate_objs:              # warnings never block: slice what's on the bed, name the rest
                import trimesh as _tm
                stl.write_bytes(_tm.util.concatenate(plate_objs).export(file_type="stl"))
        fitted = fit_to_printer(stl, work / "model.stl", prof, scale_to_fit or fit, info=(scaling := {}))
        paint_info = None
        model_for_engine = work / "model.stl"
        if support_paint:
            from app.services import support_paint as spaint
            import trimesh
            try:
                strokes = spaint.parse_strokes(support_paint)
            except spaint.PaintError as e:
                _fail(400, "bad_paint", str(e))
            if strokes:
                mesh = trimesh.load(str(work / "model.stl"), force="mesh")
                paint_info = spaint.write_paint_3mf(mesh, strokes, work / "model_paint.3mf")
                model_for_engine = work / "model_paint.3mf"
                # Painted "need support" areas require supports on; leave the maker's Auto/Everywhere choice.
                if paint_info["enforcers"] and chosen.get("supports") == "off":
                    opts = {**opts, "supports": "auto"}
                    try:
                        prof, chosen = eng.profile_for(printer_id or profile, nozzle, opts)
                    except eng.SliceError as e:
                        _fail(e.status, e.code, e.message)
                    paint_info = {**paint_info, "supports_forced": "auto",
                                  "supports_note": "You painted areas that need supports, so ZEIM turned Supports on (Auto). You can still pick Everywhere."}
        parts = None
        if model_id and model_for_engine == work / "model.stl" and len(plate_objs or []) >= 2:
            parts = plate_parts(plate_objs, work, scaling.get("scale", 1.0))
        res = eng.slice_model_path(model_for_engine, prof, work / "model.gcode",
                                   bounds_stl=work / "model.stl", parts=parts)
    except eng.SliceError as e:
        shutil.rmtree(work, ignore_errors=True)
        _fail(e.status, e.code, e.message)
    except HTTPException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    finally:
        _slots.release()
        (work / "input.stl").unlink(missing_ok=True)
    _g = work / "model.gcode"
    _g.write_text(fslots.gcode_header(slot_plan) + _g.read_text(errors="ignore"))
    (work / "slots.json").write_text(__import__("json").dumps(slot_plan))
    from app.services import slicer as _sl, willprint
    stats = _sl.parse_stats((work / "model.gcode").read_text(errors="ignore"))
    try:
        badge = willprint.check_file(work / "model.stl", prof.id, prof.nozzle, slices_ok=True, filament_g=res.filament_grams)
    except Exception:
        badge = None
    from app.services import gcode_hints, gcode_pause
    hints = gcode_hints.markers(work / "model.stl", chosen.get("supports") or "off", badge)

    return {
        "slice_id": slice_id,
        "profile": prof.id,
        "plate_objects": len(parts) if parts else 1,
        "skipped_objects": skipped,
        "skipped_note": (f"Skipped {len(skipped)} object{'s' * (len(skipped) > 1)} off the bed: {', '.join(skipped)}. "
                         "Only the objects on the bed were sliced. Split them onto another plate to print them too.") if skipped else "",
        "gcode_url": f"/api/slice/{slice_id}/gcode",
        "print_time_seconds": res.print_time_seconds,
        "print_time_human": eng.humanize(res.print_time_seconds),
        "filament_grams": res.filament_grams,
        "filament_density_g_cm3": chosen.get("filament_density"), "grams_note": chosen.get("grams_note") or "",
        "model_size_mm": [round(v, 2) for v in res.size_mm],
        "printer_id": prof.id, "printer": prof.name, "nozzle": prof.nozzle, "settings": chosen,
        "filament_mm": float(stats["filament_mm"]) if stats.get("filament_mm") else None,
        "scaled_pct": fitted, "scaling": scaling, "will_print": badge,
        "material_warning": chosen.get("material_warning"), "temp_notes": chosen.get("temp_notes") or [],
        "support_paint": paint_info, "slots": slot_plan["slots"], "slot_notes": slot_plan["notes"],
        "firmware": gcode_pause.firmware_for(prof.id), "problem_markers": hints,
        "downloads": {"gcode": f"/api/slice/{slice_id}/gcode", "stl": f"/api/slice/{slice_id}/model.stl",
                      "3mf": f"/api/slice/{slice_id}/model.3mf", "layers": f"/api/slice/{slice_id}/layers"},
    }


FIT_MARGIN_MM = 2.0      # kept clear on each side in X/Y and above the model in Z
MIN_FIT_SCALE = 0.10     # shrinking further than this is almost always a units mix-up


def fit_scale(extents, limits, margin: float = FIT_MARGIN_MM) -> float:
    """Uniform factor (<= 1) that fits `extents` in `limits` with `margin` mm to spare; 1.0 if it already fits."""
    if all(d <= l + eng.FIT_TOLERANCE_MM for d, l in zip(extents, limits)):
        return 1.0
    usable = (limits[0] - 2 * margin, limits[1] - 2 * margin, limits[2] - margin)
    return min(1.0, min(u / d for u, d in zip(usable, extents) if d > 0))


def plate_on_bed(model_id: str, prof) -> tuple[list | None, list[str]]:
    """Plate-editor project -> (visible objects on the chosen printer's bed, names of visible objects that are off it).
    Bed is centred on (0, 0) like the plate editor. Not a plate / nothing on the bed -> (None or objs, [])."""
    from app.core import plate
    from app.services import editproj
    from app.services.history import store
    try:
        meta = store.get(model_id)
        if not meta or meta.get("kind") != "edit":
            return None, []
        m = editproj.mesh_at(model_id, meta)
        L = editproj.layout_at(meta, m)
        if not L:
            return None, []
        hx, hy, tol = prof.bed_x / 2, prof.bed_y / 2, 0.5
        on, off = [], []
        for i, (o, h) in enumerate(zip(plate.objects(m, L), L["hidden"])):
            if h:
                continue
            lo, hi = o.bounds
            inside = lo[0] >= -hx - tol and hi[0] <= hx + tol and lo[1] >= -hy - tol and hi[1] <= hy + tol
            (on if inside else off).append((i, o))
        if not on:                          # nothing on the bed: slice as before (the bed-fit check explains)
            return [o for _, o in off], []
        return [o for _, o in on], [f"Object {i + 1}" for i, _ in off]
    except Exception:
        return None, []


def plate_parts(objs: list, work: Path, scale: float = 1.0) -> list[Path] | None:
    """2+ plate objects -> one STL per object, placed exactly where the whole (already fitted) model.stl puts them,
    so PrusaSlicer gets every object of the plate as separate objects."""
    import trimesh
    try:
        lo_o = np.min([o.bounds[0] for o in objs], axis=0)
        lo_m = trimesh.load(str(work / "model.stl"), force="mesh").bounds[0]
        t = lo_m - scale * lo_o
        out = []
        for k, o in enumerate(objs):
            o = o.copy(); o.apply_scale(scale); o.apply_translation(t)
            f = work / f"part_{k + 1:02d}.stl"
            f.write_bytes(o.export(file_type="stl"))
            out.append(f)
        return out
    except Exception:                      # never block a slice: fall back to the single merged STL
        return None


def fit_to_printer(src: Path, dst: Path, prof, scale: bool, info: Optional[dict] = None):
    """Copy the model, sitting on z=0 and centred on the chosen printer's bed; shrunk to fit when asked
    (never enlarged). Returns the scale percent applied (None = unchanged) and fills `info` with the details.
    Without `scale`, a too-big model is refused by slice_stl."""
    import trimesh
    info = {} if info is None else info
    eng.stl_bounds(src)                                    # friendly "bad_model" for garbage before trimesh sees it
    try:
        mesh = trimesh.load(str(src), file_type="stl", force="mesh")
        if mesh.bounds is None:
            raise ValueError
    except Exception:
        raise eng.SliceError("bad_model", "That file doesn't look like a valid STL model. Please export it as an STL and try again.", 400)
    pct = None
    info.update(scaled=False, scale=1.0, margin_mm=FIT_MARGIN_MM,
                original_size_mm=[round(float(v), 2) for v in mesh.extents] if len(mesh.vertices) else None)
    if scale and len(mesh.vertices):
        limits = (prof.bed_x, prof.bed_y, prof.max_z)
        f = fit_scale(mesh.extents, limits)
        if f < MIN_FIT_SCALE:
            x, y, z = mesh.extents
            raise eng.SliceError(
                "cannot_fit",
                f"This model would have to shrink to {f * 100:.0f}% to fit the printer, which is probably a "
                f"units mix-up (it is {x:.0f} x {y:.0f} x {z:.0f} mm). Please check the size in the Edit tab.", 422)
        if f < 1:
            mesh.apply_scale(f)
            pct = round(f * 100, 1)
            info.update(scaled=True, scale=round(float(f), 4), percent=pct)
    lo, hi = mesh.bounds
    mesh.apply_translation([prof.bed_x / 2 - (lo[0] + hi[0]) / 2, prof.bed_y / 2 - (lo[1] + hi[1]) / 2, -lo[2]])
    dst.write_bytes(mesh.export(file_type="stl"))
    return pct


@router.get("/{slice_id}/model.{ext}")
def download_model(slice_id: str, ext: str):
    """The model exactly as sliced: sized for the chosen printer, placed on its bed. 3MF is built from it on demand."""
    if not _SLICE_ID.match(slice_id) or ext not in ("stl", "3mf"):
        _fail(404, "not_found", "File not found.")
    stl = slices_root() / slice_id / "model.stl"
    if not stl.is_file():
        _fail(404, "not_found", "That file has expired. Please slice again.")
    if ext == "stl":
        return FileResponse(stl, media_type="model/stl", filename="zeim-model.stl")
    out = stl.with_suffix(".3mf")
    if not out.is_file():
        import trimesh
        import json as _j
        from app.services import filament_slots as fslots
        sj = stl.parent / "slots.json"
        plan = _j.loads(sj.read_text()) if sj.is_file() else fslots.plan([], None)
        out.write_bytes(fslots.annotate_3mf(trimesh.load(str(stl), force="mesh").export(file_type="3mf"), plan))
    return FileResponse(out, media_type="model/3mf", filename="zeim-model.3mf")


@router.get("/{slice_id}/gcode")
def download_gcode(slice_id: str):
    # The id is an unguessable uuid4 (acts as a capability); format-checked against path tricks.
    if not _SLICE_ID.match(slice_id):
        _fail(404, "not_found", "G-code not found.")
    path = slices_root() / slice_id / "model.gcode"
    if not path.is_file():
        _fail(404, "not_found", "That G-code has expired. Please slice again.")
    return FileResponse(path, media_type="text/plain", filename="zeim-model.gcode")


@router.get("/{slice_id}/gcode-paused")
def download_gcode_paused(slice_id: str, layers: str = "", cmd: str = ""):
    """A NEW file with a pause at the start of each listed layer (1-based, same numbering as the preview).
    The original model.gcode is never touched."""
    from app.services import gcode_pause
    import hashlib
    if not _SLICE_ID.match(slice_id):
        _fail(404, "not_found", "G-code not found.")
    path = slices_root() / slice_id / "model.gcode"
    if not path.is_file():
        _fail(404, "not_found", "That G-code has expired. Please slice again.")
    if cmd not in gcode_pause.COMMANDS:
        _fail(422, "bad_command", "Pick a pause command: " + ", ".join(gcode_pause.COMMANDS))
    try:
        want = sorted({int(x) for x in layers.split(",") if x.strip()})
    except ValueError:
        want = []
    if not want or len(want) > 50 or want[0] < 1 or want[-1] > 1_000_000:
        _fail(422, "bad_layers", "Give 1 to 50 layer numbers, like layers=12,40.")
    key = hashlib.sha1(f"{cmd}|{want}".encode()).hexdigest()[:12]
    out = path.with_name(f"paused-{key}.gcode")
    if not out.is_file():
        tmp = out.with_name(f"{out.name}.{uuid.uuid4().hex}.tmp")
        gcode_pause.insert_pauses(path, tmp, want, cmd)
        tmp.replace(out)
    return FileResponse(out, media_type="text/plain", filename="zeim-model-with-pauses.gcode")


@router.get("/{slice_id}/layers")
def layer_preview(slice_id: str, request: Request):
    """Layer-by-layer preview data read from this slice's G-code (same unguessable-id capability as /gcode).
    Parsed once, cached gzipped next to the G-code (removed with it after 24 h)."""
    import gzip
    import json
    from app.services import gcode_layers
    if not _SLICE_ID.match(slice_id):
        _fail(404, "not_found", "Layer preview not found.")
    work = slices_root() / slice_id
    gc, cache = work / "model.gcode", work / "layers.json.gz"
    if not gc.is_file():
        _fail(404, "not_found", "That slice has expired. Please slice again.")
    if not cache.is_file():
        try:
            data = gcode_layers.parse(gc.read_text(errors="ignore"))
        except gcode_layers.GcodeError as e:
            _fail(422, "no_layers", str(e))
        tmp = work / f"layers.{uuid.uuid4().hex}.tmp"
        tmp.write_bytes(gzip.compress(json.dumps(data, separators=(",", ":")).encode(), 6))
        tmp.replace(cache)
    body = cache.read_bytes()
    h = {"Vary": "Accept-Encoding", "Cache-Control": "no-store"}
    if "gzip" in request.headers.get("accept-encoding", "").lower():
        return Response(body, media_type="application/json", headers={**h, "Content-Encoding": "gzip"})
    return Response(gzip.decompress(body), media_type="application/json", headers=h)
