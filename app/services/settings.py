"""User settings (printers, default slicer, public URL). JSON on disk.

Future: per-user settings move to a profile store; keep access behind these functions.
"""
from __future__ import annotations

import json
import threading
import uuid

from .. import config
from . import netguard, printers as printers_mod
from ..config import DATA

FILE = DATA / "settings.json"
KEYFILE = DATA / ".settings.key"
ENC_PREFIX = "enc:v1:"
_lock = threading.Lock()
SLICER_CHOICES = ("auto", "creality", "prusaslicer", "bambustudio", "orcaslicer", "cura")   # "auto": Creality Print / Cloud on phones and with a K1, else PrusaSlicer
DEFAULTS = {"public_base_url": "", "default_slicer": "auto", "printers": []}


def effective_slicer(s: dict, phone: bool = False, user_printer: str | None = None) -> str:
    """What 'Default slicer' means right now. 'auto' follows the account printer, phone, or configured printers."""
    v = s.get("default_slicer") or "auto"
    if v != "auto":
        return v if v in SLICER_CHOICES else "prusaslicer"
    if user_printer:
        up = user_printer.lower()
        if "bambu" in up:
            return "bambustudio"
        if "creality" in up or "ender" in up or "k1" in up:
            return "creality"
        if "prusa" in up:
            return "prusaslicer"
    k1 = any(p.get("profile") == "creality_k1" for p in s.get("printers", []))
    return "creality" if (phone or k1) else "prusaslicer"
PRINTER_FIELDS = ("name", "type", "url", "api_key", "bed_x", "bed_y", "profile",
                  "serial", "spool_remaining_g", "alert_done", "alert_failed",
                  "watch_failures", "timelapse")


def _fernet():
    """Printer API keys are stored encrypted (Fernet). Key: env PHOTO3D_SECRET_KEY (a Fernet key) or a random 0600 file next to the
    data. HONEST LIMIT: with the key file on the same disk this protects settings.json when it is copied, backed up, or shown on
    its own - not against someone who owns the whole machine. Put the key in the environment for more."""
    from cryptography.fernet import Fernet
    import os
    k = os.environ.get("PHOTO3D_SECRET_KEY", "").strip()
    if not k:
        if not KEYFILE.exists():
            KEYFILE.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(KEYFILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(Fernet.generate_key().decode())
        k = KEYFILE.read_text().strip()
    return Fernet(k.encode())


def encrypt_secret(v: str) -> str:
    if not v or v.startswith(ENC_PREFIX):
        return v or ""
    return ENC_PREFIX + _fernet().encrypt(v.encode()).decode()


def decrypt_secret(v: str) -> str:
    if not v or not v.startswith(ENC_PREFIX):
        return v or ""          # legacy plain text: still readable, re-written encrypted on the next load()
    from cryptography.fernet import InvalidToken
    try:
        return _fernet().decrypt(v[len(ENC_PREFIX):].encode()).decode()
    except InvalidToken:
        return ""               # wrong/lost key: behave as "no key saved" rather than crash or leak the ciphertext


def _write(d: dict):
    out = json.loads(json.dumps(d))
    for p in out.get("printers", []):
        p["api_key"] = encrypt_secret(p.get("api_key") or "")
    FILE.write_text(json.dumps(out, indent=2))
    try:
        FILE.chmod(0o600)
    except OSError:
        pass


def load() -> dict:
    with _lock:
        if FILE.exists():
            try:
                d = {**DEFAULTS, **json.loads(FILE.read_text())}
            except Exception:
                return json.loads(json.dumps(DEFAULTS))
            legacy = False
            for p in d.get("printers", []):
                k = p.get("api_key") or ""
                if k and not k.startswith(ENC_PREFIX):
                    legacy = True
                p["api_key"] = decrypt_secret(k)
            if legacy:
                try:
                    _write(d)          # migrate plain-text keys in place
                except OSError:
                    pass
            return d
        return json.loads(json.dumps(DEFAULTS))


def base_url(request) -> str:
    """The URL used in join QR codes and slicer links: deployment setting (env) > admin-saved setting > this request's host."""
    return config.PUBLIC_BASE_URL or load().get("public_base_url") or str(request.base_url).rstrip("/")


def trusted_base_url(request) -> str | None:
    """Like base_url(), but NEVER built from a client-supplied Host header unless that header is a loopback name
    (someone browsing on this computer). None = nothing trustworthy is configured: ask an admin to set the public address."""
    configured = config.PUBLIC_BASE_URL or load().get("public_base_url")
    if configured:
        return configured
    host = (request.headers.get("host") or "").strip().lower()
    host = host[1:host.index("]")] if host.startswith("[") and "]" in host else host.split(":")[0]
    if host in config.LOOPBACK_HOSTS or host in config.LOCAL_HOSTS:
        return str(request.base_url).rstrip("/")
    return None


def public(s: dict | None = None, redact: bool = False) -> dict:
    """Settings safe to send to the browser (API keys masked). `redact=True` (visitors without settings rights in
    shared mode) also hides printer addresses."""
    s = json.loads(json.dumps(s or load()))
    for p in s["printers"]:
        p["has_key"] = bool(p.get("api_key"))
        pr = printers_mod.profile_of(p)
        p["experimental"] = bool(pr and pr.get("experimental"))
        p["profile_label"] = pr["label"] if pr else ""
        p.pop("api_key", None)
        if redact:
            p.pop("url", None)
    if config.PUBLIC_BASE_URL:
        s["public_base_url"] = config.PUBLIC_BASE_URL
    s["public_base_url_locked"] = bool(config.PUBLIC_BASE_URL)
    s["direct_control"] = printers_mod.direct_control_enabled()
    s["printer_verification"] = printers_mod.verification_tag()
    s["printer_honesty"] = printers_mod.honesty_note(bool(s.get("printers")))
    s["bambu_limits"] = printers_mod.bambu_limits()
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
        if q.get("url") and q.get("type") in printers_mod.IMPLEMENTED:
            q["url"] = netguard.parse_printer_url(q["url"])          # http(s) only, no credentials, valid port, sane length (every mode)
            if not printers_mod.direct_control_enabled():
                raise ValueError(printers_mod.DIRECT_OFF_MESSAGE)
            denial = printers_mod.shared_mode_denial(q["url"])        # shared mode: no loopback / metadata / private LAN (SSRF)
            if denial:
                raise ValueError(denial)
            printers_mod.check_url(q["url"])
        q["profile"] = q.get("profile") or ""
        if q["profile"] and q["profile"] not in printers_mod.PROFILES:
            raise ValueError("Unknown printer preset.")
        if q["profile"] and printers_mod.PROFILES[q["profile"]]["type"] != q.get("type"):
            raise ValueError(f"The preset '{printers_mod.PROFILES[q['profile']]['label']}' works with {printers_mod.PROFILES[q['profile']]['type']} printers.")
        bx, by = printers_mod.bed_of({**q, "bed_x": q.get("bed_x") or None, "bed_y": q.get("bed_y") or None})
        q["bed_x"], q["bed_y"] = float(bx), float(by)
        q["serial"] = (q.get("serial") or "")[:40]
        try:
            sg = q.get("spool_remaining_g")
            q["spool_remaining_g"] = float(sg) if sg not in (None, "") else None
        except (TypeError, ValueError):
            q["spool_remaining_g"] = None
        for flag in ("alert_done", "alert_failed", "watch_failures", "timelapse"):
            q[flag] = bool(q.get(flag))
        # Keep prior URL when the browser omits it (direct control off / redacted UI).
        if not q.get("url"):
            q["url"] = old.get(pid, {}).get("url", "")
        printers.append(q)
    new = {"public_base_url": cur.get("public_base_url", "") if config.PUBLIC_BASE_URL else clean_base_url(incoming.get("public_base_url")),
           "default_slicer": incoming.get("default_slicer") if incoming.get("default_slicer") in SLICER_CHOICES else "auto",
           "printers": printers}
    with _lock:
        _write(new)
    return new


def get_printer(pid: str) -> dict | None:
    return next((p for p in load()["printers"] if p["id"] == pid), None)
