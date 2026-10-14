"""Calibration wizard API (Zach 2026-10-13 queue).

GET  /api/calibration/plan?printer_id=&nozzle=&material=        four tests: steps, what to look for, PrusaSlicer keys
GET  /api/calibration/{test}.stl?printer_id=&nozzle=&material=   the generated test model (download / own slicer)
POST /api/calibration/{test}/slice                              slice it in ZEIM (same engine + downloads + layer preview
                                                                as /api/slice); the temperature tower gets its M104 bands
"""
from __future__ import annotations

import shutil
import uuid
from typing import Optional

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import Response

from app.api import slice as slice_api
from app.services import calibration as cal
from app.services import slice_engine as eng

router = APIRouter(prefix="/api/calibration", tags=["calibration"])


def _fail(e: cal.CalibrationError):
    raise HTTPException(status_code=e.status, detail={"code": "bad_calibration", "message": str(e)})


@router.get("/plan")
def get_plan(printer_id: Optional[str] = None, nozzle: Optional[str] = None, material: Optional[str] = None):
    try:
        return cal.plan(printer_id, nozzle, material)
    except cal.CalibrationError as e:
        _fail(e)


@router.get("/{test}.stl")
def get_model(test: str, printer_id: Optional[str] = None, nozzle: Optional[str] = None, material: Optional[str] = None):
    try:
        mesh = cal.model_for(test, printer_id, nozzle, material)
    except cal.CalibrationError as e:
        _fail(e)
    return Response(mesh.export(file_type="stl"), media_type="model/stl",
                    headers={"Content-Disposition": f'attachment; filename="zeim-calibration-{test}.stl"'})


@router.post("/{test}/slice")
def slice_test(test: str, printer_id: Optional[str] = Form(None), nozzle: Optional[str] = Form(None),
               material: Optional[str] = Form(None), ventilation_ok: bool = Form(False)):
    try:
        mesh = cal.model_for(test, printer_id, nozzle, material)
        plan = cal.plan(printer_id, nozzle, material)
    except cal.CalibrationError as e:
        _fail(e)
    try:
        prof, chosen = eng.profile_for(plan["printer_id"], plan["nozzle"], cal.slice_opts(test, plan["material"]))
    except eng.SliceError as e:
        slice_api._fail(e.status, e.code, e.message)
    warn = chosen.get("material_warning")
    if warn and not ventilation_ok:       # same rule as /api/slice: ABS / ASA / PC ask once before slicing
        raise HTTPException(status_code=409, detail={"code": "ventilation_check", "message": warn["title"] + ". " + warn["message"],
                                                     "warning": warn})
    root = slice_api.slices_root()
    slice_api._prune(root)
    slice_id = uuid.uuid4().hex
    work = root / slice_id
    work.mkdir(parents=True, exist_ok=True)
    if not slice_api._slots.acquire(blocking=False):
        shutil.rmtree(work, ignore_errors=True)
        slice_api._fail(503, "busy", "The slicer is busy right now. Please try again in a minute.")
    try:
        (work / "model.stl").write_bytes(mesh.export(file_type="stl"))
        res = eng.slice_stl(work / "model.stl", prof, work / "model.gcode")
        bands = None
        if test == "temp_tower":
            bands = plan["tests"][1]["values"]["bands_c"]
            cal.add_temperature_bands(work / "model.gcode", bands)
    except eng.SliceError as e:
        shutil.rmtree(work, ignore_errors=True)
        slice_api._fail(e.status, e.code, e.message)
    finally:
        slice_api._slots.release()
    return {"slice_id": slice_id, "test": test, "printer_id": prof.id, "printer": prof.name, "nozzle": prof.nozzle,
            "material": chosen["material"], "settings": chosen, "temperature_bands_c": bands,
            "print_time_seconds": res.print_time_seconds, "print_time_human": eng.humanize(res.print_time_seconds),
            "filament_grams": res.filament_grams, "grams_note": chosen.get("grams_note") or "",
            "temp_notes": chosen.get("temp_notes") or [], "estimate_note": cal.ESTIMATE,
            "downloads": {"gcode": f"/api/slice/{slice_id}/gcode", "stl": f"/api/slice/{slice_id}/model.stl",
                          "3mf": f"/api/slice/{slice_id}/model.3mf", "layers": f"/api/slice/{slice_id}/layers"}}
