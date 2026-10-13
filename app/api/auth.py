"""HTTP layer for ZEIM login. Thin on purpose: all rules live in app/auth/service.py (unit-tested).

Wire-up (app/main.py):
    from app.api.auth import router as auth_router, init_auth
    init_auth(app, legacy_resolver=my_legacy_resolver)   # legacy_resolver is optional, see docs/auth.md
    app.include_router(auth_router)
"""
from __future__ import annotations

import os
import re
from typing import Callable, Optional

from fastapi import APIRouter, Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.auth.config import AuthConfig
from app.auth.errors import AuthError, RateLimited
from app.auth.mailer import mailer_from_env
from app.auth.service import AuthService, SessionInfo
from app.auth.store import AuthStore
from app.auth.webauthn_backend import PyWebAuthnBackend

router = APIRouter(prefix="/api/auth", tags=["auth"])
_ID = re.compile(r"^[A-Za-z0-9_\-]{1,512}$")
_NO_STORE = {"Cache-Control": "no-store"}


def init_auth(app: FastAPI, service: Optional[AuthService] = None,
              legacy_resolver: Optional[Callable] = None) -> AuthService:
    """Build the service from environment variables (or accept a ready one, as tests do)."""
    if service is None:
        cfg = AuthConfig.from_env()
        service = AuthService(cfg, AuthStore(cfg.db_path), PyWebAuthnBackend(cfg.rp_id, cfg.rp_name, cfg.origins),
                              mailer_from_env(os.environ))
    app.state.auth_service = service
    app.state.legacy_resolver = legacy_resolver
    return service


# ------------------------------------------------------------------ plumbing
def _svc(request: Request) -> AuthService:
    return request.app.state.auth_service


def _fail(e: AuthError):
    headers = {"Retry-After": str(e.retry_after)} if isinstance(e, RateLimited) else None
    raise HTTPException(status_code=e.status, detail={"code": e.code, "message": e.message}, headers=headers)


def _ip(request: Request) -> str:
    svc = _svc(request)
    if svc.cfg.trust_proxy:                                  # only behind a proxy you control
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[-1].strip()                # the hop our proxy appended
    return request.client.host if request.client else "unknown"


def _csrf(request: Request) -> None:
    """Cookie auth => defend against cross-site requests: custom header (forces a CORS preflight) + Origin check."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if request.headers.get("x-requested-with") != "zeim":
        raise HTTPException(403, detail={"code": "csrf", "message": "That request was blocked for your safety."})
    origin = request.headers.get("origin")
    if origin and origin not in _svc(request).cfg.origins:
        raise HTTPException(403, detail={"code": "csrf", "message": "That request was blocked for your safety."})


def _json(request: Request, body: dict, status: int = 200, token: Optional[str] = None, clear: bool = False) -> JSONResponse:
    cfg = _svc(request).cfg
    resp = JSONResponse(body, status_code=status, headers=_NO_STORE)
    if token:
        resp.set_cookie(cfg.cookie_name, token, max_age=cfg.session_max_s, httponly=True,
                        secure=cfg.secure_cookies, samesite="lax", path="/")
    if clear:
        resp.delete_cookie(cfg.cookie_name, path="/", secure=cfg.secure_cookies, httponly=True, samesite="lax")
    return resp


def _cookie_session(request: Request) -> Optional[SessionInfo]:
    svc = _svc(request)
    return svc.resolve_session(request.cookies.get(svc.cfg.cookie_name))


def _need_session(request: Request) -> SessionInfo:
    s = _cookie_session(request)
    if not s:
        raise HTTPException(401, detail={"code": "not_signed_in", "message": "Please sign in first."})
    return s


def _session_or_legacy(request: Request) -> tuple:
    """(session, via_legacy). A cookie-only account may run the add-passkey / add-email steps once."""
    s = _cookie_session(request)
    if s:
        return s, False
    resolver = request.app.state.legacy_resolver
    found = resolver(request) if resolver else None
    if found:
        legacy_id, display_name = found
        try:
            aid = _svc(request).ensure_legacy_account(legacy_id, display_name or "")
        except AuthError as e:
            _fail(e)
        return _svc(request).ephemeral_legacy_session(aid), True
    raise HTTPException(401, detail={"code": "not_signed_in", "message": "Please sign in first."})


def _dict(payload) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(400, detail={"code": "bad_request", "message": "That request wasn't understood."})
    return payload


def _run(fn, *a, **k):
    try:
        return fn(*a, **k)
    except AuthError as e:
        _fail(e)


# ------------------------------------------------------------------ sign-up / sign-in
@router.post("/signup/begin")
def signup_begin(request: Request, payload: dict = Body(...)):
    _csrf(request); p = _dict(payload)
    return _json(request, _run(_svc(request).signup_begin, p.get("display_name"), p.get("birth_date"), _ip(request)))


@router.post("/signup/finish")
def signup_finish(request: Request, payload: dict = Body(...)):
    _csrf(request); p = _dict(payload)
    token, s = _run(_svc(request).signup_finish, p.get("ceremony_id"), p.get("credential"), p.get("name"),
                    request.headers.get("user-agent"))
    return _json(request, {"signed_in": True, "display_name": _svc(request).overview(s)["display_name"]}, 201, token=token)


@router.post("/signin/begin")
def signin_begin(request: Request):
    _csrf(request)
    return _json(request, _run(_svc(request).signin_begin, _ip(request)))


@router.post("/signin/finish")
def signin_finish(request: Request, payload: dict = Body(...)):
    _csrf(request); p = _dict(payload)
    token, s = _run(_svc(request).signin_finish, p.get("ceremony_id"), p.get("credential"),
                    request.headers.get("user-agent"), _ip(request))
    return _json(request, {"signed_in": True}, token=token)


@router.post("/email/request")
def email_request(request: Request, payload: dict = Body(...)):
    _csrf(request); p = _dict(payload)
    _run(_svc(request).email_request_login, p.get("email"), _ip(request))
    return _json(request, {"ok": True, "message": "If that email belongs to an account, we've sent a code. It works for 10 minutes."}, 202)


@router.post("/email/verify")
def email_verify(request: Request, payload: dict = Body(...)):
    _csrf(request); p = _dict(payload)
    token, s = _run(_svc(request).email_verify_login, p.get("email"), p.get("code"),
                    request.headers.get("user-agent"), _ip(request))
    return _json(request, {"signed_in": True}, token=token)


# ------------------------------------------------------------------ session + account
@router.get("/session")
def session_status(request: Request):
    s = _cookie_session(request)
    return _json(request, {"signed_in": bool(s)})


@router.get("/account")
def account(request: Request):
    s = _need_session(request)
    return _json(request, _svc(request).overview(s))


@router.post("/logout")
def logout(request: Request):
    _csrf(request)
    s = _cookie_session(request)
    if s:
        _svc(request).logout(s)
    return _json(request, {"signed_in": False}, clear=True)


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: str, request: Request):
    _csrf(request); s = _need_session(request)
    if not _ID.match(session_id):
        raise HTTPException(404, detail={"code": "not_found", "message": "That device wasn't found."})
    _run(_svc(request).revoke_session, s.account_id, session_id)
    return _json(request, {"ok": True}, clear=(session_id == s.id))


@router.post("/sessions/revoke-all")
def revoke_all(request: Request, payload: dict = Body(default={})):
    """'Sign out everywhere'. keep_current=true leaves this device signed in."""
    _csrf(request); s = _need_session(request); p = _dict(payload)
    keep = p.get("keep_current") is True
    n = _svc(request).revoke_all(s.account_id, s.id if keep else None)
    return _json(request, {"ok": True, "signed_out": n}, clear=not keep)


# ------------------------------------------------------------------ add methods while signed in
@router.post("/passkeys/begin")
def passkey_add_begin(request: Request):
    _csrf(request); s, _legacy = _session_or_legacy(request)
    return _json(request, _run(_svc(request).passkey_add_begin, s))


@router.post("/passkeys/finish")
def passkey_add_finish(request: Request, payload: dict = Body(...)):
    _csrf(request); p = _dict(payload); s, legacy = _session_or_legacy(request)
    svc = _svc(request)
    out = _run(svc.passkey_add_finish, s, p.get("ceremony_id"), p.get("credential"), p.get("name"))
    if legacy:                                              # upgrade complete: give this device a real session
        token, _ = svc.session_for_legacy(s.account_id, request.headers.get("user-agent"))
        return _json(request, out, 201, token=token)
    return _json(request, out, 201)


@router.patch("/passkeys/{cred_id}")
def passkey_rename(cred_id: str, request: Request, payload: dict = Body(...)):
    _csrf(request); s = _need_session(request); p = _dict(payload)
    if not _ID.match(cred_id):
        raise HTTPException(404, detail={"code": "not_found", "message": "That passkey wasn't found."})
    _run(_svc(request).rename_passkey, s.account_id, cred_id, p.get("name"))
    return _json(request, {"ok": True})


@router.delete("/passkeys/{cred_id}")
def passkey_remove(cred_id: str, request: Request):
    _csrf(request); s = _need_session(request)
    if not _ID.match(cred_id):
        raise HTTPException(404, detail={"code": "not_found", "message": "That passkey wasn't found."})
    _run(_svc(request).remove_passkey, s, cred_id)
    return _json(request, {"ok": True})


@router.post("/email/add/request")
def email_add_request(request: Request, payload: dict = Body(...)):
    _csrf(request); p = _dict(payload); s, _legacy = _session_or_legacy(request)
    _run(_svc(request).email_add_request, s, p.get("email"), _ip(request))
    return _json(request, {"ok": True, "message": "We've sent a code to that address. It works for 10 minutes."}, 202)


@router.post("/email/add/verify")
def email_add_verify(request: Request, payload: dict = Body(...)):
    _csrf(request); p = _dict(payload); s, legacy = _session_or_legacy(request)
    svc = _svc(request)
    out = _run(svc.email_add_verify, s, p.get("email"), p.get("code"), _ip(request))
    if legacy:
        token, _ = svc.session_for_legacy(s.account_id, request.headers.get("user-agent"))
        return _json(request, out, token=token)
    return _json(request, out)


@router.delete("/email")
def email_remove(request: Request):
    _csrf(request); s = _need_session(request)
    _run(_svc(request).remove_email, s)
    return _json(request, {"ok": True})
