"""User settings (printers, default slicer, public URL). JSON on disk.

Future: per-user settings move to a profile store; keep access behind these functions.
"""
from __future__ import annotations

import json
import threading
import uuid

from .. import config
from . import printers as printers_mod
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


def base_url(request) -> str:
    """The URL used in join QR codes and slicer links: deployment setting (env) > admin-saved setting > this request's host."""
    return config.PUBLIC_BASE_URL or load().get("public_base_url") or str(request.base_url).rstrip("/")


def public(s: dict | None = None, redact: bool = False) -> dict:
    """Settings safe to send to the browser (API keys masked). `redact=True` (visitors without settings rights in
    shared mode, and class students) also hides printer addresses."""
    s = json.loads(json.dumps(s or load()))
    for p in s["printers"]:
        p["has_key"] = bool(p.get("api_key"))
        p.pop("api_key", None)
        if redact:
            p.pop("url", None)
    if config.PUBLIC_BASE_URL:
        s["public_base_url"] = config.PUBLIC_BASE_URL
    s["public_base_url_locked"] = bool(config.PUBLIC_BASE_URL)
    return s


def clean_base_url(v) -> str:
    """Validate the public base URL an admin types in: http(s), a host, nothing else (no credentials/path/query)."""
    from urllib.parse import urlsplit
    v = (v or "").strip().rstrip("/")
    if not v:
        return ""
    if len(v) > 200:
        raise ValueError("Public base URL is too long.")
    u = urlsplit(v)
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.path or u.query or u.fragment:
        raise ValueError("Public base URL must look like https://zeim.example.org (http or https, host and optional port only).")
    try:
        u.port
    except ValueError:
        raise ValueError("Public base URL has an invalid port.")
    return v


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
        if q.get("url") and q.get("type") in printers_mod.IMPLEMENTED and not str(q["url"]).lower().startswith(("http://", "https://")):
            raise ValueError("Printer address must start with http:// or https://")
        q["bed_x"] = float(q.get("bed_x") or 250)
        q["bed_y"] = float(q.get("bed_y") or 210)
        printers.append(q)
    new = {"public_base_url": cur.get("public_base_url", "") if config.PUBLIC_BASE_URL else clean_base_url(incoming.get("public_base_url")),
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
