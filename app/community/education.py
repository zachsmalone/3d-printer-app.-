"""Learning library: curated, original, family-friendly lessons + a private step checklist.

Content is static/curated only (no user-generated content, no chat, no external links).
2026-10-12: school features removed. No quizzes, scores, grades or school records are stored;
the only thing kept is which steps this browser ticked off, visible only to that browser.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .store import PROGRESS

LESSONS = [
    {"id": "first-print", "objective": 'You can describe how FDM printing works and follow basic printer safety.', "title": "Your first print", "emoji": "🖨", "minutes": 20, "age": "8+",
     "summary": "Meet your printer, stay safe, and make something small.",
     "steps": [
         {"title": "Safety first", "body": "The nozzle and the bed get HOT. Never touch the nozzle, keep children and pets away from the printer while it runs, and keep hair and sleeves away from moving parts."},
         {"title": "How a printer builds things", "body": "A 3D printer melts plastic and draws your shape one very thin layer at a time, like stacking super-thin sheets of paper until a solid object appears."},
         {"title": "Pick a starter model", "body": "Choose something small and flat. Open the Studio, press 'Try a sample photo', pick Relief and build it. Small + flat prints are quick and rarely fail."},
         {"title": "Slice it", "body": "A 'slicer' cuts your model into layers and writes the printer's instructions (G-code). Use Print → Slice here, or open it in your slicer."},
         {"title": "Watch the first layer", "body": "The first layer must stick well. Watch it go down; if it curls up, pause the print and re-level the bed."},
     ],
     "try": {"mode": "relief", "preset": "thin", "label": "Open the Studio with a starter relief"}},
    {"id": "intro-modeling", "objective": 'You will explain that brightness can be mapped to height and compare two relief heights.', "title": "Intro to modeling", "emoji": "📐", "minutes": 25, "age": "9+",
     "summary": "Learn how pictures become 3D shapes using height.",
     "steps": [
         {"title": "Height from brightness", "body": "A computer can turn a picture into a 3D shape by treating bright spots as tall and dark spots as short. That's called a heightmap."},
         {"title": "Make a heightmap", "body": "In the Studio choose Relief, drop in a photo, and press Build. Spin your model around in the 3D view."},
         {"title": "Change the depth", "body": "Switch to Expert mode and change 'Relief height' from 2 to 10 mm. What changes? Rebuild and compare."},
         {"title": "Flat colour layers", "body": "Pop-art mode squeezes a picture into a few colours and stacks them like cake layers so the picture pops off the page."},
     ],
     "try": {"mode": "popart", "preset": "standard", "label": "Try a pop-art build"}},
    {"id": "lithophanes", "objective": 'You will predict how thickness changes light transmission and test it with an LED light.', "title": "Make a lithophane", "emoji": "💡", "minutes": 25, "age": "8+",
     "summary": "Print a picture that glows when a light shines through it.",
     "steps": [
         {"title": "What is a lithophane?", "body": "A lithophane is a thin plastic picture. Thick parts block light (dark), thin parts let more light through (bright)."},
         {"title": "Pick a photo", "body": "High-contrast photos with a clear subject (a pet or a face) work best. Busy backgrounds look muddy."},
         {"title": "Build it", "body": "Choose Lithophane in the Studio, keep Beginner mode, pick Standard thickness and build."},
         {"title": "Check the preview", "body": "Under 'Pick up where you left off', your model's card shows a glowing preview. Does it look like your photo?"},
         {"title": "Print and light it", "body": "Print it standing up, then put a small LED light behind it. Never use a hot bulb — plastic can melt!"},
     ],
     "try": {"mode": "lithophane", "preset": "standard", "label": "Build a lithophane"}},
]
BADGES = {"first-print": "🏅 First Printer", "intro-modeling": "🏅 Shape Maker", "lithophanes": "🏅 Light Painter"}


def _by_id(lid):
    return next((l for l in LESSONS if l["id"] == lid), None)


def catalog(sid: str) -> list[dict]:
    prog = PROGRESS.read().get(sid, {})
    out = []
    for l in LESSONS:
        p = prog.get(l["id"], {})
        out.append({"id": l["id"], "title": l["title"], "emoji": l["emoji"], "minutes": l["minutes"], "age": l["age"],
                    "summary": l["summary"], "steps": len(l["steps"]),
                    "done_steps": len(p.get("steps_done", [])), "completed": bool(p.get("completed_at")),
                    "badge": BADGES[l["id"]] if p.get("completed_at") else None})
    return out


def lesson(sid: str, lid: str) -> dict | None:
    l = _by_id(lid)
    if not l:
        return None
    p = PROGRESS.read().get(sid, {}).get(lid, {})
    return {**{k: l[k] for k in ("id", "title", "emoji", "minutes", "age", "summary", "steps", "try", "objective")},
            "progress": {"steps_done": p.get("steps_done", []),
                         "completed": bool(p.get("completed_at"))}}


def mark_step(sid: str, lid: str, idx: int, done: bool):
    l = _by_id(lid)
    if not l or not (0 <= idx < len(l["steps"])):
        raise KeyError(lid)

    def f(d):
        p = d.setdefault(sid, {}).setdefault(lid, {})
        s = set(p.get("steps_done", []))
        (s.add if done else s.discard)(idx)
        p["steps_done"] = sorted(s)
        _maybe_complete(l, p)
    PROGRESS.update(f)


def _maybe_complete(l, p):
    if len(p.get("steps_done", [])) == len(l["steps"]) and not p.get("completed_at"):
        p["completed_at"] = datetime.now(timezone.utc).isoformat()


def reset(sid: str):
    PROGRESS.update(lambda d: d.pop(sid, None))
