"""Mounting passkey login for local/pilot: auto-on for localhost / ZEIM_ENV=dev, refuse weak
secrets outside that without crashing the app, legacy cookie accounts keep their id."""
from __future__ import annotations

import logging
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.config import AuthConfig, ConfigError
from app.api.auth import _auth_env, legacy_cookie_resolver, try_mount_auth


def test_dev_env_fills_local_defaults(monkeypatch):
    monkeypatch.setenv("ZEIM_ENV", "dev")
    for k in ("ZEIM_RP_ID", "ZEIM_ORIGINS", "ZEIM_AUTH_PEPPER", "ZEIM_INSECURE_COOKIES"):
        monkeypatch.delenv(k, raising=False)
    env = _auth_env()
    cfg = AuthConfig.from_env(env)
    assert cfg.rp_id == "localhost"
    assert any(o.startswith("http://localhost:") for o in cfg.origins)
    assert cfg.cookie_name == "zeim_session"          # insecure cookies on in local/dev
    assert len(cfg.pepper) >= 32


def test_production_still_refuses_weak_or_missing_secrets(monkeypatch):
    monkeypatch.delenv("ZEIM_ENV", raising=False)
    monkeypatch.setenv("ZEIM_RP_ID", "zeim.example")
    monkeypatch.setenv("ZEIM_ORIGINS", "https://zeim.example")
    monkeypatch.setenv("ZEIM_AUTH_PEPPER", "short")    # too short
    with pytest.raises(ConfigError):
        AuthConfig.from_env(os.environ)
    monkeypatch.setenv("ZEIM_AUTH_PEPPER", "x" * 32)
    monkeypatch.setenv("ZEIM_ORIGINS", "http://zeim.example")   # http outside dev
    with pytest.raises(ConfigError):
        AuthConfig.from_env(os.environ)


def test_try_mount_skips_without_crash_when_secrets_missing(monkeypatch, caplog):
    """Non-loopback + no ZEIM_ENV=dev + no secrets => warning, old login stays, app lives."""
    import app.config as config
    monkeypatch.setattr(config, "HOST", "0.0.0.0")
    monkeypatch.delenv("ZEIM_ENV", raising=False)
    for k in ("ZEIM_RP_ID", "ZEIM_ORIGINS", "ZEIM_AUTH_PEPPER"):
        monkeypatch.delenv(k, raising=False)
    app = FastAPI()
    with caplog.at_level(logging.WARNING, logger="zeim.auth"):
        assert try_mount_auth(app) is False
    assert app.state.auth_mounted is False
    assert any("passkey/email login is OFF" in r.message for r in caplog.records)
    # no /api/auth routes
    paths = {getattr(r, "path", None) for r in app.routes}
    assert not any(isinstance(p, str) and p.startswith("/api/auth") for p in paths)


def test_try_mount_on_loopback_uses_dev_defaults(monkeypatch, tmp_path):
    import app.config as config
    monkeypatch.setattr(config, "HOST", "127.0.0.1")
    monkeypatch.setattr(config, "PORT", 8765)
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.delenv("ZEIM_ENV", raising=False)
    for k in ("ZEIM_RP_ID", "ZEIM_ORIGINS", "ZEIM_AUTH_PEPPER", "ZEIM_AUTH_DB"):
        monkeypatch.delenv(k, raising=False)
    app = FastAPI()
    assert try_mount_auth(app) is True
    assert app.state.auth_mounted is True
    c = TestClient(app, base_url="http://127.0.0.1:8765")
    r = c.get("/api/auth/session")
    assert r.status_code == 200 and r.json() == {"signed_in": False}


def test_main_app_has_auth_routes_on_localhost():
    """Importing app.main on this box (HOST defaults to 127.0.0.1) should have mounted auth."""
    from app.main import app
    assert getattr(app.state, "auth_mounted", False) is True
    c = TestClient(app)
    assert c.get("/api/auth/session").status_code == 200


def test_legacy_resolver_returns_account_id_and_name(tmp_path, monkeypatch):
    """Cookie account -> (user id, display name) so owner_id stays the legacy id after upgrade."""
    os.environ.setdefault("PHOTO3D_DATA", str(tmp_path / "data"))
    os.environ.setdefault("PHOTO3D_OUT", str(tmp_path / "out"))
    from app.community import identity as idn
    from app.community.store import USERS
    from starlette.requests import Request

    sid = "a" * 24
    USERS.update(lambda d: d.__setitem__(sid, {"id": "abc123", "display_name": "Old Sam", "dob": "1990-01-01"}))

    scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "client": ("127.0.0.1", 0)}
    req = Request(scope)
    req._cookies = {idn.COOKIE: sid}          # type: ignore[attr-defined]
    # Request.cookies is a property over the header; set Cookie header instead
    scope["headers"] = [(b"cookie", f"{idn.COOKIE}={sid}".encode())]
    req = Request(scope)
    assert legacy_cookie_resolver(req) == ("abc123", "Old Sam")
    assert legacy_cookie_resolver(Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": ("127.0.0.1", 0)})) is None


def test_legacy_upgrade_keeps_owner_id_through_real_resolver():
    """legacy_cookie_resolver + add-passkey keeps SessionInfo.owner_id == the cookie account id."""
    from app.api.auth import init_auth, router
    from app.community import identity as idn
    from app.community.store import USERS
    from tests.auth_helpers import SoftKey, make_service

    sid = "c" * 24
    USERS.update(lambda d: d.__setitem__(sid, {"id": "legacy99", "display_name": "Old Sam", "dob": "1990-01-01"}))
    app = FastAPI()
    svc = make_service()
    init_auth(app, service=svc, legacy_resolver=legacy_cookie_resolver)
    app.include_router(router)
    c = TestClient(app, base_url="https://zeim.test")
    c.cookies.set(idn.COOKIE, sid)
    H = {"X-Requested-With": "zeim", "Origin": "https://zeim.test"}
    key = SoftKey()
    b = c.post("/api/auth/passkeys/begin", headers=H)
    assert b.status_code == 200, b.text
    r = c.post("/api/auth/passkeys/finish",
               json={"ceremony_id": b.json()["ceremony_id"],
                     "credential": key.register(b.json()["options"]), "name": "phone"},
               headers=H)
    assert r.status_code == 201, r.text
    tok = r.cookies.get("__Host-zeim_session") or c.cookies.get("__Host-zeim_session")
    assert tok and svc.resolve_session(tok).owner_id == "legacy99"
