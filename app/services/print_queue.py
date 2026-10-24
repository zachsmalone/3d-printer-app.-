"""Simple manual-start print queue (feature 9).

Jobs sit until the user presses Start. No auto-chaining onto a busy printer.
Stored in data/print_queue.json. Simulated / not verified on real hardware.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

from ..config import DATA
from . import printers as printers_mod
from . import settings

FILE = DATA / "print_queue.json"
_lock = threading.Lock()


def _empty():
    return {"jobs": []}


def _load() -> dict:
    with _lock:
        if not FILE.exists():
            return _empty()
        try:
            d = json.loads(FILE.read_text())
            return d if isinstance(d, dict) and isinstance(d.get("jobs"), list) else _empty()
        except Exception:
            return _empty()


def _save(d: dict) -> None:
    with _lock:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        FILE.write_text(json.dumps(d, indent=2))
        try:
            FILE.chmod(0o600)
        except OSError:
            pass


def list_jobs() -> dict:
    d = _load()
    return {"jobs": d["jobs"], "verification": printers_mod.verification_tag(),
            "hardware_verified": printers_mod.HARDWARE_VERIFIED,
            "note": "Manual start only — ZEIM will not auto-start the next job on a busy printer."}


def enqueue(printer_id: str, build_id: str, *, name: str = "", gcode_name: str = "",
            start_on_send: bool = False) -> dict:
    if not settings.get_printer(printer_id):
        return {"ok": False, "message": "Unknown printer."}
    bid = (build_id or "").strip()
    if not bid.isalnum():
        return {"ok": False, "message": "Invalid build id."}
    job = {
        "id": uuid.uuid4().hex[:10],
        "printer_id": printer_id,
        "build_id": bid,
        "name": (name or f"build {bid}")[:80],
        "gcode_name": (gcode_name or f"photo3d_{bid}.gcode")[:120],
        "start_on_send": bool(start_on_send),
        "created": time.time(),
        "status": "queued",
    }
    d = _load()
    d["jobs"].append(job)
    _save(d)
    return {"ok": True, "job": job, "verification": printers_mod.verification_tag()}


def remove(job_id: str) -> dict:
    d = _load()
    before = len(d["jobs"])
    d["jobs"] = [j for j in d["jobs"] if j.get("id") != job_id]
    if len(d["jobs"]) == before:
        return {"ok": False, "message": "Job not found."}
    _save(d)
    return {"ok": True}


def start_job(job_id: str) -> dict:
    """Slice (if needed) is the caller's job; here we upload an existing model.gcode and mark the row."""
    from .history import store
    d = _load()
    job = next((j for j in d["jobs"] if j.get("id") == job_id), None)
    if not job:
        return {"ok": False, "message": "Job not found."}
    if job.get("status") == "sent":
        return {"ok": False, "message": "That job was already sent."}
    pr = settings.get_printer(job["printer_id"])
    if not pr:
        return {"ok": False, "message": "Printer was removed."}
    gcode = store.dir(job["build_id"]) / "model.gcode"
    if not gcode.exists():
        return {"ok": False, "message": "No G-code yet — slice this build first, then start the queue job.",
                "need_slice": True}
    out = printers_mod.send(pr, gcode, job.get("gcode_name") or gcode.name, bool(job.get("start_on_send")))
    job["status"] = "sent" if out.get("ok") else "failed"
    job["last_result"] = {k: out[k] for k in out if k != "response"}
    job["sent_at"] = time.time()
    _save(d)
    return {"ok": bool(out.get("ok")), "job": job, "send": out}
