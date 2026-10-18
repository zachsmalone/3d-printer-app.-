"""SQLite storage backend (ZEIM_STORAGE=db).

One database file (DATA/zeim.sqlite3) holds the community document stores and
build metadata. The passkey/email auth accounts keep their own database
(ZEIM_AUTH_DB, default data/auth.sqlite3): the two are bridged at signup, where
the auth layer creates the matching community account — this module deliberately
does NOT create a second account system.

Design rules:
  * one source of truth — in db mode a failed DB operation raises; code must
    never silently fall back to writing JSON;
  * atomic read-modify-write — every mutation runs inside BEGIN IMMEDIATE so
    concurrent workers serialize on the write lock instead of losing updates
    (the JSON mode process-level RLock cannot protect multiple processes);
  * WAL journal + busy_timeout so readers never block writers.

The auth SQLite store (app/auth/store.py) follows the same rules and stays
untouched by this module.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from . import config

_LOCK = threading.RLock()
_TX_LOCK = threading.RLock()      # serializes transactions within this process; BEGIN IMMEDIATE
_CONNS: dict[str, sqlite3.Connection] = {}   # serializes them across processes

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents(
    name       TEXT PRIMARY KEY,
    doc        TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS builds(
    id         TEXT PRIMARY KEY,
    owner_sid  TEXT,
    visibility TEXT NOT NULL DEFAULT 'private',
    created    TEXT NOT NULL,
    favorite   INTEGER NOT NULL DEFAULT 0,
    saved      INTEGER NOT NULL DEFAULT 0,
    payload    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_builds_owner ON builds(owner_sid, created);
CREATE INDEX IF NOT EXISTS idx_builds_visibility ON builds(visibility);
"""


def db_path() -> Path:
    """Database location, read from the live config so tests can redirect it."""
    return Path(config.DATA) / "zeim.sqlite3"


def conn() -> sqlite3.Connection:
    """Connection for the current DATA dir (cached per path; thread-safe)."""
    path = db_path()
    key = str(path)
    with _LOCK:
        c = _CONNS.get(key)
        if c is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            c = sqlite3.connect(key, timeout=30, check_same_thread=False)
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=30000")
            c.execute("PRAGMA synchronous=NORMAL")
            c.executescript(_SCHEMA)
            c.commit()
            _CONNS[key] = c
        return c


def reset() -> None:
    """Close and forget cached connections (tests only)."""
    with _LOCK:
        for c in _CONNS.values():
            try:
                c.close()
            except Exception:
                pass
        _CONNS.clear()


# --- document store (backs app/community/store.py JsonFile in db mode) ---

def doc_read(name: str, default):
    row = conn().execute("SELECT doc FROM documents WHERE name=?", (name,)).fetchone()
    if row is None:
        return json.loads(json.dumps(default))
    return json.loads(row[0])


def doc_write(name: str, data) -> None:
    c = conn()
    c.execute(
        "INSERT INTO documents(name, doc, updated_at) VALUES(?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET doc=excluded.doc, updated_at=excluded.updated_at",
        (name, json.dumps(data, default=str), time.time()),
    )
    c.commit()


def doc_update(name: str, default, fn):
    """Atomic read-modify-write: the whole mutation is one transaction."""
    c = conn()
    with _TX_LOCK:
        c.execute("BEGIN IMMEDIATE")
        try:
            row = c.execute("SELECT doc FROM documents WHERE name=?", (name,)).fetchone()
            d = json.loads(row[0]) if row is not None else json.loads(json.dumps(default))
            result = fn(d)
            c.execute(
                "INSERT INTO documents(name, doc, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET doc=excluded.doc, updated_at=excluded.updated_at",
                (name, json.dumps(d, default=str), time.time()),
            )
            c.commit()
            return result
        except Exception:
            c.rollback()
            raise


# --- build metadata (backs app/services/history.py BuildStore in db mode) ---

_BUILD_COLS = "id, owner_sid, visibility, created, favorite, saved, payload"


def _row_to_meta(row) -> dict:
    meta = json.loads(row[6])
    meta["favorite"] = bool(row[4])
    meta["saved"] = bool(row[5])
    return meta


def _meta_to_row(meta: dict) -> tuple:
    return (
        meta["id"], meta.get("owner_sid"), meta.get("visibility", "private"),
        meta.get("created", ""), int(bool(meta.get("favorite"))), int(bool(meta.get("saved"))),
        json.dumps(meta, default=str),
    )


def build_list(owner: str | None = None) -> list[dict]:
    c = conn()
    if owner is None:
        rows = c.execute(f"SELECT {_BUILD_COLS} FROM builds ORDER BY created").fetchall()
    else:
        rows = c.execute(
            f"SELECT {_BUILD_COLS} FROM builds WHERE owner_sid=? ORDER BY created", (owner,)
        ).fetchall()
    return [_row_to_meta(r) for r in rows]


def build_get(bid: str) -> dict | None:
    row = conn().execute(f"SELECT {_BUILD_COLS} FROM builds WHERE id=?", (bid,)).fetchone()
    return _row_to_meta(row) if row else None


def build_save(meta: dict) -> None:
    c = conn()
    c.execute(
        "INSERT INTO builds(id, owner_sid, visibility, created, favorite, saved, payload) "
        "VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET owner_sid=excluded.owner_sid, "
        "visibility=excluded.visibility, created=excluded.created, favorite=excluded.favorite, "
        "saved=excluded.saved, payload=excluded.payload",
        _meta_to_row(meta),
    )
    c.commit()


def build_delete(bid: str) -> None:
    c = conn()
    c.execute("DELETE FROM builds WHERE id=?", (bid,))
    c.commit()


def build_update(bid: str, fn):
    """Atomic read-modify-write on one build's metadata. Returns fn's result."""
    c = conn()
    with _TX_LOCK:
        c.execute("BEGIN IMMEDIATE")
        try:
            row = c.execute(f"SELECT {_BUILD_COLS} FROM builds WHERE id=?", (bid,)).fetchone()
            if row is None:
                raise KeyError(bid)
            meta = _row_to_meta(row)
            result = fn(meta)
            c.execute(
                "INSERT INTO builds(id, owner_sid, visibility, created, favorite, saved, payload) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET owner_sid=excluded.owner_sid, "
                "visibility=excluded.visibility, created=excluded.created, favorite=excluded.favorite, "
                "saved=excluded.saved, payload=excluded.payload",
                _meta_to_row(meta),
            )
            c.commit()
            return result
        except Exception:
            c.rollback()
            raise


def build_claim_unowned(sid: str) -> int:
    """Give every unowned build to `sid` (single-user-era migration). Returns how many."""
    c = conn()
    with _TX_LOCK:
        c.execute("BEGIN IMMEDIATE")
        try:
            rows = c.execute("SELECT id, payload FROM builds WHERE owner_sid IS NULL OR owner_sid=''").fetchall()
            for bid, payload in rows:
                meta = json.loads(payload)
                meta["owner_sid"] = sid
                meta.setdefault("visibility", "private")
                c.execute(
                    "INSERT INTO builds(id, owner_sid, visibility, created, favorite, saved, payload) "
                    "VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET owner_sid=excluded.owner_sid, "
                    "visibility=excluded.visibility, created=excluded.created, favorite=excluded.favorite, "
                    "saved=excluded.saved, payload=excluded.payload",
                    _meta_to_row(meta),
                )
            c.commit()
            return len(rows)
        except Exception:
            c.rollback()
            raise
