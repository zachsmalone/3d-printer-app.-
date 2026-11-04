"""FEAT5: saved versions of an edit project (a named snapshot of its steps, position and dimensions).

Additive storage only: in db mode a new `build_versions` table (app/db.py); in json mode a new
`versions.json` file in the build folder. Builds themselves are never altered by saving a version.
Restoring first saves the current state as a version, so a restore can always be undone.
"""
from __future__ import annotations

import copy
import json
from collections import OrderedDict
from datetime import datetime, timezone

from .. import config
from ..core import meshedit
from . import editproj
from .history import store

MAX_VERSIONS = 20
LABEL_MAX = 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load(bid: str) -> list[dict]:
    if config.STORAGE_MODE == "db":
        from .. import db
        rows = db.conn().execute("SELECT n, created, label, snapshot FROM build_versions WHERE bid=? ORDER BY n", (bid,)).fetchall()
        return [{"n": r[0], "created": r[1], "label": r[2], "snapshot": json.loads(r[3])} for r in rows]
    f = store.dir(bid) / "versions.json"
    return json.loads(f.read_text()) if f.exists() else []


def _add(bid: str, label: str, snap: dict) -> dict:
    vs = _load(bid)
    if len(vs) >= MAX_VERSIONS:
        raise ValueError(f"This project already has {MAX_VERSIONS} saved versions.")
    v = {"n": (vs[-1]["n"] + 1) if vs else 1, "created": _now(), "label": label, "snapshot": snap}
    if config.STORAGE_MODE == "db":
        from .. import db
        c = db.conn()
        with db._TX_LOCK:
            c.execute("INSERT INTO build_versions(bid, n, created, label, snapshot) VALUES(?,?,?,?,?)",
                      (bid, v["n"], v["created"], label, json.dumps(snap)))
            c.commit()
    else:
        f = store.dir(bid) / "versions.json"
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(vs + [v]))
        tmp.replace(f)
    return v


def _snap(meta: dict) -> dict:
    return {"ops": copy.deepcopy(meta.get("ops") or []), "head": int(meta.get("head") or 0),
            "dims": copy.deepcopy(meta.get("dims") or {})}


def _public(v: dict) -> dict:
    s = v["snapshot"]
    return {"n": v["n"], "created": v["created"], "label": v["label"], "steps": len(s["ops"]), "head": s["head"]}


def list_versions(bid: str) -> list[dict]:
    return [_public(v) for v in _load(bid)]


def save(bid: str, label: str) -> dict:
    label = (label or "").strip()[:LABEL_MAX]
    if "<" in label or ">" in label:
        raise ValueError("A version name can't contain < or >.")
    if label:
        from ..community import safety
        safety.filter_only(label, "Version name")
    with editproj._lock:
        meta = store.get(bid)
        v = _add(bid, label or f"Version {len(_load(bid)) + 1}", _snap(meta))
    return _public(v)


def restore(bid: str, n: int) -> dict:
    with editproj._lock:
        v = next((x for x in _load(bid) if x["n"] == n), None)
        if v is None:
            raise meshedit.OpError("no such version")
        meta = store.get(bid)
        _add(bid, f"Before restoring “{v['label']}”"[:LABEL_MAX], _snap(meta))
        s = copy.deepcopy(v["snapshot"])
        old = {k: copy.deepcopy(meta.get(k)) for k in ("ops", "head", "dims")}
        meta["ops"], meta["dims"] = s["ops"], s["dims"]
        editproj._STATES[bid] = OrderedDict()
        meta["last_report"] = None
        try:
            editproj._commit(bid, meta, max(0, min(s["head"], len(s["ops"]))))
        except meshedit.OpError:
            meta.update(old)
            editproj._STATES[bid] = OrderedDict()
            raise
    return _public(v)
