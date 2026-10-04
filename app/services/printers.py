"""Network printer upload clients.

Implemented (tested against mock servers, not real hardware): OctoPrint, Moonraker.
Stubs (return a clear 'not implemented' result): PrusaLink, Bambu LAN, Duet, Repetier.
"""
from __future__ import annotations

from pathlib import Path

import httpx

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
