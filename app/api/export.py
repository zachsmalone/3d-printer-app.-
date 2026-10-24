"""Universal export API endpoints: one format picker ('Export for my printer'), readable file names, rename."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.builds import meta_for
from app.community.identity import Actor, get_actor
from app.services import filenames as fnames
from app.services import print_setup as ps
from app.services import universal_export as ue
from app.services.history import store

router = APIRouter(prefix="/api/export", tags=["export"])
FMT_PATTERN = "^(" + "|".join(ue.FORMATS) + ")$"


@router.get("/hints")
def get_slicer_hints(printer_id: str = Query("", description="Optional printer ID for official slicer matching")):
    hints = ue.get_open_in_hints(printer_id or None)
    return {"hints": hints, "count": len(hints)}


@router.get("/formats")
def get_formats():
    """Every format of the export picker, each with a one-line description. STEP: only with a true solid (never here)."""
    return ue.formats_public()


def _pid(actor: Actor, printer_id: str) -> str:
    pref_pid = printer_id
    if not pref_pid and actor.user and actor.user.get("printer", {}).get("printer_id"):
        pref_pid = actor.user["printer"]["printer_id"]
    try:
        pref_pid, _ = ps.resolve(pref_pid or None)
    except ps.SetupError:
        pref_pid, _ = ps.resolve()
    return pref_pid


def _noz(nozzle: str) -> Optional[float]:
    try:
        n = float(nozzle)
        return n if 0.1 <= n <= 2 else None
    except (TypeError, ValueError):
        return None


@router.get("/{bid}")
def get_export_info(
    bid: str,
    printer_id: str = Query("", description="Optional printer ID (defaults to account setting)"),
    nozzle: str = Query(""),
    actor: Actor = Depends(get_actor),
):
    """Metadata, URLs and file names for the export picker."""
    meta = meta_for(bid, actor, owner_only=True)
    pref_pid = _pid(actor, printer_id)
    p = ps.printer_public(pref_pid)
    pref = (actor.user or {}).get("printer") or {} if actor.user else {}
    noz = _noz(nozzle) or (pref.get("nozzle") if pref.get("printer_id") == pref_pid else None)
    names = {k: ue.build_file_name(meta, pref_pid, k, nozzle=noz) for k in ue.FORMATS}
    default_stem = fnames.default_stem(*ue.name_parts(meta, pref_pid, noz))
    return {
        "build_id": bid,
        "title": meta.get("title", ""),
        "printer": {
            "id": pref_pid,
            "name": p["name"],
            "bed_mm": p["bed_mm"],
            "official_slicer": p.get("official_slicer"),
            "official_slicer_url": p.get("official_slicer_url"),
        },
        "name": fnames.safe_name(meta.get("file_name")) if meta.get("file_name") else default_stem,
        "default_name": default_stem,
        "filename": names["3mf"],
        "filename_fallback": names["stl"],
        "filenames": names,
        "downloads": {k: f"/api/export/{bid}/download?format={k}&printer_id={pref_pid}" for k in ue.FORMATS},
        **ue.formats_public(),
        "open_in_hints": ue.get_open_in_hints(pref_pid),
        "colour_count": _colour_count(bid),
        "print_presets": _presets(meta, p),
        "parts": _parts(bid, meta),
    }


def _presets(meta: dict, p: dict) -> list:
    """Print presets the picker can add to a 3MF of this build (lithophanes only, for now Bambu)."""
    if meta.get("mode") != "lithophane":
        return []
    from app.services import litho_preset as lp
    return [{"id": lp.PRESET_ID, "label": "Add lithophane print settings for Bambu Studio",
             "desc": "0.12 mm layers, 100% infill, slower outer wall" + (", 5 mm brim" if (meta.get("params") or {}).get("shape") in lp.UPRIGHT else "") + ".",
             "note": lp.NOTE, "suggested": str(p.get("brand", "")).startswith("Bambu") or str(p.get("id", "")).startswith("bambu_")}]


def _colour_count(bid: str) -> int:
    """Distinct body colours of the build (0/1 = one material). The slot picker offers multi-slot only above 1."""
    try:
        from app.api.builds import load_model
        from app.services import filament_slots as fs
        return len(fs.model_colours(load_model(bid)))
    except Exception:
        return 0


_PART_LABELS = {"lithophane": "Lithophane panel", "stand": "Display stand",
               "stand_cap_a": "Stand end cap A", "stand_cap_b": "Stand end cap B"}


def _parts(bid: str, meta: dict) -> list:
    """Separate download choices when a lithophane has a panel + stand (or other named bodies)."""
    if meta.get("mode") != "lithophane":
        return []
    try:
        from app.api.builds import load_model
        names = [b.name for b in load_model(bid).bodies]
    except Exception:
        return []
    if len(names) < 2:
        return []
    out = [{"id": "", "label": "Both (one file)"}]
    for n in names:
        out.append({"id": n, "label": _PART_LABELS.get(n, n)})
    return out


@router.put("/{bid}/name")
def rename(bid: str, body: dict, actor: Actor = Depends(get_actor)):
    """One-tap rename: the file name used for every export and for 'Back up all'. Empty = back to the default."""
    meta = meta_for(bid, actor, owner_only=True)
    raw = str(body.get("name") or "").strip()
    if len(raw) > 400:
        raise HTTPException(400, "That name is too long.")
    if raw:
        from app.community import safety
        if safety.scan(raw):
            raise HTTPException(400, "Please pick a different name.")
        for ext in ue.FORMATS:
            raw = fnames.strip_ext(raw, ext)
        meta["file_name"] = fnames.safe_name(raw)
    else:
        meta.pop("file_name", None)
    store.save(meta)
    return {"name": meta.get("file_name") or fnames.default_stem(*ue.name_parts(meta, _pid(actor, ""))),
            "custom": bool(meta.get("file_name"))}


@router.get("/{bid}/download")
def download_export(
    bid: str,
    format: str = Query("3mf", pattern=FMT_PATTERN),
    printer_id: str = Query("", description="Optional printer ID (defaults to account setting)"),
    nozzle: str = Query(""),
    name: str = Query("", max_length=400),
    slots: str = Query("", max_length=60, description="Filament slots to use, e.g. '2' or '1,3' (default Slot 1)"),
    preset: str = Query("", pattern="^(|bambu_litho)$", description="bambu_litho: add lithophane print settings for Bambu Studio (3MF, lithophanes)"),
    part: str = Query("", max_length=40, description="Optional body name: lithophane | stand (empty = whole model)"),
    actor: Actor = Depends(get_actor),
):
    """Download in the picked format, sized and named for the printer (3MF falls back to STL if it cannot be made)."""
    from ..services import quarantine
    quarantine.guard(bid)                        # quarantined builds are not served
    pref_pid = _pid(actor, printer_id)
    from ..services import filament_slots as fs
    try:
        picked = fs.parse_slots(slots or None)
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        data, filename, ext, mime, info = ue.export_build_for_printer(
            bid, actor, printer_id=pref_pid, force_format=format, name=name or None, nozzle=_noz(nozzle),
            slots=picked, preset=preset, part=part)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Could not export model: {e}")

    return Response(
        content=data,
        media_type=mime,
        headers={
            "Content-Disposition": fnames.disposition(filename),
            "Cache-Control": "no-store",
            "X-Export-Printer": info["printer_id"],
            "X-Export-Format": ext,
            "X-Export-Slots": ",".join(map(str, info.get("slots") or [])),
            "X-Export-Preset": info.get("preset") or "",
            "X-Export-Part": info.get("part") or "",
        },
    )


me_router = APIRouter(prefix="/api/me", tags=["export"])


@me_router.get("/backup.zip")
def backup_all(format: str = Query("3mf", pattern=FMT_PATTERN), actor: Actor = Depends(get_actor)):
    """'Back up all': one zip of every saved project of this person, each model under its chosen file name,
    plus a small readable index. Nothing leaves the server except to this person."""
    import io, json, zipfile
    from ..services import quarantine
    items = store.list(actor.sid)
    buf, used, index = io.BytesIO(), set(), []
    pid = _pid(actor, "")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for m in items:
            try:
                quarantine.guard(m["id"])
                data, fname, ext, _mime, _info = ue.export_build_for_printer(m["id"], actor, printer_id=pid, force_format=format)
            except Exception:
                index.append({"title": m.get("title", ""), "created": m.get("created"), "file": None,
                              "note": "Could not be exported (expired or unavailable)."})
                continue
            stem, n = fname[: -len(ext) - 1], 2
            while fname.lower() in used:
                fname = f"{stem} ({n}).{ext}"; n += 1
            used.add(fname.lower())
            z.writestr(fname, data)
            index.append({"title": m.get("title", ""), "created": m.get("created"), "mode": m.get("mode"), "file": fname,
                          "starred": bool(m.get("favorite"))})
        z.writestr("ZEIM backup - contents.json", json.dumps({"projects": index, "format": format}, indent=2, ensure_ascii=False))
    import time
    zname = f"ZEIM backup {time.strftime('%Y-%m-%d')}.zip"
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": fnames.disposition(zname), "Cache-Control": "no-store",
                             "X-Backup-Count": str(sum(1 for i in index if i["file"]))})
