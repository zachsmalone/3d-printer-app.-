"""Local-only personalization ('Picked for you'). Data = tag weights + recent searches per browser,
stored in data/prefs.json. User can view, disable, and clear it at any time."""
from __future__ import annotations

from .store import PREFS

import copy


def _empty():
    return {"enabled": True, "interests": {}, "searches": []}


def get(sid: str) -> dict:
    return {**_empty(), **PREFS.read().get(sid, {})}


def _upd(sid, fn):
    def f(d):
        p = {**_empty(), **d.get(sid, {})}
        if p["enabled"]:
            fn(p)
        d[sid] = p
    PREFS.update(f)


def record_search(sid: str, q: str, tags_known: set[str]):
    def fn(p):
        p["searches"] = ([q] + [s for s in p["searches"] if s != q])[:30]
        for tok in q.lower().split():
            if tok in tags_known:
                p["interests"][tok] = p["interests"].get(tok, 0) + 1.0
    _upd(sid, fn)


def record_view(sid: str, tags: list[str], weight=0.5):
    def fn(p):
        for t in tags:
            p["interests"][t] = p["interests"].get(t, 0) + weight
    _upd(sid, fn)


def set_enabled(sid: str, on: bool):
    def f(d):
        p = {**_empty(), **d.get(sid, {})}
        p["enabled"] = bool(on)
        d[sid] = p
    PREFS.update(f)


def clear(sid: str):
    def f(d):
        en = d.get(sid, {}).get("enabled", True)
        d[sid] = {**_empty(), "enabled": en}
    PREFS.update(f)
