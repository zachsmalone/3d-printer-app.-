"""2D->3D engine client, plan gate, daily cap and cooldown.

The engine is a separate worker (workers/ai3d, TripoSR). ZEIM sends it the cleaned photo (EXIF/GPS already removed) over
the local Docker network and gets a mesh back. Nothing goes to any outside service.

Plan: Pro after launch (ZEIM_AI3D_PRO_ONLY=1). While testing: unlocked for every adult account, capped per day.
Cooldown (Zach, 2026-10-20): 5 minutes between models, starting when a model FINISHES (tweaks never count), plus 5 more
after each paid model that day. ZEIM_TESTING_MODE=1 lifts the cap and the cooldown. Tests swap engine_call for a double.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
import uuid

from .. import config
from .subscriptions import has_paid_plan

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


def engine_call(image: bytes, mode: str, resolution: int = 192) -> bytes:
    """Photo bytes -> PLY bytes from the worker."""
    if config.AI3D_FAKE:
        from ..core.ai3d_mesh import fake_engine_mesh
        time.sleep(0.4)
        return fake_engine_mesh(mode)
    if not config.AI3D_URL:
        raise EngineMissing("The 2D to 3D engine is not installed on this server.")
    req = urllib.request.Request(config.AI3D_URL + "/generate", data=image, method="POST",
                                 headers={"Content-Type": "application/octet-stream", "X-Mode": mode,
                                          "X-Resolution": str(resolution), "X-Token": config.AI3D_TOKEN})
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
    """Pro gate. `plan` is written by Stripe webhooks, not by the browser."""
    return has_paid_plan(actor.user, "pro")


def plan(actor) -> dict:
    """What this account may do right now (shown in the tab; enforced in start())."""
    now = time.time()
    sid = actor.sid
    if config.TESTING_MODE:
        return {"allowed": True, "testing_mode": True, "cap": 0, "used_today": 0, "wait_s": 0, "phase": "testing"}
    if config.AI3D_PRO_ONLY and not is_pro(actor):
        return {"allowed": False, "reason": "pro", "phase": "pro", "wait_s": 0, "cap": 0, "used_today": 0, "testing_mode": False}
    day = _day(now)
    used = _made_today.get(sid, ("", 0)); used = used[1] if used[0] == day else 0
    paid = _paid_today.get(sid, ("", 0)); paid = paid[1] if paid[0] == day else 0
    cap = 0 if config.AI3D_PRO_ONLY else config.AI3D_DAILY_CAP
    wait_min = config.AI3D_COOLDOWN_MIN + config.AI3D_COOLDOWN_STEP_MIN * paid
    last = _last_done.get(sid)
    wait_s = max(0, int(round(last + wait_min * 60 - now))) if last else 0
    p = {"allowed": True, "testing_mode": False, "cap": cap, "used_today": used, "wait_s": wait_s,
         "cooldown_min": wait_min, "phase": "pro" if config.AI3D_PRO_ONLY else "testing"}
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
