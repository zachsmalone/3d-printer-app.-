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


_PROXY_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "forwarded", "x-real-ip", "cf-connecting-ip", "cf-ray", "via")


def is_this_computer(request: Request) -> bool:
    """True only for a request that really comes from the machine running ZEIM: loopback peer, loopback Host, no proxy/tunnel headers.
    (A tunnel adds forwarding headers and a public Host, so it is never 'this computer'.)"""
    if any(h in request.headers for h in _PROXY_HEADERS):
        return False
    host = (request.headers.get("host") or "").strip().lower()
    host = host[1:host.index("]")] if host.startswith("[") and "]" in host else host.split(":")[0]
    peer = request.client.host if request.client else ""
    return host in config.LOCAL_HOSTS and peer in config.LOCAL_CLIENTS


def is_owner(request: Request) -> bool:
    """The machine's owner: local mode AND the request comes from this computer. (Local mode over a tunnel/LAN is NOT the owner.)"""
    return config.MODE == "local" and is_this_computer(request)


def is_admin(request: Request) -> bool:
    tok = request.headers.get("x-admin-token", "")
    if not tok or not config.ADMIN_TOKEN:
        return False
    from ..core import ratelimit
    from .textcap import ip
    key = "admintok:" + ip(request)
    if ratelimit.count(key, 600) >= config.ADMIN_FAIL_LIMIT:         # too many wrong guesses: even the right token waits
        raise HTTPException(429, "Too many wrong admin tokens from this address. Try again in a few minutes.")
    if hmac.compare_digest(tok.encode(), config.ADMIN_TOKEN.encode()):
        return True
    ratelimit.hit(key, 10 ** 6, 600)
    return False


def can_see_printer_urls(request: Request, actor: Actor) -> bool:
    if classrooms.is_student(actor.sid):
        return False
    return is_owner(request) or is_admin(request)


def require_settings_admin(request: Request, actor: Actor):
    if classrooms.is_student(actor.sid):
        raise HTTPException(403, "Your teacher manages printers and settings.")
    if is_owner(request):
        origin = request.headers.get("origin")                     # S-01 local mode: another web page open in the owner's browser must not change settings
        if origin and origin != "null" and origin.split("://", 1)[-1].lower() != (request.headers.get("host") or "").lower():
            raise HTTPException(403, "Settings can only be changed from ZEIM's own page.")
        if origin == "null":
            raise HTTPException(403, "Settings can only be changed from ZEIM's own page.")
        return
    if is_admin(request):
        return
    raise HTTPException(403, "Server settings can only be changed by the server admin (X-Admin-Token) on a shared server.")


def _role(request: Request, actor: Actor) -> str:
    """'student' | 'teen' | 'adult'. Visitors who have NOT passed the age gate count as teens on a shared server (Download
    only); on a local server (one person's own machine) they are treated as the owner, like before."""
    if classrooms.is_student(actor.sid):
        return "student"
    if actor.user:
        return "adult" if actor.is_adult else "teen"
    if is_admin(request) or is_owner(request):
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
        room = classrooms.room_of(actor.sid)
        caps["class_code"] = room.get("code") if room else None
    elif role == "adult":
        caps.update(share=True, printer=True, links=True)
    # What the PAGE may draw (the policy above is what the server enforces):
    #  share_ui   - the share-sheet rows exist only after the device spike passed (flag PHOTO3D_SEND_SHARE)
    #  printer_ui - direct-to-printer only where it can really work: ZEIM running on the user's own computer (local mode).
    #               A hosted https page cannot call an http:// printer on someone's LAN, so hosted ZEIM does not promise it.
    caps["share_ui"] = bool(caps["share"] and config.SEND_SHARE_UI)
    caps["printer_ui"] = bool(caps["printer"] and config.MODE == "local")
    caps["mode"] = config.MODE
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


def showcase_gate(actor: Actor, likes: bool = False):
    """Class students see the public Showcase only if their teacher switched it on (and may like only if a second switch is on).
    Everyone who is not a class student is unaffected. (Education CR-3)"""
    pol = classrooms.showcase_policy(actor.sid)
    if pol is None:
        return
    if not pol["enabled"]:
        raise HTTPException(404, "Your teacher has turned this off.")
    if likes and not pol["likes"]:
        raise HTTPException(403, "Your teacher turned nozzles off for your class.")
