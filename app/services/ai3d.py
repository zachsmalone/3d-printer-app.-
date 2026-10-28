"""2D->3D engine client, plan gate, daily cap and cooldown.

The engine is a separate worker (workers/ai3d, TripoSR). ZEIM sends it the cleaned photo (EXIF/GPS already removed) over
the local Docker network and gets a mesh back. Nothing goes to any outside service. Photo prep runs first
(workers/ai3d/prep.py). When the worker is up, prep uses its cut-out; otherwise ZEIM prepares the photo itself.

Plan: Pro after launch (ZEIM_AI3D_PRO_ONLY=1). While testing: unlocked for every adult account, capped per day.
Cooldown (Zach, flat 5 minutes): 5 minutes between models, starting when a conversion FINISHES. Editing, exporting,
or sending that mesh on does not start it again. ZEIM_AI3D_COOLDOWN_STEP_MIN stays 0 unless an operator sets it.
ZEIM_TESTING_MODE=1 lifts the cooldown (and the Pro-only gate).
The daily model cap stays unless ZEIM_TESTING_ALLOW_PAID=1, because each model uses the worker.
Neither flag starts a payment. Tests swap engine_call for a double.
"""
from __future__ import annotations

import base64
import json
import threading
import time
import urllib.error
import urllib.request
import uuid

from .. import config
from ..core.ai3d_prep import prepare_image

_lock = threading.Lock()
_last_done: dict[str, float] = {}           # sid -> time the last model finished
_paid_today: dict[str, tuple[str, int]] = {}  # sid -> (day, paid models)
_made_today: dict[str, tuple[str, int]] = {}  # sid -> (day, models)
JOBS: dict[str, dict] = {}


class EngineMissing(RuntimeError):
    pass


class EngineError(RuntimeError):
    pass


def _day(now=None) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(now or time.time()))


def engine_status() -> dict:
    """{'installed': bool, 'ready': bool, 'device': ..., 'test_double': bool}. Never raises."""
    if not config.ai3d_enabled():
        return {"installed": False, "ready": False, "device": None, "engine": "TripoSR", "test_double": False}
    if config.AI3D_FAKE:
        return {"installed": True, "ready": True, "device": "test double", "engine": "test double", "test_double": True}
    if not config.AI3D_URL:
        return {"installed": False, "ready": False, "device": None, "engine": "TripoSR", "test_double": False}
    try:
        with urllib.request.urlopen(config.AI3D_URL + "/health", timeout=3) as r:
            j = json.loads(r.read().decode())
        return {"installed": True, "ready": bool(j.get("ready")), "device": j.get("device"), "busy": bool(j.get("busy")),
                "engine": j.get("engine", "TripoSR"), "test_double": False}
    except Exception:
        return {"installed": True, "ready": False, "device": None, "engine": "TripoSR", "test_double": False, "unreachable": True}


def _prep_headers(mode: str, *, crop: bool, tone: bool, grey: bool, prepared: bool = False, resolution: int | None = None) -> dict:
    headers = {"Content-Type": "application/octet-stream", "X-Mode": mode, "X-Token": config.AI3D_TOKEN,
               "X-Prep-Crop": "1" if crop else "0", "X-Prep-Tone": "1" if tone else "0",
               "X-Prep-Bg": "grey" if grey else "keep", "X-Prepared": "1" if prepared else "0"}
    if resolution is not None:
        headers["X-Resolution"] = str(resolution)
    return headers


def prepare_photo(image: bytes, mode: str, *, crop: bool = True, tone: bool = True, grey: bool = True) -> tuple[bytes, list[str]]:
    """Bytes the engine should see, plus short notes. Worker cut-out when it answers; local prep otherwise."""
    if not config.AI3D_FAKE and config.AI3D_URL and config.ai3d_enabled():
        try:
            return _worker_prepare(image, mode, crop=crop, tone=tone, grey=grey)
        except Exception:
            png, notes = prepare_image(image, mode, crop=crop, tone=tone, grey=grey)
            return png, list(notes) + ["The engine did not prepare the photo, so this crop and light were used."]
    return prepare_image(image, mode, crop=crop, tone=tone, grey=grey)


def _worker_prepare(image: bytes, mode: str, *, crop: bool, tone: bool, grey: bool) -> tuple[bytes, list[str]]:
    req = urllib.request.Request(
        config.AI3D_URL + "/prepare", data=image, method="POST",
        headers=_prep_headers(mode, crop=crop, tone=tone, grey=grey))
    try:
        with urllib.request.urlopen(req, timeout=min(180, config.AI3D_TIMEOUT_S)) as r:
            body = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise EngineError("The engine could not prepare this photo.") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise EngineMissing("The 2D to 3D engine is not answering.") from e
    try:
        png = base64.b64decode(body.get("png_b64") or "")
    except Exception as e:
        raise EngineError("The engine could not prepare this photo.") from e
    if not png:
        raise EngineError("The engine could not prepare this photo.")
    notes = [str(n) for n in (body.get("notes") or []) if str(n).strip()]
    return png, notes


def engine_call(image: bytes, mode: str, resolution: int = 192, *, prepared: bool = False,
                crop: bool = True, tone: bool = True, grey: bool = True) -> bytes:
    """Photo bytes -> PLY bytes from the worker. Refuses while ZEIM_2D3D_ENABLED is off.

    prepared=True means ZEIM already ran photo prep, so the worker must not crop or cut the subject out again.
    """
    if not config.ai3d_enabled():
        raise EngineMissing("2D to 3D is not available yet.")
    if config.AI3D_FAKE:
        from ..core.ai3d_mesh import fake_engine_mesh
        time.sleep(0.4)
        return fake_engine_mesh(mode)
    if not config.AI3D_URL:
        raise EngineMissing("The 2D to 3D engine is not installed on this server.")
    req = urllib.request.Request(
        config.AI3D_URL + "/generate", data=image, method="POST",
        headers=_prep_headers(mode, crop=crop, tone=tone, grey=grey, prepared=prepared, resolution=resolution))
    try:
        with urllib.request.urlopen(req, timeout=config.AI3D_TIMEOUT_S) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("error")
        except Exception:
            msg = None
        raise EngineError(msg or "The engine could not make a model from this photo.")
    except (urllib.error.URLError, TimeoutError, OSError):
        raise EngineMissing("The 2D to 3D engine is not answering. It may be starting up or not installed.")


def is_pro(actor) -> bool:
    u = actor.user or {}
    return str(u.get("plan", "")).lower() == "pro"


def plan(actor) -> dict:
    """What this account may do right now (shown in the tab; enforced in start())."""
    if not config.ai3d_enabled():
        return {"allowed": False, "reason": "unavailable", "phase": "off", "wait_s": 0,
                "cap": 0, "used_today": 0, "testing_mode": False, "allow_paid": False}
    now = time.time()
    sid = actor.sid
    testing = bool(config.TESTING_MODE)
    allow_paid = bool(testing and config.TESTING_ALLOW_PAID)
    if config.AI3D_PRO_ONLY and not is_pro(actor) and not testing:
        return {"allowed": False, "reason": "pro", "phase": "pro", "wait_s": 0, "cap": 0, "used_today": 0,
                "testing_mode": False, "allow_paid": False}
    day = _day(now)
    used = _made_today.get(sid, ("", 0)); used = used[1] if used[0] == day else 0
    paid = _paid_today.get(sid, ("", 0)); paid = paid[1] if paid[0] == day else 0
    # Testing mode lifts the pause. The daily count stays, unless the separate paid flag is on,
    # because each model uses GPU time on the worker. Pro-only with testing mode off still has no daily cap.
    if allow_paid or (config.AI3D_PRO_ONLY and is_pro(actor) and not testing):
        cap = 0
    else:
        cap = config.AI3D_DAILY_CAP
    wait_min = 0 if testing else config.AI3D_COOLDOWN_MIN + config.AI3D_COOLDOWN_STEP_MIN * paid
    last = _last_done.get(sid)
    wait_s = 0 if testing else (max(0, int(round(last + wait_min * 60 - now))) if last else 0)
    p = {"allowed": True, "testing_mode": testing, "allow_paid": allow_paid, "cap": cap, "used_today": used,
         "wait_s": wait_s, "cooldown_min": wait_min,
         "phase": "testing" if testing or not config.AI3D_PRO_ONLY else "pro"}
    if cap and used >= cap:
        p.update(allowed=False, reason="cap")
    elif wait_s > 0:
        p.update(allowed=False, reason="cooldown")
    return p


def mark_done(actor, now=None):
    """A model finished converting: start the cooldown and count it."""
    now = now or time.time()
    with _lock:
        _last_done[actor.sid] = now
        d = _day(now)
        c = _made_today.get(actor.sid, ("", 0)); _made_today[actor.sid] = (d, (c[1] if c[0] == d else 0) + 1)
        if config.AI3D_PRO_ONLY and is_pro(actor):
            p = _paid_today.get(actor.sid, ("", 0)); _paid_today[actor.sid] = (d, (p[1] if p[0] == d else 0) + 1)


def reset():
    with _lock:
        _last_done.clear(); _paid_today.clear(); _made_today.clear(); JOBS.clear()


def busy(sid: str) -> bool:
    return any(j["sid"] == sid and j["state"] == "running" for j in JOBS.values())


def new_job(sid: str) -> dict:
    j = {"id": uuid.uuid4().hex[:12], "sid": sid, "state": "running", "started": time.time(), "result": None, "error": None}
    with _lock:
        for k in [k for k, v in JOBS.items() if time.time() - v["started"] > 6 * 3600]:
            JOBS.pop(k, None)
        JOBS[j["id"]] = j
    return j
