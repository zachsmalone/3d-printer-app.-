"""Network printer upload clients.

Implemented (tested against mock servers, not real hardware): OctoPrint, Moonraker.
Stubs (return a clear 'not implemented' result): PrusaLink, Bambu LAN, Duet, Repetier.
"""
from __future__ import annotations

from pathlib import Path

import httpx

PROFILE_DIR = Path(__file__).resolve().parent.parent / "profiles"
DEFAULT_BED = (250.0, 210.0)       # the generic bed used when no printer is chosen; ONE place, used by /api/slice and /api/send alike
# Printer presets. NOT new printer types: a preset is a Moonraker/OctoPrint printer plus a bed size and a slicer profile.
# Creality K1: stock firmware has no Moonraker; this preset is for a K1 that has Moonraker (rooted + community add-on) at :7125.
PROFILES = {
    "creality_k1": {"label": "Creality K1 (Experimental)", "type": "moonraker", "bed": (220.0, 220.0), "max_z": 250.0,
                    "ini": PROFILE_DIR / "creality_k1.ini", "experimental": True,
                    "hint": "Experimental: not tested on a real K1. Needs Moonraker on the printer (usually http://<printer-ip>:7125, not the Fluidd page on 4408). "
                            "It may not work with the factory firmware."},
}

TYPES = [
    {"type": "octoprint", "label": "OctoPrint", "implemented": True,
     "hint": "URL like http://octopi.local ; API key from OctoPrint > Settings > API"},
    {"type": "moonraker", "label": "Moonraker (Klipper / Mainsail / Fluidd)", "implemented": True,
     "hint": "URL like http://printer.local:7125 ; API key only if auth is enabled"},
    {"type": "prusalink", "label": "PrusaLink (stub)", "implemented": False,
     "hint": "Not implemented yet - use the slicer hand-off or download G-code"},
    {"type": "bambu", "label": "Bambu Lab LAN (stub)", "implemented": False,
     "hint": "Needs MQTT+FTPS with access code - not implemented yet"},
    {"type": "duet", "label": "Duet / RepRapFirmware (stub)", "implemented": False, "hint": "Not implemented yet"},
    {"type": "repetier", "label": "Repetier-Server (stub)", "implemented": False, "hint": "Not implemented yet"},
]
IMPLEMENTED = {t["type"] for t in TYPES if t["implemented"]}


def _client(p):
    return httpx.Client(base_url=p["url"].rstrip("/"), timeout=60,
                        headers={"X-Api-Key": p["api_key"]} if p.get("api_key") else {})


def send(printer: dict, gcode: "Path | None", name: str, start: bool) -> dict:
    t = printer.get("type")
    if t not in IMPLEMENTED:
        return {"ok": False, "stub": True,
                "message": f"'{t}' support is a stub and not implemented yet. "
                           "Use 'Open in slicer' or download the G-code and send it manually."}
    if not printer.get("url"):
        return {"ok": False, "message": "printer URL is not configured"}
    try:
        with _client(printer) as c, open(gcode, "rb") as fh:
            if t == "octoprint":
                r = c.post("/api/files/local", files={"file": (name, fh, "application/octet-stream")},
                           data={"select": "true", "print": "true" if start else "false"})
            else:  # moonraker
                r = c.post("/server/files/upload", files={"file": (name, fh, "application/octet-stream")},
                           data={"root": "gcodes", "print": "true" if start else "false"})
        if r.status_code >= 300:
            return {"ok": False, "message": f"{t} answered HTTP {r.status_code}: {r.text[:200]}"}
        return {"ok": True, "message": f"Uploaded '{name}' to {printer['name']}"
                + (" and started the print" if start else ""), "response": r.text[:300]}
    except httpx.HTTPError as e:
        return {"ok": False, "message": f"could not reach printer: {e}"}


def profile_of(printer: dict | None) -> dict | None:
    return PROFILES.get((printer or {}).get("profile") or "")


def bed_of(printer: dict | None) -> tuple[float, float]:
    """The bed the slicer must use for this printer. /api/slice and /api/send both call this - they cannot disagree."""
    if not printer:
        return DEFAULT_BED
    pr = profile_of(printer)
    return (float(printer.get("bed_x") or (pr["bed"][0] if pr else DEFAULT_BED[0])),
            float(printer.get("bed_y") or (pr["bed"][1] if pr else DEFAULT_BED[1])))


def ini_of(printer: dict | None):
    pr = profile_of(printer)
    return pr["ini"] if pr and pr["ini"].exists() else None


def test(printer: dict) -> dict:
    """Connection test: read-only GET requests, 5 s timeout, NEVER a print/upload/command. Returns {ok, message, detail}."""
    t, pr = printer.get("type"), profile_of(printer)
    note = (" " + pr["hint"]) if pr else ""
    if t not in IMPLEMENTED:
        return {"ok": False, "message": f"'{t}' is not implemented yet, so it cannot be tested.", "detail": {}}
    if not printer.get("url"):
        return {"ok": False, "message": "Add the printer's address first.", "detail": {}}
    try:
        with httpx.Client(base_url=printer["url"].rstrip("/"), timeout=5, follow_redirects=False,
                          headers={"X-Api-Key": printer["api_key"]} if printer.get("api_key") else {}) as c:
            if t == "octoprint":
                r = c.get("/api/version")
                if r.status_code in (401, 403):
                    return {"ok": False, "message": "The printer asked for a key. Check the API key.", "detail": {"status": r.status_code}}
                if r.status_code != 200:
                    return {"ok": False, "message": f"The address answered, but not like OctoPrint (HTTP {r.status_code}).", "detail": {"status": r.status_code}}
                j = _json(r)
                return {"ok": True, "message": "Reached OctoPrint" + (f" {j.get('server')}" if j.get("server") else "") + ".", "detail": {"server": j.get("server"), "api": j.get("api")}}
            r = c.get("/server/info")                                                # moonraker
            if r.status_code in (401, 403):
                return {"ok": False, "message": "The printer asked for a key. Check the API key." + note, "detail": {"status": r.status_code}}
            if r.status_code != 200:
                return {"ok": False, "message": f"The address answered, but not like Moonraker (HTTP {r.status_code}). For a K1 this usually means Moonraker is not installed, or the port is 4408 instead of 7125." + note,
                        "detail": {"status": r.status_code}}
            res = _json(r).get("result") or {}
            state = res.get("klippy_state")
            d = {"klippy_state": state, "moonraker_version": res.get("moonraker_version")}
            r2 = c.get("/printer/info")
            if r2.status_code == 200:
                d["printer_state"] = (_json(r2).get("result") or {}).get("state")
            if state == "ready" and d.get("printer_state", "ready") == "ready":
                return {"ok": True, "message": "Reached the printer and it is ready." + note, "detail": d}
            return {"ok": False, "message": f"Found the printer service, but the printer is not ready (state={d.get('printer_state') or state or 'unknown'})." + note, "detail": d}
    except httpx.TimeoutException:
        return {"ok": False, "message": "Nothing answered within 5 seconds. Check the address and that the printer is on." + note, "detail": {}}
    except httpx.HTTPError:
        return {"ok": False, "message": "Could not reach that address. Nothing answers there." + note, "detail": {}}


def _json(r) -> dict:
    try:
        j = r.json()
        return j if isinstance(j, dict) else {}
    except ValueError:
        return {}
