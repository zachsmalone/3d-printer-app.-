"""Opt-in done/failed alerts, multi-printer board polling, timelapse hooks,
and opt-in local failure detection that ONLY pauses (features 5, 6, 8, 10).

All paths are labelled Simulated until HARDWARE_VERIFIED flips in printers.py.
Never cancels on failure detection — pause only.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from ..config import DATA
from . import printers as printers_mod
from . import settings

STATE_FILE = DATA / "print_watch.json"
TLAPSE_DIR = DATA / "timelapse"
_lock = threading.Lock()

# States that mean "finished ok" / "failed" across OctoPrint + Moonraker (+ Bambu mock).
_DONE = {"operational", "complete", "completed", "standby", "idle", "finish", "finished", "done"}
_FAIL = {"error", "cancelled", "canceled", "klipper_shutdown", "shutdown", "offline", "disconnected"}
_PRINTING = {"printing", "paused", "pausing", "resuming", "running", "busy"}


def _load_state() -> dict:
    with _lock:
        if not STATE_FILE.exists():
            return {"printers": {}, "alerts": []}
        try:
            d = json.loads(STATE_FILE.read_text())
            return d if isinstance(d, dict) else {"printers": {}, "alerts": []}
        except Exception:
            return {"printers": {}, "alerts": []}


def _save_state(d: dict) -> None:
    with _lock:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(d, indent=2))
        try:
            STATE_FILE.chmod(0o600)
        except OSError:
            pass


def alert_prefs(printer: dict | None = None) -> dict:
    """Per-printer opt-in flags (defaults off)."""
    p = printer or {}
    return {
        "alert_done": bool(p.get("alert_done")),
        "alert_failed": bool(p.get("alert_failed")),
        "watch_failures": bool(p.get("watch_failures")),  # opt-in; pause only
        "timelapse": bool(p.get("timelapse")),
    }


def board() -> dict:
    """Status for every saved printer (multi-printer board)."""
    rows = []
    for p in settings.load().get("printers") or []:
        pub = {k: p.get(k) for k in ("id", "name", "type", "profile", "bed_x", "bed_y", "serial")}
        pub["has_key"] = bool(p.get("api_key"))
        prefs = alert_prefs(p)
        if not printers_mod.direct_control_enabled() or p.get("type") not in printers_mod.IMPLEMENTED:
            rows.append({**pub, **prefs, "ok": False,
                         "state": "unavailable",
                         "message": "Direct control off or type not implemented.",
                         "verification": printers_mod.verification_tag()})
            continue
        st = printers_mod.status(p)
        row = {**pub, **prefs, **{k: st.get(k) for k in (
            "ok", "state", "job_name", "progress_pct", "print_time", "print_time_left",
            "temperatures", "message", "verification", "hardware_verified", "limits")}}
        # Failure watch (opt-in): pause only
        if prefs["watch_failures"] and st.get("ok"):
            paused = _maybe_pause_on_failure(p, st)
            if paused:
                row["failure_pause"] = paused
        # Alert transitions
        notes = _note_transitions(p, st, prefs)
        if notes:
            row["new_alerts"] = notes
        rows.append(row)
    return {"printers": rows, "verification": printers_mod.verification_tag(),
            "hardware_verified": printers_mod.HARDWARE_VERIFIED,
            "note": "Simulated until a real-hardware pass. Failure watch only pauses — it never stops the job."}


def _norm_state(s: str | None) -> str:
    return (s or "").strip().lower()


def _note_transitions(printer: dict, st: dict, prefs: dict) -> list:
    if not st.get("ok"):
        return []
    pid = printer.get("id") or ""
    state = _norm_state(st.get("state"))
    d = _load_state()
    prev = (d.get("printers") or {}).get(pid) or {}
    prev_state = _norm_state(prev.get("state"))
    d.setdefault("printers", {})[pid] = {
        "state": state, "job_name": st.get("job_name"), "ts": time.time(),
        "progress_pct": st.get("progress_pct"),
    }
    alerts = []
    was_printing = prev_state in _PRINTING or prev_state == "printing"
    if prefs["alert_done"] and was_printing and state in _DONE:
        alerts.append({"kind": "done", "printer_id": pid, "name": printer.get("name"),
                       "job_name": st.get("job_name") or prev.get("job_name"),
                       "message": f"{printer.get('name') or 'Printer'}: print finished.",
                       "ts": time.time(), "verification": printers_mod.verification_tag()})
    if prefs["alert_failed"] and state in _FAIL and prev_state not in _FAIL:
        alerts.append({"kind": "failed", "printer_id": pid, "name": printer.get("name"),
                       "job_name": st.get("job_name") or prev.get("job_name"),
                       "message": f"{printer.get('name') or 'Printer'}: print failed or stopped with an error.",
                       "ts": time.time(), "verification": printers_mod.verification_tag()})
    if alerts:
        d.setdefault("alerts", [])
        d["alerts"] = (d["alerts"] + alerts)[-50:]
    _save_state(d)
    return alerts


def peek_alerts() -> dict:
    d = _load_state()
    return {"alerts": list(d.get("alerts") or []), "verification": printers_mod.verification_tag()}


def drain_alerts() -> dict:
    d = _load_state()
    alerts = list(d.get("alerts") or [])
    d["alerts"] = []
    _save_state(d)
    return {"alerts": alerts, "verification": printers_mod.verification_tag()}


def _maybe_pause_on_failure(printer: dict, st: dict) -> dict | None:
    """Opt-in local failure detection: if state looks failed/error while a job was active, pause only."""
    state = _norm_state(st.get("state"))
    pid = printer.get("id") or ""
    d = _load_state()
    prev = (d.get("printers") or {}).get(pid) or {}
    # Heuristic 1: explicit error-ish state
    bad = state in _FAIL or "error" in state
    # Heuristic 2: progress stuck while claiming to print (Simulated — needs real hardware tuning)
    stuck = False
    try:
        cur_p = float(st.get("progress_pct") or -1)
        prev_p = float(prev.get("progress_pct") or -1)
        if state in _PRINTING and prev.get("state") in _PRINTING and cur_p >= 0 and prev_p >= 0:
            if abs(cur_p - prev_p) < 0.01 and (time.time() - float(prev.get("ts") or 0)) > 120:
                stuck = True
    except (TypeError, ValueError):
        pass
    if not (bad or stuck):
        return None
    # Only pause — never cancel.
    r = printers_mod.control(printer, "pause")
    return {"reason": "error_state" if bad else "progress_stuck", "pause": r,
            "verification": printers_mod.verification_tag(),
            "note": "Failure watch only pauses. You choose whether to resume or stop."}


def timelapse_start(printer_id: str) -> dict:
    pr = settings.get_printer(printer_id)
    if not pr:
        return {"ok": False, "message": "Unknown printer."}
    if not alert_prefs(pr).get("timelapse") and not pr.get("timelapse"):
        # Allow explicit API start even if flag off — UI opts in first.
        pass
    folder = TLAPSE_DIR / (printer_id or "x")
    folder.mkdir(parents=True, exist_ok=True)
    d = _load_state()
    d.setdefault("timelapse", {})[printer_id] = {"active": True, "started": time.time(), "frames": 0, "dir": str(folder)}
    _save_state(d)
    # Grab one frame now if camera works
    snap = printers_mod.camera_snapshot(pr)
    frames = 0
    if snap.get("ok") and snap.get("data"):
        (folder / f"frame_{int(time.time())}.jpg").write_bytes(snap["data"])
        frames = 1
        d["timelapse"][printer_id]["frames"] = 1
        _save_state(d)
    return {"ok": True, "frames": frames, "dir": str(folder),
            "message": "Timelapse folder ready (Simulated — frames are local snapshots when the camera answers).",
            "verification": printers_mod.verification_tag(),
            "camera": {k: snap.get(k) for k in ("ok", "message", "verification")}}


def timelapse_stop(printer_id: str) -> dict:
    d = _load_state()
    info = (d.get("timelapse") or {}).get(printer_id) or {}
    if printer_id in (d.get("timelapse") or {}):
        d["timelapse"][printer_id]["active"] = False
        d["timelapse"][printer_id]["stopped"] = time.time()
        _save_state(d)
    return {"ok": True, "info": info, "verification": printers_mod.verification_tag(),
            "message": "Timelapse stopped. Frames stay on this computer under data/timelapse/."}


def timelapse_tick(printer_id: str) -> dict:
    """Capture one more frame if timelapse is active."""
    d = _load_state()
    info = (d.get("timelapse") or {}).get(printer_id) or {}
    if not info.get("active"):
        return {"ok": False, "message": "No active timelapse for this printer."}
    pr = settings.get_printer(printer_id)
    if not pr:
        return {"ok": False, "message": "Unknown printer."}
    snap = printers_mod.camera_snapshot(pr)
    if not snap.get("ok"):
        return {"ok": False, "message": snap.get("message") or "No camera frame.", "verification": printers_mod.verification_tag()}
    folder = Path(info.get("dir") or (TLAPSE_DIR / printer_id))
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"frame_{int(time.time())}.jpg"
    path.write_bytes(snap["data"])
    info["frames"] = int(info.get("frames") or 0) + 1
    d["timelapse"][printer_id] = info
    _save_state(d)
    return {"ok": True, "frames": info["frames"], "path": str(path), "verification": printers_mod.verification_tag()}
