"""Settings + linked accounts endpoints."""
from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..community.identity import Actor, get_actor
from ..services import accounts, printers, settings
from . import guards

router = APIRouter(prefix="/api")


_base = settings.base_url


@router.get("/settings")
def get_settings(request: Request, actor: Actor = Depends(get_actor)):
    from .. import config
    manage = guards.can_manage_printers(request, actor)
    return {**settings.public(redact=not manage), "printer_types": printers.TYPES,
            "printer_presets": [{"id": k, "label": v["label"], "type": v["type"], "bed": list(v["bed"]), "hint": v["hint"]} for k, v in printers.PROFILES.items()],
            "mode": config.MODE, "can_edit": _can_edit(request, actor), "printer_manage": manage}


def _can_edit(request, actor) -> bool:
    try:
        guards.require_settings_admin(request, actor)
        return True
    except HTTPException:
        return False


@router.put("/settings")
def put_settings(body: dict, request: Request, actor: Actor = Depends(get_actor)):
    guards.require_settings_admin(request, actor)
    try:
        settings.save_from_client(body)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    return settings.public()


@router.put("/settings/printers")
def put_printers(body: dict, request: Request, actor: Actor = Depends(get_actor)):
    """Printer rows only. The public base URL and default slicer stay as they are."""
    if not guards.can_manage_printers(request, actor):
        raise HTTPException(403, "Only the person who manages this server can change printers.")
    try:
        settings.save_printers(body.get("printers") or [])
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    return settings.public(redact=False)


@router.get("/accounts")
def list_accounts():
    return {"providers": accounts.status(),
            "note": "Scaffolding only: you can connect accounts when OAuth client keys are configured, "
                    "but sharing/posting is not implemented yet."}


@router.get("/accounts/{provider}/connect")
def connect(provider: str, request: Request, actor: Actor = Depends(get_actor)):
    guards.require_settings_admin(request, actor)
    p = accounts.REGISTRY.get(provider)
    if not p:
        raise HTTPException(404)
    if not p.configured():
        raise HTTPException(409, f"{p.label} is not configured. Set "
                                 f"PHOTO3D_{provider.upper()}_CLIENT_ID and _CLIENT_SECRET and restart.")
    return RedirectResponse(accounts.begin(provider, _base(request)))


@router.get("/accounts/{provider}/callback")
def callback(provider: str, request: Request, code: str = "", state: str = "", error: str = ""):
    if provider not in accounts.REGISTRY:
        raise HTTPException(404)
    if error or not code:
        return HTMLResponse(f"<p>Authorization failed: {escape(str(error or 'no code')[:200])}.</p><a href='/'>Back</a>", 400)
    try:
        accounts.finish(provider, code, state, _base(request))
    except Exception as e:
        return HTMLResponse(f"<p>Could not connect: {escape(type(e).__name__)}: {escape(str(e)[:200])}</p><a href='/'>Back</a>", 400)
    return RedirectResponse("/?connected=" + provider)


@router.delete("/accounts/{provider}")
def disconnect(provider: str, request: Request, actor: Actor = Depends(get_actor)):
    guards.require_settings_admin(request, actor)
    if provider not in accounts.REGISTRY:
        raise HTTPException(404)
    accounts.disconnect(provider)
    return {"ok": True}
