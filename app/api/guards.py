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


def require_send(request: Request, actor: Actor):
    if classrooms.is_student(actor.sid):
        raise HTTPException(403, "Sending to a printer is done by your teacher.")
    if config.MODE == "local" or is_admin(request) or actor.is_adult:
        return
    raise HTTPException(403, "Sending to a printer needs an adult account on a shared server.")
