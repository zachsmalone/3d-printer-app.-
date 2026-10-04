"""Settings + linked accounts endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..services import accounts, printers, settings

router = APIRouter(prefix="/api")


def _base(request: Request) -> str:
    return settings.load().get("public_base_url") or str(request.base_url).rstrip("/")


@router.get("/settings")
def get_settings():
    return {**settings.public(), "printer_types": printers.TYPES}


@router.put("/settings")
def put_settings(body: dict):
    settings.save_from_client(body)
    return settings.public()


@router.get("/accounts")
def list_accounts():
    return {"providers": accounts.status(),
            "note": "Scaffolding only: you can connect accounts when OAuth client keys are configured, "
                    "but sharing/posting is not implemented yet."}


@router.get("/accounts/{provider}/connect")
def connect(provider: str, request: Request):
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
        return HTMLResponse(f"<p>Authorization failed: {error or 'no code'}.</p><a href='/'>Back</a>", 400)
    try:
        accounts.finish(provider, code, state, _base(request))
    except Exception as e:
        return HTMLResponse(f"<p>Could not connect: {type(e).__name__}: {e}</p><a href='/'>Back</a>", 400)
    return RedirectResponse("/?connected=" + provider)


@router.delete("/accounts/{provider}")
def disconnect(provider: str):
    if provider not in accounts.REGISTRY:
        raise HTTPException(404)
    accounts.disconnect(provider)
    return {"ok": True}
