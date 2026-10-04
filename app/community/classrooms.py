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
    if not isinstance(name, str) or len(name) > 60:
        raise ValueError("Class name must be text of at most 60 characters.")
    name = name.strip()
    if not name:
        raise ValueError("classroom name required")
    safety.filter_only(name, "Class name")
    check_new_password(password)
    code = _code()
    room = {"code": code, "name": name, "teacher_sid": actor.sid, "teacher": actor.user["display_name"],
            "teacher_uid": actor.user["id"], "pw": _hash(password),
            "created": datetime.now(timezone.utc).isoformat(), "assigned": [], "students": {},
            "projects": [], "notifications": []}
    CLASSROOMS.update(lambda d: d.__setitem__(code, room))
    return {"code": code, "name": name, "join_path": f"/#join/{code}"}


MIN_PASSWORD, MAX_PASSWORD = 8, 64
_WEAK = {"password", "12345678", "123456789", "1234567890", "11111111", "00000000", "qwertyui", "qwerty123", "abcdefgh",
         "password1", "letmein1", "iloveyou", "student1", "classroom", "teacher1", "12341234"}


def check_new_password(password):
    """Class join passwords: 8-64 characters, not an obvious one. (Guessing is also rate-limited per class and address.)"""
    if not isinstance(password, str) or not (MIN_PASSWORD <= len(password) <= MAX_PASSWORD):
        raise ValueError(f"Set a join password of {MIN_PASSWORD}-{MAX_PASSWORD} characters for your class "
                         "(a few words with a number, like plum-otter-42, works well).")
    if password.lower() in _WEAK or len(set(password)) < 4:
        raise ValueError("That password is too easy to guess. Try a few words with a number, like plum-otter-42.")


# ---- join-guess limiter: keyed by class code + network address (NOT by cookie: clearing cookies must not reset it) ----
_LOCKS: dict = {}       # (code, ip) -> (locked_until, strikes)
JOIN_FAILS, JOIN_WINDOW = 5, 600           # 5 wrong passwords in 10 min -> lockout for this address on this class
JOIN_IP_FAILS = 20                         # ...or 20 wrong guesses from one address across ALL classes in 10 min
LOCK_BASE, LOCK_MAX = 300, 24 * 3600       # lockout 5 min, doubling on each repeat, at most 24 h
_DUMMY_HASH = None


def _locked_for(code: str, ip: str) -> float:
    until, _ = _LOCKS.get((code, ip), (0, 0))
    return max(0.0, until - time.time())


def _note_fail(code: str, ip: str):
    from ..core import ratelimit
    ratelimit.hit(f"joinfail:{code}:{ip}", 10 ** 6, JOIN_WINDOW)
    ratelimit.hit(f"joinfail-ip:{ip}", 10 ** 6, JOIN_WINDOW)
    ratelimit.hit(f"joinfail-code:{code}", 10 ** 6, 3600)       # only used to tell the teacher how many wrong tries there were
    if (ratelimit.count(f"joinfail:{code}:{ip}", JOIN_WINDOW) >= JOIN_FAILS
            or ratelimit.count(f"joinfail-ip:{ip}", JOIN_WINDOW) >= JOIN_IP_FAILS):
        _, strikes = _LOCKS.get((code, ip), (0, 0))
        _LOCKS[(code, ip)] = (time.time() + min(LOCK_MAX, LOCK_BASE * 2 ** strikes), strikes + 1)
        ratelimit.clear(f"joinfail:{code}:{ip}")
        if len(_LOCKS) > 20000:
            for k in [k for k, v in _LOCKS.items() if v[0] < time.time()][:5000]:
                _LOCKS.pop(k, None)


def recent_failed_joins(code: str) -> int:
    from ..core import ratelimit
    return ratelimit.count(f"joinfail-code:{code}", 3600)


def join(sid: str, code: str, nickname: str, password: str = "", ip: str = "-", seat_code: str = "") -> dict:
    global _DUMMY_HASH
    if not all(isinstance(x, str) for x in (code or "", nickname or "", password or "", seat_code or "")):
        raise ValueError("Join details must be text.")
    code, nickname, password, seat_code = code or "", nickname or "", password or "", seat_code or ""
    if len(code) > 12 or len(nickname) > 60 or len(password) > MAX_PASSWORD or len(seat_code) > 20:
        raise ValueError("Nickname must be 2-20 letters/numbers. Do NOT use your real full name.")
    code = code.strip().upper()
    nick = nickname.strip()
    if not NICK.match(nick):
        raise ValueError("Nickname must be 2-20 letters/numbers. Do NOT use your real full name.")
    safety.filter_only(nick, "Nickname")
    wait = _locked_for(code, ip)
    if wait > 0:
        raise PermissionError(f"Too many wrong passwords from this network. Try again in {int(wait // 60) + 1} minutes, or ask your teacher.")
    # Check the password OUTSIDE the store lock (scrypt is slow), against a dummy hash for unknown classes (same timing/answer).
    room0 = CLASSROOMS.read().get(code)
    if _DUMMY_HASH is None:
        _DUMMY_HASH = _hash("not-a-real-password")
    ok = _verify(password, room0["pw"] if room0 else _DUMMY_HASH) and room0 is not None
    if not ok:
        _note_fail(code, ip)
        raise KeyError(code)               # same answer for "no such class" and "wrong password"
    out = {}

    def f(d):
        room = d.get(code)
        if not room:
            raise KeyError(code)
        others = [s["nickname"].lower() for k, s in room["students"].items() if k != sid]
        if sid not in room["students"] and len(room["students"]) >= 60:
            raise ValueError("classroom is full")
        if nick.lower() in others:
            raise ValueError("That nickname is taken in this class - pick another.")
        prev = room["students"].get(sid, {})
        room["students"][sid] = {"nickname": nick, "joined": prev.get("joined") or datetime.now(timezone.utc).isoformat(),
                                 "muted": prev.get("muted", False)}
        out.update(name=room["name"], code=code, assigned=room["assigned"], teacher=room["teacher"])
    CLASSROOMS.update(f)
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
                    "canned": {k: safety.CANNED[k] for k in safety.TEACHER_CANNED},
                    "failed_joins_last_hour": recent_failed_joins(r["code"])})
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
    if not isinstance(comment, str) or len(comment) > 4 * MAX_FEEDBACK:
        raise ValueError(f"Keep feedback under {MAX_FEEDBACK} characters.")
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
