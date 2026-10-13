"""Honest proof badges for ZEIM Originals (owner ask 2026-10-12): every Original is **Simulated** until a real print is logged.

Simulated    = checked on a computer only: geometry checks + a slicer run with a generic 0.4 mm profile
               (reports/qa/originals-and-regression-2026-10-12.md). It says the check was done, NOT that it passed.
Test-printed = the ZEIM team logged a real print of that file (printer, date, outcome). The badge names the printer
               that was logged, so nothing ever says "tested on a K1" unless a K1 print was logged.

Prints are logged by the server admin (X-Admin-Token) through /api/moderation/originals/... and kept in
data/originals_prints.json. A wrong entry is RETRACTED (kept, marked), never deleted, so the history stays honest.
"""
from __future__ import annotations

import secrets
from datetime import date, datetime, timezone

from .store import JsonFile

PRINTS = JsonFile("originals_prints.json", {"prints": []})

RESULTS = {
    "worked": "Printed and worked as intended",
    "printed": "Printed fine; how well it works was not checked yet",
    "failed": "Print failed",
}
SIMULATED = {"badge": "simulated", "label": "Simulated",
             "detail": "Checked on a computer only (shape checks and a slicer preview with a generic 0.4 mm profile). "
                       "Untested print: not printed by the ZEIM team yet.", "prints": []}


class ProofError(ValueError):
    pass


def _clean(s, n: int) -> str:
    s = (s if isinstance(s, str) else "").strip()
    return "".join(c for c in s if c >= " ")[:n]


def log_print(item_id: str, printer: str, printed_on: str, result: str, logged_by: str = "admin", notes: str = "") -> dict:
    """Record one real print of an Original. Needs the printer model, the date it was printed (not in the future) and the outcome."""
    printer = _clean(printer, 60)
    if not printer:
        raise ProofError("Say which printer it was printed on (for example: Creality K1).")
    try:
        d = date.fromisoformat(_clean(printed_on, 10))
    except ValueError:
        raise ProofError("Print date must be YYYY-MM-DD.")
    if d > datetime.now(timezone.utc).date():
        raise ProofError("The print date can't be in the future.")
    if result not in RESULTS:
        raise ProofError("Result must be one of: " + ", ".join(RESULTS) + ".")
    e = {"id": "tp_" + secrets.token_hex(5), "item_id": item_id, "printer": printer, "printed_on": d.isoformat(),
         "result": result, "notes": _clean(notes, 500), "logged_by": _clean(logged_by, 40) or "admin",
         "logged_at": datetime.now(timezone.utc).isoformat(), "retracted": None}
    PRINTS.update(lambda db: db.setdefault("prints", []).append(e))
    return e


def retract(entry_id: str, reason: str = "", by: str = "admin") -> dict:
    """Mark a logged print as wrong (kept for the record, no longer counts)."""
    out = {}

    def f(db):
        for e in db.get("prints", []):
            if e["id"] == entry_id:
                if not e.get("retracted"):
                    e["retracted"] = {"at": datetime.now(timezone.utc).isoformat(), "by": _clean(by, 40) or "admin",
                                      "reason": _clean(reason, 300)}
                out["e"] = e
                return
    PRINTS.update(f)
    if "e" not in out:
        raise KeyError(entry_id)
    return out["e"]


def entries(item_id: str | None = None, include_retracted: bool = True) -> list[dict]:
    return [e for e in PRINTS.read().get("prints", [])
            if (item_id is None or e["item_id"] == item_id) and (include_retracted or not e.get("retracted"))]


def proof(item_id: str, _db: dict | None = None) -> dict:
    """The badge for one Original. Test-printed only when a live (not retracted) 'worked' or 'printed' entry exists."""
    db = _db if _db is not None else PRINTS.read()
    live = [e for e in db.get("prints", []) if e["item_id"] == item_id and not e.get("retracted")]
    good = sorted([e for e in live if e["result"] in ("worked", "printed")], key=lambda e: e["printed_on"], reverse=True)
    if not good:
        out = dict(SIMULATED)
        if any(e["result"] == "failed" for e in live):
            out["detail"] = SIMULATED["detail"] + " A ZEIM test print of this file failed; it is being fixed."
        return out
    last = good[0]
    detail = f"Printed by the ZEIM team on a {last['printer']} ({last['printed_on']})."
    detail += " It worked as intended." if any(e["result"] == "worked" for e in good) else " How well it works was not checked yet."
    return {"badge": "test_printed", "label": "Test-printed", "detail": detail,
            "prints": [{"printer": e["printer"], "printed_on": e["printed_on"], "result": e["result"]} for e in good]}


def count_test_printed(item_ids) -> int:
    db = PRINTS.read()
    return sum(1 for i in item_ids if proof(i, db)["badge"] == "test_printed")
