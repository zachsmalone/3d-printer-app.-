"""SQLite storage for accounts, passkeys, sessions, ceremonies, email codes and rate-limit events.

Everything sensitive is stored hashed: session tokens (SHA-256), emails (keyed HMAC + masked hint),
email codes (keyed HMAC with per-code salt). Passkeys store only the *public* key.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts(
  id TEXT PRIMARY KEY,
  legacy_id TEXT UNIQUE,             -- id of the pre-login anonymous account this one upgraded, if any
  display_name TEXT NOT NULL DEFAULT '',
  email_hash TEXT UNIQUE,            -- HMAC(pepper, email); the address itself is never stored
  email_hint TEXT,                   -- j***@e***.com
  email_verified_at REAL,
  login_name TEXT,                   -- lowercase username for password sign-in; NULL until a password exists
  password_hash TEXT,                -- Argon2id hash only; the password is never stored
  password_set_at REAL,
  created_at REAL NOT NULL,
  disabled_at REAL
);
CREATE TABLE IF NOT EXISTS credentials(
  id TEXT PRIMARY KEY,               -- WebAuthn credential id, base64url
  account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  public_key BLOB NOT NULL,
  sign_count INTEGER NOT NULL DEFAULT 0,
  transports TEXT NOT NULL DEFAULT '',
  name TEXT NOT NULL DEFAULT 'Passkey',
  device_type TEXT NOT NULL DEFAULT '',
  backed_up INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  last_used_at REAL
);
CREATE INDEX IF NOT EXISTS credentials_account ON credentials(account_id);
CREATE TABLE IF NOT EXISTS sessions(
  id TEXT PRIMARY KEY,               -- public id shown in the device list (not the secret)
  account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,   -- SHA-256 of the cookie value
  created_at REAL NOT NULL,
  last_seen_at REAL NOT NULL,
  authed_at REAL NOT NULL,           -- when the person last proved who they are
  idle_expires_at REAL NOT NULL,
  abs_expires_at REAL NOT NULL,
  label TEXT NOT NULL DEFAULT '',
  auth_method TEXT NOT NULL DEFAULT '',
  revoked_at REAL
);
CREATE INDEX IF NOT EXISTS sessions_account ON sessions(account_id);
CREATE TABLE IF NOT EXISTS ceremonies(
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  challenge BLOB NOT NULL,
  account_id TEXT,
  payload TEXT,
  expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS email_codes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  purpose TEXT NOT NULL,             -- 'login' | 'add'
  email_hash TEXT NOT NULL,
  account_id TEXT,
  salt TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  used_at REAL
);
CREATE INDEX IF NOT EXISTS email_codes_lookup ON email_codes(purpose, email_hash);
CREATE TABLE IF NOT EXISTS rate_events(key TEXT NOT NULL, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS rate_events_key ON rate_events(key, ts);
"""


class AuthStore:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        if path != ":memory:":
            self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self._migrate()
        if path != ":memory:":
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass

    def _migrate(self) -> None:
        """Add password columns to an auth database created before passwords existed.

        CREATE TABLE IF NOT EXISTS does not alter an old table. Existing accounts
        (including passkey-only ones) are left in place; the new columns stay NULL
        until that person sets a password.
        """
        have = {row["name"] for row in self._db.execute("PRAGMA table_info(accounts)")}
        for name, typ in (("login_name", "TEXT"), ("password_hash", "TEXT"), ("password_set_at", "REAL")):
            if name not in have:
                self._db.execute(f"ALTER TABLE accounts ADD COLUMN {name} {typ}")
        self._db.execute("CREATE UNIQUE INDEX IF NOT EXISTS accounts_login_name ON accounts(login_name)")

    @contextmanager
    def tx(self):
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield self
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            else:
                self._db.execute("COMMIT")

    def run(self, sql: str, params: tuple = ()) -> int:
        with self._lock:
            return self._db.execute(sql, params).rowcount

    def one(self, sql: str, params: tuple = ()):
        with self._lock:
            return self._db.execute(sql, params).fetchone()

    def all(self, sql: str, params: tuple = ()):
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    def dump_text(self) -> str:
        """Everything in the DB as one string (used by tests to prove no plaintext secrets are stored)."""
        with self._lock:
            return "\n".join(self._db.iterdump())

    def close(self):
        with self._lock:
            self._db.close()
