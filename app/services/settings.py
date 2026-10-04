"""User settings (printers, default slicer, public URL). JSON on disk.

Future: per-user settings move to a profile store; keep access behind these functions.
"""
from __future__ import annotations

import json
import threading
import uuid

from ..config import DATA

FILE = DATA / "settings.json"
_lock = threading.Lock()
DEFAULTS = {"public_base_url": "", "default_slicer": "prusaslicer", "printers": []}
PRINTER_FIELDS = ("name", "type", "url", "api_key", "bed_x", "bed_y")


def load() -> dict:
    with _lock:
        if FILE.exists():
            try:
                return {**DEFAULTS, **json.loads(FILE.read_text())}
            except Exception:
                pass
        return json.loads(json.dumps(DEFAULTS))


def public(s: dict | None = None) -> dict:
    """Settings safe to send to the browser (API keys masked)."""
    s = json.loads(json.dumps(s or load()))
    for p in s["printers"]:
        p["has_key"] = bool(p.get("api_key"))
        p.pop("api_key", None)
    return s


def save_from_client(incoming: dict) -> dict:
    cur = load()
    old = {p["id"]: p for p in cur["printers"]}
    printers = []
    for p in incoming.get("printers", []):
        pid = p.get("id") or uuid.uuid4().hex[:8]
        q = {k: p.get(k) for k in PRINTER_FIELDS}
        q["id"] = pid
        if not q.get("api_key"):  # blank = keep stored key
            q["api_key"] = old.get(pid, {}).get("api_key", "")
        q["bed_x"] = float(q.get("bed_x") or 250)
        q["bed_y"] = float(q.get("bed_y") or 210)
        printers.append(q)
    new = {"public_base_url": (incoming.get("public_base_url") or "").rstrip("/"),
           "default_slicer": incoming.get("default_slicer") or "prusaslicer",
           "printers": printers}
    with _lock:
        FILE.write_text(json.dumps(new, indent=2))
        try:
            FILE.chmod(0o600)
        except OSError:
            pass
    return new


def get_printer(pid: str) -> dict | None:
    return next((p for p in load()["printers"] if p["id"] == pid), None)
