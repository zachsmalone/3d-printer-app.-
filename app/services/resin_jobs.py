"""One background LUMEN slice at a time, with progress and cancel.

The request thread only records the job. Raster and encode run on a worker so the
page can poll. A second slice waits, then reports busy instead of starting a third.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

import trimesh

from app import config
from app.core import resin_slice
from app.services import mslicer_engine

_lock = threading.Lock()
_cancel: dict[str, threading.Event] = {}
_sem = threading.BoundedSemaphore(1)


def _dir() -> Path:
    d = config.DATA / "resin"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(job_id: str) -> Path:
    return _dir() / f"job{job_id}.json"


def _read(job_id: str) -> dict | None:
    try:
        return json.loads(_path(job_id).read_text())
    except (OSError, ValueError):
        return None


def _write(job: dict) -> None:
    path = _path(job["job_id"])
    path.write_text(json.dumps(job))


def public(job: dict) -> dict:
    report = job.get("report") or {}
    out = {
        "job_id": job["job_id"],
        "status": job["status"],
        "progress": job.get("progress", 0),
        "phase": job.get("phase") or "",
        "layers": job.get("layers"),
        "done_layers": job.get("done_layers") or 0,
        "error": job.get("error") or "",
        "download": job.get("download"),
        "plate_id": job.get("plate_id"),
        "name": job.get("name") or "torchc0",
        "format": job.get("format") or "lumen",
    }
    if report:
        fmt = report.get("format") or out["format"]
        out["report"] = {
            "format": fmt,
            "extension": report.get("extension") or f".{fmt}",
            "layers": report.get("layers"),
            "width_px": report.get("width_px"),
            "height_px": report.get("height_px"),
            "layer_height_um": report.get("layer_height_um"),
            "normal_exposure_ms": report.get("normal_exposure_ms"),
            "bottom_exposure_ms": report.get("bottom_exposure_ms"),
            "bottom_layer_count": report.get("bottom_layer_count"),
            "lift_slow_distance_um": report.get("lift_slow_distance_um"),
            "lift_slow_speed_um_min": report.get("lift_slow_speed_um_min"),
            "anti_aliasing": report.get("anti_aliasing"),
            "aa_level": report.get("aa_level"),
            "plate_name": report.get("plate_name"),
            "native_format": report.get("native_format"),
            "native_format_written": bool(report.get("native_format_written")),
            "engine": report.get("engine") or "lumen-format",
            "ctb_container": report.get("ctb_container") or "",
            "file_magic": report.get("file_magic") or "",
            "hardware_tested": False,
            "mirror_applied": False,
            "mirror_x": bool(report.get("mirror_x")),
            "mirror_y": bool(report.get("mirror_y")),
            "bytes": report.get("bytes"),
            "seconds_raster": report.get("seconds_raster"),
            "note": report.get("note"),
            "lit": report.get("lit"),
        }
    return out


def start(rid: str, sid: str, plate_id: str, *, aa: bool, aa_level: int, fmt: str) -> dict:
    kind = mslicer_engine.output_format(fmt)
    plate = resin_slice.plate_by_id(plate_id)
    d = _dir()
    try:
        info = json.loads((d / f"{rid}.json").read_text())
    except (OSError, ValueError):
        raise resin_slice.ResinSliceError("That prepared model has expired. Prepare it again.")
    if info.get("sid") != sid or not (d / f"{rid}.stl").is_file() or not (d / f"{rid}.settings.json").is_file():
        raise resin_slice.ResinSliceError("That prepared model has expired. Prepare it again.")
    printer = info.get("printer")
    resin_slice.refuse_for_printer(plate, kind, printer if isinstance(printer, dict) else None)
    if kind != "lumen":
        mslicer_engine.require_format_plate(plate, kind)
    job_id = uuid.uuid4().hex
    job = {
        "job_id": job_id, "rid": rid, "sid": sid, "name": info.get("name") or "torchc0",
        "status": "queued", "progress": 0,
        "phase": "queued", "layers": None, "done_layers": 0, "error": "", "download": None,
        "plate_id": plate_id, "aa": aa, "aa_level": aa_level, "format": kind, "created": time.time(),
        "placed": bool(printer),
    }
    cancel = threading.Event()
    with _lock:
        _cancel[job_id] = cancel
        _write(job)
    threading.Thread(target=_run, args=(job_id, plate), name=f"lumen-{job_id[:8]}", daemon=True).start()
    return public(job)


def get(job_id: str, sid: str) -> dict:
    job = _owned(job_id, sid)
    return public(job)


def cancel(job_id: str, sid: str) -> dict:
    _owned(job_id, sid)
    with _lock:
        ev = _cancel.get(job_id)
        if ev is not None:
            ev.set()
        job = _read(job_id)
    if job and job["status"] in ("queued", "running"):
        job["phase"] = "cancel"
        _write(job)
    return public(_read(job_id) or job)


def file_for(job_id: str, sid: str, kind: str, index: int | None = None) -> Path:
    job = _owned(job_id, sid)
    if job["status"] != "done":
        raise resin_slice.ResinSliceError("That slice is not ready.")
    d = _dir()
    if kind == "lumen":
        path = d / f"job{job_id}.lumen"
    elif kind in ("goo", "ctb", "nanodlp"):
        path = d / f"job{job_id}.{kind}"
    elif kind == "png":
        path = d / f"job{job_id}" / f"{index:04d}.png"
    else:
        raise resin_slice.ResinSliceError("Unknown slice file.")
    if not path.is_file():
        raise resin_slice.ResinSliceError("That slice file has expired.")
    return path


def _owned(job_id: str, sid: str) -> dict:
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise resin_slice.ResinSliceError("Unknown slice.")
    job = _read(job_id)
    if not job or job.get("sid") != sid:
        raise resin_slice.ResinSliceError("Unknown slice.")
    return job


def _run(job_id: str, plate: dict) -> None:
    job = _read(job_id)
    if job is None:
        return
    if not _sem.acquire(timeout=resin_slice_wait()):
        _fail(job, "TorchC0 is busy. Try the slice again in a moment.")
        return
    try:
        with _lock:
            ev = _cancel.get(job_id)
        if ev is not None and ev.is_set():
            _finish_cancel(job)
            return
        d = _dir()
        settings = json.loads((d / f"{job['rid']}.settings.json").read_text())["settings"]
        stl_path = d / f"{job['rid']}.stl"
        mesh = trimesh.load(str(stl_path), file_type="stl", force="mesh")
        kind = job.get("format") or "lumen"
        thumb = d / f"job{job_id}"
        thumb.mkdir(exist_ok=True)
        out = d / f"job{job_id}.{kind if kind != 'lumen' else 'lumen'}"
        job["status"] = "running"
        job["phase"] = "raster"
        _write(job)
        last = 0.0

        def progress(done, total, phase):
            nonlocal last
            now = time.monotonic()
            if done != total and now - last < 0.15:
                return
            last = now
            job["layers"] = total
            job["done_layers"] = done
            job["progress"] = round(done / total, 4) if total else 0
            job["phase"] = phase
            _write(job)

        if kind == "lumen":
            report = resin_slice.slice_mesh(
                mesh, settings, plate, out, aa=bool(job["aa"]), aa_level=int(job["aa_level"]),
                thumb_dir=thumb, cancel=ev, progress=progress,
            )
        else:
            ext = mesh.extents
            sx = plate["build_width_um"] / 1000.0
            sy = plate["build_depth_um"] / 1000.0
            sz = plate["build_height_um"] / 1000.0
            if ext[0] > sx + 1e-3 or ext[1] > sy + 1e-3 or ext[2] > sz + 1e-3:
                raise resin_slice.ResinSliceError(
                    f"The model is {ext[0]:.1f} × {ext[1]:.1f} × {ext[2]:.1f} mm. "
                    f"{plate['name']} is {sx:.1f} × {sy:.1f} × {sz:.1f} mm."
                )
            job["phase"] = "mslicer"
            _write(job)
            report = mslicer_engine.slice_file(
                stl_path, out, plate, settings, kind, aa=bool(job["aa"]), cancel=ev,
                placed=bool(job.get("placed")),
            )
            report["plate_name"] = plate["name"]
            report["plate_id"] = plate["id"]
        # Drop the per-layer hashes from the status file. The download is the artifact.
        report.pop("sha256", None)
        report.pop("head", None)
        job["status"] = "done"
        job["progress"] = 1
        job["phase"] = "done"
        job["layers"] = report["layers"]
        job["done_layers"] = report["layers"]
        job["report"] = report
        ext = "lumen" if kind == "lumen" else kind
        job["download"] = f"/api/resin/jobs/{job_id}/print.{ext}"
        _write(job)
    except resin_slice.ResinSliceCancelled:
        _finish_cancel(job)
    except resin_slice.ResinSliceError as exc:
        _fail(job, str(exc))
    except Exception:
        _fail(job, "The slice failed. Try a simpler model or a coarser plate.")
    finally:
        _sem.release()
        with _lock:
            _cancel.pop(job_id, None)


def resin_slice_wait() -> float:
    return float(os.environ.get("ZEIM_RESIN_WAIT_S", "150"))


def _fail(job: dict, message: str) -> None:
    job["status"] = "error"
    job["error"] = message
    job["phase"] = "error"
    _write(job)
    _cleanup_partial(job["job_id"])


def _finish_cancel(job: dict) -> None:
    job["status"] = "cancelled"
    job["phase"] = "cancelled"
    job["error"] = ""
    _write(job)
    _cleanup_partial(job["job_id"])


def _cleanup_partial(job_id: str) -> None:
    d = _dir()
    for name in (f"job{job_id}.lumen", f"job{job_id}.goo", f"job{job_id}.ctb", f"job{job_id}.nanodlp"):
        path = d / name
        if path.is_file():
            path.unlink()
    thumb = d / f"job{job_id}"
    if thumb.is_dir():
        for child in thumb.iterdir():
            child.unlink()
        thumb.rmdir()
