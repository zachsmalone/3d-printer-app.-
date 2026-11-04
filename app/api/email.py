from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..services import email

router = APIRouter(prefix="/api/email")


@router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe(u: str = "", t: str = ""):
    if u and email.check_unsub(u, t):
        email.opt_out(u)
        msg = "Done. You won't get these emails again, and your address has been deleted from the email list."
    else:
        msg = "This link didn't work. It may be old or cut off."
    return HTMLResponse(f'<!doctype html><meta name=viewport content="width=device-width"><title>ZEIM email</title>'
                        f'<p style="font-family:system-ui;max-width:480px;margin:40px auto;padding:0 16px">{msg} <a href="/">Back to ZEIM</a></p>')
