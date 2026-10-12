"""Helpers for builds / lesson checklist that belong to a browser session (moved out of the removed classrooms module, 2026-10-12)."""
from __future__ import annotations


def purge_builds(sid: str) -> int:
    """Delete every build / Edit project (source photo included) that this browser session owns. Returns how many."""
    from ..services.history import store
    n = 0
    for m in store.list(sid):
        store.delete(m["id"]); n += 1
    return n


def move_owner(old: str, new: str):
    """Builds/Edit projects + lesson checklist follow an account to its new browser session."""
    from ..services.history import store
    from .store import PROGRESS
    with store.lock:
        for m in store.list(old):
            m["owner_sid"] = new
            store.save(m)

    def f(d):
        if old in d:
            d[new] = d.pop(old)
    PROGRESS.update(f)
