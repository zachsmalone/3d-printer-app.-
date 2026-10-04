"""Classrooms: a teacher (adult account) creates a class with a name + join PASSWORD; students join with the class
code (or QR / join link) + the password + a NICKNAME. No account, DOB, email or real name is collected.

  * Join: code + password + nickname. Passwords are stored salted+hashed (scrypt); wrong guesses are rate-limited.
    The QR code / link carries only the class code - the teacher hands out the password separately.
  * Projects: a student "submits" a build to the class; a snapshot (STL/3MF/thumb) is copied into the class. Class
    projects are PRIVATE TO THE CLASSROOM (teacher + members only), never public, never in Showcase/search/feeds.
  * Feedback: the teacher writes TEXT comments on a student's project (no ratings/scores exist). Free text goes
    through the language filter (safety.py): disallowed language is blocked and the sender is told so.
  * "Talk next class": no free-text DMs. Student<->teacher communicate only with canned requests that show up as a
    notification on the other side. A teacher can mute a student (their requests are then ignored) and anyone can
    report a feedback comment to the moderator queue.
Not yet: roster import, LMS sign-in, parental consent flows, COPPA/FERPA review (see ROADMAP).
"""
from __future__ import annotations

import hashlib
import hmac
import io
import re
import secrets
import shutil
import time
from datetime import datetime, timezone

from ..config import DATA
from . import education, safety
from .identity import Actor
from .store import CLASSROOMS

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
NICK = re.compile(r"^[A-Za-z0-9 _-]{2,20}$")
CDIR = DATA / "classroom_projects"
CDIR.mkdir(exist_ok=True)
MAX_FEEDBACK = 500
_FAILS: dict = {}          # (sid, code) -> [timestamps]  (in-memory join-guess limiter)


def _code():
    return "".join(secrets.choice(ALPHABET) for _ in range(6))


def _hash(pw: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return salt.hex() + "$" + h.hex()


def _verify(pw: str, stored: str) -> bool:
    try:
        salt, h = stored.split("$")
        return hmac.compare_digest(hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32).hex(), h)
    except Exception:
        return False


def create(actor: Actor, name: str, password: str = "") -> dict:
    if not actor.user or not actor.is_adult:
        raise PermissionError("Only adult accounts can create a classroom.")
    name = (name or "").strip()[:60]
    if not name:
        raise ValueError("classroom name required")
    safety.filter_only(name, "Class name")
    if not (4 <= len(password or "") <= 40):
        raise ValueError("Set a join password of 4-40 characters for your class.")
    code = _code()
    room = {"code": code, "name": name, "teacher_sid": actor.sid, "teacher": actor.user["display_name"],
            "teacher_uid": actor.user["id"], "pw": _hash(password),
            "created": datetime.now(timezone.utc).isoformat(), "assigned": [], "students": {},
            "projects": [], "notifications": []}
    CLASSROOMS.update(lambda d: d.__setitem__(code, room))
    return {"code": code, "name": name, "join_path": f"/#join/{code}"}


def join(sid: str, code: str, nickname: str, password: str = "") -> dict:
    code = (code or "").strip().upper()
    nick = (nickname or "").strip()
    if not NICK.match(nick):
        raise ValueError("Nickname must be 2-20 letters/numbers. Do NOT use your real full name.")
    safety.filter_only(nick, "Nickname")
    now = time.time()
    fails = [t for t in _FAILS.get((sid, code), []) if now - t < 600]
    if len(fails) >= 5:
        raise PermissionError("Too many wrong passwords. Wait a few minutes and ask your teacher.")
    out = {}

    def f(d):
        room = d.get(code)
        if not room or not _verify(password or "", room["pw"]):
            fails.append(now)
            _FAILS[(sid, code)] = fails
            raise KeyError(code)               # same answer for "no such class" and "wrong password"
        if sid not in room["students"]:
            if len(room["students"]) >= 60:
                raise ValueError("classroom is full")
            if any(s["nickname"].lower() == nick.lower() for s in room["students"].values()):
                raise ValueError("That nickname is taken in this class - pick another.")
        prev = room["students"].get(sid, {})
        room["students"][sid] = {"nickname": nick, "joined": prev.get("joined") or datetime.now(timezone.utc).isoformat(),
                                 "muted": prev.get("muted", False)}
        out.update(name=room["name"], code=code, assigned=room["assigned"], teacher=room["teacher"])
    CLASSROOMS.update(f)
    _FAILS.pop((sid, code), None)
    return out


def is_student(sid: str) -> bool:
    """True if this browser session is a member (student) of any classroom."""
    return any(sid in room["students"] for room in CLASSROOMS.read().values())


def student_view(sid: str):
    for room in CLASSROOMS.read().values():
        if sid in room["students"]:
            return {"name": room["name"], "code": room["code"], "teacher": room["teacher"],
                    "assigned": room["assigned"], "nickname": room["students"][sid]["nickname"],
                    "notifications": [n for n in room["notifications"] if n["to"] == sid[:8] and not n["read"]],
                    "canned": {k: safety.CANNED[k] for k in safety.STUDENT_CANNED}}
    return None


def _own(d, actor, code):
    room = d.get((code or "").upper())
    if not room or room["teacher_sid"] != actor.sid:
        raise KeyError(code)
    return room


def teacher_rooms(actor: Actor) -> list[dict]:
    out = []
    for r in CLASSROOMS.read().values():
        if r["teacher_sid"] != actor.sid:
            continue
        studs = []
        for sid, s in r["students"].items():
            cat = {c["id"]: c for c in education.catalog(sid)}
            studs.append({"id": sid[:8], "nickname": s["nickname"], "muted": s.get("muted", False),
                          "lessons": [{"id": lid, "done_steps": cat[lid]["done_steps"], "steps": cat[lid]["steps"],
                                       "completed": cat[lid]["completed"]} for lid in (r["assigned"] or cat)]})
        out.append({"code": r["code"], "name": r["name"], "assigned": r["assigned"], "students": studs,
                    "join_path": f"/#join/{r['code']}", "projects": [project_public(p, r) for p in r["projects"]],
                    "notifications": [n for n in r["notifications"] if n["to"] == "teacher" and not n["read"]],
                    "canned": {k: safety.CANNED[k] for k in safety.TEACHER_CANNED}})
    return out


def assign(actor: Actor, code: str, lesson_ids: list[str]):
    valid = {l["id"] for l in education.LESSONS}
    ids = [l for l in lesson_ids if l in valid]
    CLASSROOMS.update(lambda d: _own(d, actor, code).__setitem__("assigned", ids))


def _purge_projects(room, only_sid=None):
    for p in list(room["projects"]):
        if only_sid is None or p["student_sid"] == only_sid:
            shutil.rmtree(CDIR / room["code"] / p["id"], ignore_errors=True)
            room["projects"].remove(p)


def remove_student(actor: Actor, code: str, sid_prefix: str):
    def f(d):
        room = _own(d, actor, code)
        for sid in list(room["students"]):
            if sid.startswith(sid_prefix):
                del room["students"][sid]
                education.reset(sid)
                _purge_projects(room, sid)
                room["notifications"] = [n for n in room["notifications"] if sid[:8] not in (n["to"], n["from"])]
    CLASSROOMS.update(f)


def set_muted(actor: Actor, code: str, sid_prefix: str, muted: bool):
    """Teacher moderation: a muted student's canned requests are refused (they can still learn / submit)."""
    hit = []

    def f(d):
        room = _own(d, actor, code)
        for sid, s in room["students"].items():
            if sid.startswith(sid_prefix) and sid_prefix:
                s["muted"] = bool(muted)
                hit.append(sid)
    CLASSROOMS.update(f)
    if not hit:
        raise KeyError(sid_prefix)


def delete(actor: Actor, code: str):
    def f(d):
        room = _own(d, actor, code)
        for sid in room["students"]:
            education.reset(sid)
        _purge_projects(room)
        shutil.rmtree(CDIR / room["code"], ignore_errors=True)
        del d[room["code"]]
    CLASSROOMS.update(f)


def qr_svg(base_url: str, code: str) -> str:
    """QR for the join link. Only the CLASS CODE is encoded - never the password."""
    import segno
    buf = io.BytesIO()
    segno.make(f"{base_url.rstrip('/')}/#join/{code}", error="m").save(buf, kind="svg", scale=6, border=2,
                                                                         dark="#111111", light="#ffffff")
    return buf.getvalue().decode()


def membership(actor: Actor, code: str):
    """('teacher'|'student', room) or KeyError (non-members get 404 - classroom data is private)."""
    room = CLASSROOMS.read().get((code or "").upper())
    if not room:
        raise KeyError(code)
    if room["teacher_sid"] == actor.sid:
        return "teacher", room
    if actor.sid in room["students"]:
        return "student", room
    raise KeyError(code)


# ---------------------------------------------------------------- class projects (private to the classroom)
def project_public(p: dict, room: dict) -> dict:
    return {"id": p["id"], "title": p["title"], "student": p["nickname"], "student_id": p["student_sid"][:8],
            "created": p["created"], "visibility": "classroom",
            "thumb": f"/api/classrooms/{room['code']}/projects/{p['id']}/thumb",
            "files": [f"/api/classrooms/{room['code']}/projects/{p['id']}/files/{n}" for n in ("model.stl", "model.3mf")],
            "feedback": [{"id": f["id"], "comment": f["comment"], "created": f["created"], "teacher": room["teacher"]}
                         for f in p["feedback"] if not f.get("hidden")]}


def submit_project(actor: Actor, code: str, build_dir, title: str) -> dict:
    role, room = membership(actor, code)
    if role != "student":
        raise PermissionError("Only students submit projects.")
    title = safety.gate(actor, title or "My project", f"class:{code}:title")[:60] or "My project"
    pid = secrets.token_hex(4)
    d = CDIR / room["code"] / pid
    d.mkdir(parents=True)
    for n in ("model.stl", "model.3mf", "thumb.png"):
        shutil.copy(build_dir / n, d / n)
    p = {"id": pid, "student_sid": actor.sid, "nickname": room["students"][actor.sid]["nickname"], "title": title,
         "created": datetime.now(timezone.utc).isoformat(), "feedback": []}
    CLASSROOMS.update(lambda dd: dd[room["code"]]["projects"].append(p))
    return project_public(p, room)


def list_projects(actor: Actor, code: str) -> list[dict]:
    role, room = membership(actor, code)
    return [project_public(p, room) for p in room["projects"]]


def project_file(actor: Actor, code: str, pid: str, name: str):
    role, room = membership(actor, code)
    if name not in ("model.stl", "model.3mf", "thumb.png") or not pid.isalnum():
        raise KeyError(name)
    if not any(p["id"] == pid for p in room["projects"]):
        raise KeyError(pid)
    f = CDIR / room["code"] / pid / name
    if not f.exists():
        raise KeyError(name)
    return f


def add_feedback(actor: Actor, code: str, pid: str, comment: str) -> dict:
    role, room = membership(actor, code)
    if role != "teacher":
        raise PermissionError("Only the teacher can give feedback.")
    comment = (comment or "").strip()
    if not comment:
        raise ValueError("Write a comment.")
    if len(comment) > MAX_FEEDBACK:
        raise ValueError(f"Keep feedback under {MAX_FEEDBACK} characters.")
    comment = safety.gate(actor, comment, f"class:{code}:feedback")     # blocks disallowed language (ChatBlocked)
    fb = {"id": secrets.token_hex(4), "comment": comment, "created": datetime.now(timezone.utc).isoformat()}
    out = {}

    def f(d):
        pr = next((p for p in d[room["code"]]["projects"] if p["id"] == pid), None)
        if not pr:
            raise KeyError(pid)
        pr["feedback"].append(fb)
        out.update(project_public(pr, d[room["code"]]))
    CLASSROOMS.update(f)
    return out


def hide_feedback(item_id: str):
    """Moderator action for a reported feedback comment (item id 'fb:<code>:<project>:<comment>')."""
    try:
        _, code, pid, fid = item_id.split(":")
    except ValueError:
        return

    def f(d):
        for p in d.get(code, {}).get("projects", []):
            if p["id"] == pid:
                for fb in p["feedback"]:
                    if fb["id"] == fid:
                        fb["hidden"] = True
    CLASSROOMS.update(f)


# ---------------------------------------------------------------- canned requests ('talk next class') = notifications
def send_request(actor: Actor, code: str, kind: str, to: str = "") -> dict:
    """Canned request only. Students → teacher; teacher → one student (`to` = student id)."""
    role, room = membership(actor, code)
    allowed = safety.STUDENT_CANNED if role == "student" else safety.TEACHER_CANNED
    if kind not in allowed:
        raise ValueError(f"Choose one of the pre-set requests: {allowed}")
    if role == "student" and room["students"][actor.sid].get("muted"):
        raise PermissionError("Your teacher has turned off requests for you.")
    sender = actor.sid[:8] if role == "student" else "teacher"
    if role == "student":
        target = "teacher"
    else:
        if not to or not any(s.startswith(to) for s in room["students"]):
            raise KeyError(to)
        target = to
    name = room["students"][actor.sid]["nickname"] if role == "student" else room["teacher"]
    n = {"id": secrets.token_hex(4), "kind": kind, "text": safety.CANNED[kind], "from": sender, "from_name": name,
         "to": target, "created": datetime.now(timezone.utc).isoformat(), "read": False}

    def f(d):
        r = d[room["code"]]
        if any(x for x in r["notifications"] if x["from"] == sender and x["to"] == target and x["kind"] == kind and not x["read"]):
            raise ValueError("You already sent that request - it's waiting to be read.")
        r["notifications"].append(n)
        r["notifications"] = r["notifications"][-200:]
    CLASSROOMS.update(f)
    return {k: n[k] for k in ("id", "kind", "text", "created")}


def notifications(actor: Actor, code: str) -> list[dict]:
    role, room = membership(actor, code)
    me = "teacher" if role == "teacher" else actor.sid[:8]
    return [{k: n[k] for k in ("id", "kind", "text", "from_name", "created", "read")}
            for n in room["notifications"] if n["to"] == me][::-1]


def mark_read(actor: Actor, code: str):
    role, room = membership(actor, code)
    me = "teacher" if role == "teacher" else actor.sid[:8]

    def f(d):
        for n in d[room["code"]]["notifications"]:
            if n["to"] == me:
                n["read"] = True
    CLASSROOMS.update(f)
