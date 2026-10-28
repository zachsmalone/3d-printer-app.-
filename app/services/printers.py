"""Network printer clients (upload, status, control, camera).

OctoPrint and Moonraker: real HTTP clients against the public printer APIs (upload, status,
control, camera, connection test). Responses carry verification="Live API" — the protocol
talks to a reachable endpoint; they are not pretend/mock success. Zach's Creality K1 has not
been confirmed as a hardware pass yet (HARDWARE_VERIFIED_TYPES stays empty until then).

Bambu Lab LAN: FTPS upload + MQTT print start when LAN Only and Developer Mode are on
(see BAMBU_LIMITS). Still verification="Simulated" (mock env or unconfirmed hardware). Always
keep Open in Bambu Studio as the fallback.

Stubs / unconfigured printers stay Simulated. Never fake a successful send when the printer
did not answer.

Never copies GPL/AGPL frontends (OctoPrint UI, Mainsail, Fluidd, Moonraker sources, Bambu Studio).
"""
from __future__ import annotations

import json
import os
import socket
import ssl
import struct
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from .. import config
from . import netguard

PROFILE_DIR = Path(__file__).resolve().parent.parent / "profiles"
DEFAULT_BED = (250.0, 210.0)
# Add a type here only after Zach confirms that path on real hardware (e.g. "moonraker" for his K1).
HARDWARE_VERIFIED_TYPES: set[str] = set()
# Backward-compat bool: True only when every Live-API type has a hardware pass.
HARDWARE_VERIFIED = False  # kept as False until HARDWARE_VERIFIED_TYPES covers moonraker+octoprint

# Types that speak a real network protocol (not a pretend success path).
LIVE_API_TYPES = frozenset({"moonraker", "octoprint"})

PROFILES = {
    "creality_k1": {"label": "Creality K1 (Moonraker)", "type": "moonraker", "bed": (220.0, 220.0), "max_z": 250.0,
                    "ini": PROFILE_DIR / "creality_k1.ini", "experimental": True,
                    "hint": ("Point ZEIM at Moonraker on the K1: http://<printer-ip>:7125 (not Fluidd/Mainsail on 4408). "
                             "Root/community firmware with Moonraker works; stock Creality UI alone may not. "
                             "Add the printer as type Moonraker, optional API key if auth is on, then use Test connection. "
                             "Hardware pass on Zach's K1 is still pending — label is Live API, not Hardware-tested.")},
}

# Verified from Bambu Lab Wiki (third-party integration + Developer Mode pages, 2026):
# - LAN Only + Developer Mode: third-party MQTT/FTPS/camera work like older firmware (no ACS).
# - LAN Only without Developer Mode: status MQTT reads may work; starting a print / control from
#   apps other than Bambu Studio needs Bambu Connect.
# - Developer Mode is LAN-only (no Bambu Cloud while it is on).
BAMBU_LIMITS = {
    "needs_lan_only": True,
    "needs_developer_mode_for_control": True,
    "status_reads_without_developer_mode": True,
    "cloud_with_developer_mode": False,
    "fallback": "Open in Bambu Studio",
    "note": ("Bambu LAN send needs LAN Only Mode. Starting or controlling a print from ZEIM also "
             "needs Developer Mode on the printer. Without Developer Mode, use Open in Bambu Studio "
             "(or Bambu Connect). Developer Mode cannot use Bambu Cloud. "
             "Simulated until tested on a real Bambu."),
}

HONESTY_NOTE_LIVE = (
    "Moonraker / OctoPrint use a real HTTP send (Live API). "
    "Not yet confirmed on Zach's Creality K1 hardware. "
    "Bambu LAN and unconfigured/stub paths stay Simulated."
)
HONESTY_NOTE_NONE = (
    "No network printer configured. Add a Moonraker (K1) or OctoPrint printer in Settings, "
    "or download G-code / Open in slicer. Unconfigured send stays Simulated."
)

TYPES = [
    {"type": "octoprint", "label": "OctoPrint", "implemented": True,
     "hint": "URL like http://octopi.local ; API key from OctoPrint > Settings > API"},
    {"type": "moonraker", "label": "Moonraker (Klipper / Mainsail / Fluidd / Creality K1)", "implemented": True,
     "hint": "URL like http://printer.local:7125 (K1: printer IP port 7125, not 4408). API key only if auth is enabled. Live API — real HTTP upload/status/control."},
    {"type": "prusalink", "label": "PrusaLink (Coming soon)", "implemented": False,
     "hint": "Coming soon. For now use the slicer hand-off or download the G-code."},
    {"type": "bambu", "label": "Bambu Lab LAN (Simulated)", "implemented": True,
     "hint": ("Printer address as http://<printer-ip> (host only is used). API key = 8-digit LAN "
              "access code. Serial number required. Needs LAN Only + Developer Mode for send/control. "
              "Keep Open in Bambu Studio as fallback. Simulated — not tried on a real Bambu yet.")},
    {"type": "duet", "label": "Duet / RepRapFirmware (Coming soon)", "implemented": False, "hint": "Coming soon."},
    {"type": "repetier", "label": "Repetier-Server (Coming soon)", "implemented": False, "hint": "Coming soon."},
]
IMPLEMENTED = {t["type"] for t in TYPES if t["implemented"]}
CONTROL_TYPES = {"octoprint", "moonraker", "bambu"}


def verification_tag(ptype: str | None = None) -> str:
    """Per-path honesty label.

    - Hardware-tested: type listed in HARDWARE_VERIFIED_TYPES after a real-printer pass
    - Live API: Moonraker / OctoPrint real HTTP clients (clears Simulated for that path)
    - Simulated: Bambu (unconfirmed), stubs, mocks, or unknown/unconfigured
    Global (ptype None): Live API, because the primary K1 path is Moonraker. UI honesty notes
    still say Bambu stays Simulated.
    """
    t = (ptype or "").strip().lower()
    if t and t in HARDWARE_VERIFIED_TYPES:
        return "Hardware-tested"
    if t in LIVE_API_TYPES:
        return "Live API"
    if t:  # bambu, stubs, anything else named
        return "Simulated"
    return "Live API"


def honesty_note(printers_configured: bool = True) -> str:
    return HONESTY_NOTE_LIVE if printers_configured else HONESTY_NOTE_NONE


def _hardware_verified_for(ptype: str | None) -> bool:
    t = (ptype or "").strip().lower()
    return bool(t) and t in HARDWARE_VERIFIED_TYPES


def _v(extra: dict | None = None, ptype: str | None = None) -> dict:
    out = {
        "verification": verification_tag(ptype),
        "hardware_verified": _hardware_verified_for(ptype) if ptype else HARDWARE_VERIFIED,
    }
    if extra:
        out.update(extra)
    return out


def direct_control_enabled() -> bool:
    """Launch checklist Task 10: letting the server talk to arbitrary printer URLs is an SSRF
    vector, so on PRODUCTION deployments direct printer control is off unless explicitly
    re-enabled with ZEIM_PRINTER_DIRECT=1. The supported path there is file handoff: download
    the .gcode and upload it in the printer's own app (or the future paired local connector).
    Dev/localhost keeps direct control so real-printer testing works. Read at call time."""
    if (os.environ.get("ZEIM_PRINTER_DIRECT") or "").lower() in ("1", "true", "yes"):
        return True
    return (os.environ.get("ZEIM_ENV") or "").lower() != "production"


DIRECT_OFF_MESSAGE = ("This deployment uses file handoff instead of direct printer control: "
                      "download the .gcode and upload it in your printer's own app. "
                      "(Server-side printer control is disabled in production unless ZEIM_PRINTER_DIRECT=1.)")


def check_url(url: str) -> None:
    """Refuse printer addresses that could turn the server into a proxy (SSRF). Always blocked: credentials in the URL,
    link-local (incl. cloud metadata 169.254.169.254), unspecified and multicast addresses. With PHOTO3D_BLOCK_PRIVATE_PRINTERS=1
    (hosted deployments) loopback and private networks are blocked too. Called when saving AND before every request, so a
    hostname that later resolves elsewhere is still caught. Raises ValueError."""
    u = urlsplit(str(url or "").strip())
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
        raise ValueError("Printer address must look like http://host or http://host:port (no username or password in it).")
    try:
        port = u.port
        infos = socket.getaddrinfo(u.hostname, port or (443 if u.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except (ValueError, socket.gaierror, UnicodeError):
        return  # unresolvable now: the request itself will fail with a clear message, and is re-checked at send time
    for info in infos:
        ip = __import__("ipaddress").ip_address(info[4][0].split("%")[0])
        if ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
            raise ValueError("That printer address is not allowed (link-local or reserved network).")
        if config.BLOCK_PRIVATE_PRINTERS and (ip.is_loopback or ip.is_private):
            raise ValueError("This server does not allow printers on private or local networks. Use the slicer hand-off or download the G-code.")


def shared_mode_denial(url: str) -> str | None:
    """Shared mode only (ported from perplexity/ssrf-printer-guard): refuse printer addresses that resolve to the server's
    own machine, cloud metadata or private LAN ranges (PHOTO3D_LAN_PRINTERS=1 re-allows the LAN ranges for self-hosters on
    the printer's network; loopback and link-local stay blocked). Local mode is never restricted here. Checked when saving
    AND before every request. Complements check_url(), which applies in every mode."""
    if config.MODE != "shared":
        return None
    return netguard.shared_mode_denial(url, lan_ok=config.LAN_PRINTERS)


def _guard_printer(printer: dict) -> dict | None:
    """Return an error result dict, or None if the printer may be dialed."""
    t = printer.get("type")
    if not direct_control_enabled():
        return {"ok": False, "message": DIRECT_OFF_MESSAGE, **_v(ptype=t)}
    if t not in IMPLEMENTED:
        return {"ok": False, "stub": True,
                "message": f"'{t}' support is a stub and not implemented yet. "
                           "Use 'Open in slicer' or download the G-code and send it manually.", **_v(ptype=t)}
    if not printer.get("url"):
        return {"ok": False, "message": "printer URL is not configured — add an address in Settings, or use Open in slicer / download G-code.",
                **_v(ptype=t)}
    denial = shared_mode_denial(printer["url"])
    if denial:
        return {"ok": False, "message": denial, **_v(ptype=t)}
    try:
        check_url(printer["url"])
    except ValueError as e:
        return {"ok": False, "message": str(e), **_v(ptype=t)}
    return None


def _client(p, timeout: float = 60):
    return httpx.Client(base_url=p["url"].rstrip("/"), timeout=timeout,
                        headers={"X-Api-Key": p["api_key"]} if p.get("api_key") else {})


def _json(r) -> dict:
    try:
        j = r.json()
        return j if isinstance(j, dict) else {}
    except ValueError:
        return {}


def _print_confirmed(st: dict, name: str) -> bool:
    """True only when the printer's own status says this file is printing."""
    if not st or not st.get("ok"):
        return False
    if str(st.get("state") or "").strip().lower() != "printing":
        return False
    job = str(st.get("job_name") or "")
    if not job:
        return True
    return name in job or job in name


def _upload_accepted(printer: dict, name: str, start: bool, t: str) -> dict:
    """An HTTP upload is acceptance. A start flag is a request. Only a later status read confirms it."""
    who = printer.get("name") or "printer"
    note = " (Live API — real HTTP upload; not yet Hardware-tested on Zach's K1)."
    confirmed = False
    if start and t in ("moonraker", "octoprint"):
        try:
            confirmed = _print_confirmed(status(printer), name)
        except Exception:
            confirmed = False
    if not start:
        start_state = "not_requested"
        msg = f"Uploaded '{name}' to {who}. The printer accepted the file. Print was not started."
    elif confirmed:
        start_state = "confirmed"
        msg = f"Uploaded '{name}' to {who}. The printer accepted the file and reports the print is running."
    else:
        start_state = "requested"
        msg = (f"Uploaded '{name}' to {who}. The printer accepted the file. "
               "A start was requested. The printer has not confirmed that it is printing.")
    return {"ok": True, "transfer": "accepted", "start": start_state, "message": msg + note, **_v(ptype=t)}


def send(printer: dict, gcode: "Path | None", name: str, start: bool) -> dict:
    err = _guard_printer(printer)
    if err:
        return err
    t = printer.get("type")
    if t == "bambu":
        return _send_bambu(printer, gcode, name, start)
    if gcode is None or not Path(gcode).is_file():
        return {"ok": False, "message": "No G-code file to upload. Slice first, or use Open in slicer.", **_v(ptype=t)}
    try:
        with _client(printer) as c, open(gcode, "rb") as fh:
            if t == "octoprint":
                r = c.post("/api/files/local", files={"file": (name, fh, "application/octet-stream")},
                           data={"select": "true", "print": "true" if start else "false"})
            else:  # moonraker
                r = c.post("/server/files/upload", files={"file": (name, fh, "application/octet-stream")},
                           data={"root": "gcodes", "print": "true" if start else "false"})
        if r.status_code >= 300:
            return {"ok": False, "message": f"{t} answered HTTP {r.status_code}: {r.text[:200]}", **_v(ptype=t)}
        return {**_upload_accepted(printer, name, start, t), "response": r.text[:300]}
    except httpx.HTTPError as e:
        return {"ok": False, "message": f"could not reach printer: {e}", **_v(ptype=t)}


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
    if t == "bambu":
        return _test_bambu(printer)
    if t not in IMPLEMENTED:
        return {"ok": False, "message": f"'{t}' is not implemented yet, so it cannot be tested.", "detail": {}, **_v(ptype=t)}
    if not printer.get("url"):
        return {"ok": False, "message": "Add the printer's address first.", "detail": {}, **_v(ptype=t)}
    denial = shared_mode_denial(printer["url"])
    if denial:
        return {"ok": False, "message": denial, "detail": {}, **_v(ptype=t)}
    try:
        check_url(printer["url"])
    except ValueError as e:
        return {"ok": False, "message": str(e), "detail": {}, **_v(ptype=t)}
    try:
        with httpx.Client(base_url=printer["url"].rstrip("/"), timeout=5, follow_redirects=False,
                          headers={"X-Api-Key": printer["api_key"]} if printer.get("api_key") else {}) as c:
            if t == "octoprint":
                r = c.get("/api/version")
                if r.status_code in (401, 403):
                    return {"ok": False, "message": "The printer asked for a key. Check the API key.", "detail": {"status": r.status_code}, **_v(ptype=t)}
                if r.status_code != 200:
                    return {"ok": False, "message": f"The address answered, but not like OctoPrint (HTTP {r.status_code}).", "detail": {"status": r.status_code}, **_v(ptype=t)}
                j = _json(r)
                return {"ok": True, "message": "Reached OctoPrint" + (f" {j.get('server')}" if j.get("server") else "") + " (Live API).",
                        "detail": {"server": j.get("server"), "api": j.get("api")}, **_v(ptype=t)}
            r = c.get("/server/info")                                                # moonraker
            if r.status_code in (401, 403):
                return {"ok": False, "message": "The printer asked for a key. Check the API key." + note, "detail": {"status": r.status_code}, **_v(ptype=t)}
            if r.status_code != 200:
                return {"ok": False, "message": f"The address answered, but not like Moonraker (HTTP {r.status_code}). For a K1 this usually means Moonraker is not installed, or the port is 4408 instead of 7125." + note,
                        "detail": {"status": r.status_code}, **_v(ptype=t)}
            res = _json(r).get("result") or {}
            state = res.get("klippy_state")
            d = {"klippy_state": state, "moonraker_version": res.get("moonraker_version")}
            r2 = c.get("/printer/info")
            if r2.status_code == 200:
                d["printer_state"] = (_json(r2).get("result") or {}).get("state")
            if state == "ready" and d.get("printer_state", "ready") == "ready":
                return {"ok": True, "message": "Reached Moonraker and the printer is ready (Live API)." + note, "detail": d, **_v(ptype=t)}
            return {"ok": False, "message": f"Found Moonraker, but the printer is not ready (state={d.get('printer_state') or state or 'unknown'})." + note, "detail": d, **_v(ptype=t)}
    except httpx.TimeoutException:
        return {"ok": False, "message": "Nothing answered within 5 seconds. Check the address and that the printer is on." + note, "detail": {}, **_v(ptype=t)}
    except httpx.HTTPError:
        return {"ok": False, "message": "Could not reach that address. Nothing answers there." + note, "detail": {}, **_v(ptype=t)}


# ---------- 1. Live status ----------

def status(printer: dict) -> dict:
    """Live job/printer state for OctoPrint / Moonraker / Bambu. Labels are per-path (Live API vs Simulated)."""
    err = _guard_printer(printer)
    if err:
        return err
    t = printer.get("type")
    try:
        if t == "octoprint":
            return _status_octoprint(printer)
        if t == "moonraker":
            return _status_moonraker(printer)
        if t == "bambu":
            return _status_bambu(printer)
        return {"ok": False, "message": f"Status is not available for '{t}'.", **_v(ptype=t)}
    except httpx.HTTPError as e:
        return {"ok": False, "message": f"could not reach printer: {e}", **_v(ptype=t)}


def _status_octoprint(printer: dict) -> dict:
    with _client(printer, timeout=8) as c:
        job, pr = c.get("/api/job"), c.get("/api/printer")
        if job.status_code in (401, 403) or pr.status_code in (401, 403):
            return {"ok": False, "message": "The printer asked for a key. Check the API key.", **_v(ptype="octoprint")}
        if job.status_code != 200:
            return {"ok": False, "message": f"OctoPrint job status HTTP {job.status_code}.", **_v(ptype="octoprint")}
        j, p = _json(job), _json(pr) if pr.status_code == 200 else {}
        progress = (j.get("progress") or {})
        state = (j.get("state") or (p.get("state") or {}).get("text") or "unknown")
        return {"ok": True, "type": "octoprint", "state": str(state),
                "job_name": ((j.get("job") or {}).get("file") or {}).get("name"),
                "progress_pct": progress.get("completion"),
                "print_time": progress.get("printTime"),
                "print_time_left": progress.get("printTimeLeft"),
                "temperatures": _temps_octo(p),
                "flags": ((p.get("state") or {}).get("flags") or {}),
                **_v(ptype="octoprint")}


def _temps_octo(p: dict) -> dict:
    temps = p.get("temperature") or {}
    out = {}
    for k in ("tool0", "bed"):
        if isinstance(temps.get(k), dict):
            out[k] = {"actual": temps[k].get("actual"), "target": temps[k].get("target")}
    return out


def _status_moonraker(printer: dict) -> dict:
    with _client(printer, timeout=8) as c:
        r = c.get("/printer/objects/query", params={
            "print_stats": "state,filename,print_duration,message",
            "display_status": "progress",
            "virtual_sdcard": "progress,is_active",
            "extruder": "temperature,target",
            "heater_bed": "temperature,target",
        })
        if r.status_code in (401, 403):
            return {"ok": False, "message": "The printer asked for a key. Check the API key.", **_v(ptype="moonraker")}
        if r.status_code != 200:
            return {"ok": False, "message": f"Moonraker status HTTP {r.status_code}.", **_v(ptype="moonraker")}
        st = ((_json(r).get("result") or {}).get("status") or {})
        ps, ds = st.get("print_stats") or {}, st.get("display_status") or {}
        vs = st.get("virtual_sdcard") or {}
        ex, bed = st.get("extruder") or {}, st.get("heater_bed") or {}
        prog = ds.get("progress")
        if prog is None:
            prog = vs.get("progress")
        pct = (float(prog) * 100.0) if isinstance(prog, (int, float)) and prog <= 1.5 else prog
        return {"ok": True, "type": "moonraker", "state": str(ps.get("state") or "unknown"),
                "job_name": ps.get("filename"), "progress_pct": pct,
                "print_time": ps.get("print_duration"), "print_time_left": None,
                "message": ps.get("message") or "",
                "temperatures": {
                    "tool0": {"actual": ex.get("temperature"), "target": ex.get("target")},
                    "bed": {"actual": bed.get("temperature"), "target": bed.get("target")},
                }, **_v(ptype="moonraker")}


# ---------- 2. Remote pause / resume / stop ----------

def control(printer: dict, action: str) -> dict:
    """pause | resume | cancel. Never starts a new print. Labels are per-path."""
    action = (action or "").strip().lower()
    t0 = (printer or {}).get("type")
    if action not in ("pause", "resume", "cancel"):
        return {"ok": False, "message": "Action must be pause, resume, or cancel.", **_v(ptype=t0)}
    err = _guard_printer(printer)
    if err:
        return err
    t = printer.get("type")
    if t not in CONTROL_TYPES:
        return {"ok": False, "message": f"Remote control is not available for '{t}'.", **_v(ptype=t)}
    try:
        if t == "octoprint":
            return _control_octoprint(printer, action)
        if t == "moonraker":
            return _control_moonraker(printer, action)
        if t == "bambu":
            return _control_bambu(printer, action)
    except httpx.HTTPError as e:
        return {"ok": False, "message": f"could not reach printer: {e}", **_v(ptype=t)}
    return {"ok": False, "message": "Unsupported printer type.", **_v(ptype=t)}


def _control_octoprint(printer: dict, action: str) -> dict:
    body = {"command": "cancel"} if action == "cancel" else {"command": "pause", "action": action}
    with _client(printer, timeout=15) as c:
        r = c.post("/api/job", json=body)
        if r.status_code in (401, 403):
            return {"ok": False, "message": "The printer asked for a key. Check the API key.", **_v(ptype="octoprint")}
        if r.status_code in (204, 200):
            return {"ok": True, "action": action, "accepted": True, "confirmed": False,
                    "message": f"The printer accepted {action}. ZEIM has not confirmed the new state.", **_v(ptype="octoprint")}
        if r.status_code == 409:
            return {"ok": False, "message": f"OctoPrint refused {action} (nothing active to {action}).", **_v(ptype="octoprint")}
        return {"ok": False, "message": f"OctoPrint answered HTTP {r.status_code}: {r.text[:200]}", **_v(ptype="octoprint")}


def _control_moonraker(printer: dict, action: str) -> dict:
    path = {"pause": "/printer/print/pause", "resume": "/printer/print/resume", "cancel": "/printer/print/cancel"}[action]
    with _client(printer, timeout=15) as c:
        r = c.post(path)
        if r.status_code in (401, 403):
            return {"ok": False, "message": "The printer asked for a key. Check the API key.", **_v(ptype="moonraker")}
        if r.status_code == 200:
            return {"ok": True, "action": action, "accepted": True, "confirmed": False,
                    "message": f"The printer accepted {action}. ZEIM has not confirmed the new state.", **_v(ptype="moonraker")}
        return {"ok": False, "message": f"Moonraker answered HTTP {r.status_code}: {r.text[:200]}", **_v(ptype="moonraker")}


# ---------- 4. Camera (snapshot proxy) ----------

def camera_snapshot(printer: dict) -> dict:
    """Fetch one JPEG (or image bytes) from the printer camera. Same-host only (SSRF)."""
    err = _guard_printer(printer)
    if err:
        return err
    t = printer.get("type")
    try:
        if t == "octoprint":
            return _camera_octoprint(printer)
        if t == "moonraker":
            return _camera_moonraker(printer)
        if t == "bambu":
            return {"ok": False, "message": "Bambu camera in ZEIM is Simulated and not wired yet. Use Bambu Studio / Handy for live view until a real-hardware pass.",
                    "fallback": "bambu_studio", **_v(ptype="bambu")}
        return {"ok": False, "message": f"Camera is not available for '{t}'.", **_v(ptype=t)}
    except httpx.HTTPError as e:
        return {"ok": False, "message": f"could not reach camera: {e}", **_v(ptype=t)}


def _same_host(printer_url: str, candidate: str) -> bool:
    a, b = urlsplit(printer_url), urlsplit(urljoin(printer_url.rstrip("/") + "/", candidate))
    return bool(a.hostname and b.hostname and a.hostname.lower() == b.hostname.lower())


def _fetch_image(printer: dict, path_or_url: str) -> dict:
    t = printer.get("type")
    base = printer["url"].rstrip("/") + "/"
    full = urljoin(base, path_or_url)
    if not _same_host(printer["url"], full):
        return {"ok": False, "message": "Camera address must be on the same host as the printer.", **_v(ptype=t)}
    try:
        check_url(full if urlsplit(full).scheme else printer["url"])
    except ValueError as e:
        return {"ok": False, "message": str(e), **_v(ptype=t)}
    with _client(printer, timeout=10) as c:
        r = c.get(full if full.startswith("http") else path_or_url)
        if r.status_code != 200:
            return {"ok": False, "message": f"Camera answered HTTP {r.status_code}.", **_v(ptype=t)}
        ctype = (r.headers.get("content-type") or "image/jpeg").split(";")[0].strip()
        if not ctype.startswith("image/"):
            return {"ok": False, "message": "Camera did not return an image.", **_v(ptype=t)}
        return {"ok": True, "content_type": ctype, "data": r.content, **_v(ptype=t)}


def _camera_octoprint(printer: dict) -> dict:
    with _client(printer, timeout=8) as c:
        snap = "/webcam/?action=snapshot"
        r = c.get("/api/settings")
        if r.status_code == 200:
            cam = (_json(r).get("webcam") or {})
            snap = cam.get("snapshotUrl") or cam.get("snapshot") or snap
        return _fetch_image(printer, snap)


def _camera_moonraker(printer: dict) -> dict:
    with _client(printer, timeout=8) as c:
        r = c.get("/server/webcams/list")
        if r.status_code == 200:
            cams = (_json(r).get("result") or {}).get("webcams") or []
            for cam in cams:
                snap = cam.get("snapshot_url") or cam.get("snapshotUrl")
                if snap:
                    return _fetch_image(printer, snap)
        # Common fallback used by many Klipper setups
        return _fetch_image(printer, "/webcam/?action=snapshot")


# ---------- 7. Spool-enough check ----------

def spool_check(printer: dict, filament_g: float | None) -> dict:
    """Compare slice filament grams to the optional spool_remaining_g on the printer row."""
    remaining = printer.get("spool_remaining_g")
    try:
        remaining = float(remaining) if remaining is not None and remaining != "" else None
    except (TypeError, ValueError):
        remaining = None
    try:
        need = float(filament_g) if filament_g is not None else None
    except (TypeError, ValueError):
        need = None
    t = printer.get("type")
    if remaining is None:
        return {"ok": True, "checked": False, "message": "No spool amount saved for this printer — skipped.", **_v(ptype=t)}
    if need is None:
        return {"ok": True, "checked": False, "message": "Slice did not report filament grams — skipped.", **_v(ptype=t)}
    enough = remaining + 1e-6 >= need
    return {"ok": enough, "checked": True, "need_g": need, "remaining_g": remaining,
            "message": (f"Spool looks like enough (~{remaining:.1f} g left, job needs ~{need:.1f} g)."
                        if enough else
                        f"Spool may run out: ~{remaining:.1f} g left, job needs ~{need:.1f} g."),
            **_v(ptype=t)}


# ---------- Bambu LAN (3) ----------

def bambu_limits() -> dict:
    return {**BAMBU_LIMITS, **_v(ptype="bambu")}


def _bambu_host(printer: dict) -> str:
    return (urlsplit(printer.get("url") or "").hostname or "").strip()


def _bambu_code(printer: dict) -> str:
    return str(printer.get("api_key") or "").strip()


def _bambu_serial(printer: dict) -> str:
    return str(printer.get("serial") or "").strip()


def _test_bambu(printer: dict) -> dict:
    host, code, serial = _bambu_host(printer), _bambu_code(printer), _bambu_serial(printer)
    if not host:
        return {"ok": False, "message": "Add the printer's address (http://printer-ip).", "detail": {}, **_v(ptype="bambu"),
                "limits": BAMBU_LIMITS}
    if not (code.isdigit() and len(code) == 8):
        return {"ok": False, "message": "Bambu LAN access code must be 8 digits (from the printer's LAN Only screen).",
                "detail": {}, **_v(ptype="bambu"), "limits": BAMBU_LIMITS}
    if not serial:
        return {"ok": False, "message": "Add the printer serial (on the printer screen or Bambu Studio device info).",
                "detail": {}, **_v(ptype="bambu"), "limits": BAMBU_LIMITS}
    if (os.environ.get("ZEIM_BAMBU_MOCK") or "").lower() in ("1", "true", "yes"):
        return {"ok": True, "message": "Simulated Bambu LAN reachability (mock). Needs LAN Only + Developer Mode on a real printer.",
                "detail": {"host": host, "serial": serial, "mock": True}, **_v(ptype="bambu"), "limits": BAMBU_LIMITS}
    # Probe MQTT (8883) and FTPS (990) — connect only, no credentials exchange beyond TLS.
    ports = {}
    for port in (8883, 990):
        try:
            with socket.create_connection((host, port), timeout=3):
                ports[port] = "open"
        except OSError:
            ports[port] = "closed"
    if ports.get(8883) == "open" or ports.get(990) == "open":
        return {"ok": True, "message": ("Reached Bambu LAN ports (Simulated — not a full login). "
                                        "Send/control need Developer Mode. Keep Open in Bambu Studio as fallback."),
                "detail": {"host": host, "ports": ports, "serial": serial}, **_v(ptype="bambu"), "limits": BAMBU_LIMITS}
    return {"ok": False, "message": ("Nothing answered on Bambu LAN ports 8883/990. Check LAN Only Mode, the IP, "
                                     "and that this computer is on the same network. Or use Open in Bambu Studio."),
            "detail": {"host": host, "ports": ports}, **_v(ptype="bambu"), "limits": BAMBU_LIMITS}


def _send_bambu(printer: dict, gcode: Path | None, name: str, start: bool) -> dict:
    host, code, serial = _bambu_host(printer), _bambu_code(printer), _bambu_serial(printer)
    if not host or not (code.isdigit() and len(code) == 8) or not serial:
        return {"ok": False, "fallback": "bambu_studio",
                "message": "Bambu LAN needs address, 8-digit access code, and serial. Or use Open in Bambu Studio.",
                "limits": BAMBU_LIMITS, **_v(ptype="bambu")}
    if (os.environ.get("ZEIM_BAMBU_MOCK") or "").lower() in ("1", "true", "yes"):
        return {"ok": True, "transfer": "simulated", "start": "not_confirmed",
                "message": f"Simulated Bambu path: '{name}' was not sent to a real printer. "
                           + ("A start was not confirmed. " if start else "Print was not started. ")
                           + "Not tried on a real Bambu.",
                "fallback": "bambu_studio", "limits": BAMBU_LIMITS, "mock": True, **_v(ptype="bambu")}
    # Real path: FTPS put, then optional MQTT start. Label Simulated until hardware-verified.
    try:
        _bambu_ftps_upload(host, code, gcode, name)
    except Exception as e:
        return {"ok": False, "fallback": "bambu_studio",
                "message": f"Bambu FTPS upload failed ({e}). Use Open in Bambu Studio. "
                           "Confirm LAN Only + Developer Mode.",
                "limits": BAMBU_LIMITS, **_v(ptype="bambu")}
    if start:
        try:
            _bambu_mqtt_print(host, code, serial, name)
        except Exception as e:
            return {"ok": True, "started": False, "transfer": "accepted", "start": "requested", "fallback": "bambu_studio",
                    "message": f"Uploaded '{name}'. A start was requested and the printer did not confirm it ({e}). "
                               "Open the file on the printer or use Open in Bambu Studio. Needs Developer Mode.",
                    "limits": BAMBU_LIMITS, **_v(ptype="bambu")}
    return {"ok": True, "transfer": "accepted", "start": "requested" if start else "not_requested",
            "message": f"Uploaded '{name}' to Bambu (Simulated path). "
                       + ("A start was requested and is not confirmed on the printer. " if start else "Print was not started. ")
                       + "Not verified on real hardware yet.",
            "fallback": "bambu_studio", "limits": BAMBU_LIMITS, **_v(ptype="bambu")}


def _bambu_ftps_upload(host: str, code: str, path: Path, name: str) -> None:
    import ftplib
    ctx = ssl._create_unverified_context()  # printer uses a self-signed cert on LAN
    ftp = ftplib.FTP_TLS(context=ctx)
    ftp.connect(host, 990, timeout=30)
    ftp.auth()
    ftp.login("bblp", code)
    ftp.prot_p()
    with open(path, "rb") as fh:
        ftp.storbinary(f"STOR {name}", fh)
    try:
        ftp.quit()
    except Exception:
        ftp.close()


def _mqtt_encode_str(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack("!H", len(b)) + b


def _bambu_mqtt_print(host: str, code: str, serial: str, filename: str) -> None:
    """Minimal MQTT 3.1.1 CONNECT + PUBLISH over TLS (LAN, self-signed). No third-party MQTT lib."""
    ctx = ssl._create_unverified_context()
    raw = socket.create_connection((host, 8883), timeout=15)
    sock = ctx.wrap_socket(raw, server_hostname=host)
    try:
        client_id = "zeim" + os.urandom(3).hex()
        # Variable header + payload for CONNECT
        vh = b"\x00\x04MQTT\x04\xc2\x00\x3c"  # proto MQTT 3.1.1, user+pass, keepalive 60
        payload = _mqtt_encode_str(client_id) + _mqtt_encode_str("bblp") + _mqtt_encode_str(code)
        body = vh + payload
        sock.sendall(bytes([0x10, len(body)]) + body)
        ack = sock.recv(4)
        if len(ack) < 4 or ack[0] != 0x20 or ack[3] != 0:
            raise RuntimeError("MQTT CONNACK refused (is Developer Mode on?)")
        topic = f"device/{serial}/request"
        msg = json.dumps({"print": {"command": "gcode_file", "param": filename}})
        t_b, m_b = topic.encode(), msg.encode()
        pub = struct.pack("!H", len(t_b)) + t_b + m_b
        # remaining length encoding (short)
        rl = len(pub)
        if rl < 128:
            sock.sendall(bytes([0x30, rl]) + pub)
        else:
            sock.sendall(bytes([0x30, (rl & 0x7F) | 0x80, rl >> 7]) + pub)
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _status_bambu(printer: dict) -> dict:
    if (os.environ.get("ZEIM_BAMBU_MOCK") or "").lower() in ("1", "true", "yes"):
        return {"ok": True, "type": "bambu", "state": "IDLE", "job_name": None, "progress_pct": 0,
                "message": "Simulated Bambu status.", **_v(ptype="bambu"), "limits": BAMBU_LIMITS}
    # Without a standing MQTT subscription we only report reachability.
    t = _test_bambu(printer)
    if not t.get("ok"):
        return {**t, "type": "bambu"}
    return {"ok": True, "type": "bambu", "state": "reachable", "job_name": None, "progress_pct": None,
            "message": "Bambu LAN ports answer. Live job % needs a sustained MQTT session (Simulated).",
            **_v(ptype="bambu"), "limits": BAMBU_LIMITS}


def _control_bambu(printer: dict, action: str) -> dict:
    host, code, serial = _bambu_host(printer), _bambu_code(printer), _bambu_serial(printer)
    if not host or not code or not serial:
        return {"ok": False, "fallback": "bambu_studio", "message": "Bambu control needs address, access code, and serial.",
                "limits": BAMBU_LIMITS, **_v(ptype="bambu")}
    if (os.environ.get("ZEIM_BAMBU_MOCK") or "").lower() in ("1", "true", "yes"):
        return {"ok": True, "action": action, "message": f"Simulated Bambu {action}.", **_v(ptype="bambu"), "limits": BAMBU_LIMITS}
    cmd = {"pause": "pause", "resume": "resume", "cancel": "stop"}[action]
    try:
        _bambu_mqtt_cmd(host, code, serial, cmd)
        return {"ok": True, "action": action,
                "message": f"Bambu accepted {action} (Simulated path; not confirmed. Needs Developer Mode).",
                **_v(ptype="bambu"), "limits": BAMBU_LIMITS}
    except Exception as e:
        return {"ok": False, "fallback": "bambu_studio",
                "message": f"Bambu {action} failed ({e}). Use Bambu Studio. Needs Developer Mode.",
                "limits": BAMBU_LIMITS, **_v(ptype="bambu")}


def _bambu_mqtt_cmd(host: str, code: str, serial: str, cmd: str) -> None:
    ctx = ssl._create_unverified_context()
    raw = socket.create_connection((host, 8883), timeout=15)
    sock = ctx.wrap_socket(raw, server_hostname=host)
    try:
        client_id = "zeim" + os.urandom(3).hex()
        vh = b"\x00\x04MQTT\x04\xc2\x00\x3c"
        payload = _mqtt_encode_str(client_id) + _mqtt_encode_str("bblp") + _mqtt_encode_str(code)
        body = vh + payload
        sock.sendall(bytes([0x10, len(body)]) + body)
        ack = sock.recv(4)
        if len(ack) < 4 or ack[0] != 0x20 or ack[3] != 0:
            raise RuntimeError("MQTT CONNACK refused (is Developer Mode on?)")
        topic = f"device/{serial}/request"
        msg = json.dumps({"print": {"command": cmd, "param": ""}})
        t_b, m_b = topic.encode(), msg.encode()
        pub = struct.pack("!H", len(t_b)) + t_b + m_b
        rl = len(pub)
        sock.sendall((bytes([0x30, rl]) if rl < 128 else bytes([0x30, (rl & 0x7F) | 0x80, rl >> 7])) + pub)
    finally:
        try:
            sock.close()
        except Exception:
            pass
