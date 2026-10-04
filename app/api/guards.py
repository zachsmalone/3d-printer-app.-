"""Who may touch server-wide settings and printers (Education CR-1).

shared mode (default): settings/linked accounts need the admin token; sending to a printer needs an adult account or the
admin token. local mode: as before. Class students are refused in BOTH modes, and are never shown printer addresses.
"""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

from .. import config
from ..community import classrooms
from ..community.identity import Actor


def is_admin(request: Request) -> bool:
    tok = request.headers.get("x-admin-token", "")
    return bool(config.ADMIN_TOKEN) and hmac.compare_digest(tok.encode(), config.ADMIN_TOKEN.encode())


def can_see_printer_urls(request: Request, actor: Actor) -> bool:
    if classrooms.is_student(actor.sid):
        return False
    return config.MODE == "local" or is_admin(request)


def require_settings_admin(request: Request, actor: Actor):
    if classrooms.is_student(actor.sid):
        raise HTTPException(403, "Your teacher manages printers and settings.")
    if config.MODE == "local" or is_admin(request):
        return
    raise HTTPException(403, "Server settings can only be changed by the server admin (X-Admin-Token) on a shared server.")


def _role(request: Request, actor: Actor) -> str:
    """'student' | 'teen' | 'adult'. Visitors who have NOT passed the age gate count as teens on a shared server (Download
    only); on a local server (one person's own machine) they are treated as the owner, like before."""
    if classrooms.is_student(actor.sid):
        return "student"
    if actor.user:
        return "adult" if actor.is_adult else "teen"
    if is_admin(request) or config.MODE == "local":
        return "adult"
    return "teen"


def send_caps(request: Request, actor: Actor) -> dict:
    """What this visitor may do to get a build OUT of ZEIM (design-ios-send.md section 2.2). The server decides; the page only reflects it.
    download: save the file to this device.  teacher: class 'send to my teacher'.  share: hand the file to another app.
    printer: send straight to a network printer.  links: signed slicer links (/api/print/<id>/links).
    Class students without an account have no known age, so they count as under 13: never share. A signed-up 13+ student gets
    share only if the teacher switched it on for that class."""
    role = _role(request, actor)
    caps = {"download": True, "teacher": False, "share": False, "printer": False, "links": False, "role": role}
    if role == "student":
        caps["teacher"] = True
        caps["share"] = bool(classrooms.send_allowed(actor.sid) and actor.user
                             and actor.age is not None and actor.age >= 13)
        caps["class_switch_on"] = classrooms.send_allowed(actor.sid)
    elif role == "adult":
        caps.update(share=True, printer=True, links=True)
    return caps


def require_links(request: Request, actor: Actor):
    """Minting signed links that carry a build outside ZEIM: adults only (and never class students / under-13 / teens)."""
    if not send_caps(request, actor)["links"]:
        raise HTTPException(403, "Sending to other apps isn't available for your account. You can download your build.")


def require_send(request: Request, actor: Actor):
    role = _role(request, actor)
    if role == "student":
        raise HTTPException(403, "Sending to a printer is done by your teacher.")
    if role == "teen":
        raise HTTPException(403, "Sending to a printer needs an adult account.")
    return
