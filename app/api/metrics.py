"""First-party usage counts (ONB1). Minimal by design.

One event is accepted: "first_print", sent once per browser when someone downloads their first print file. It carries
only a coarse time bucket (how long since this browser first opened ZEIM). Nothing else is stored: no account, session,
browser id, IP, file or model. Lines go to DATA/metrics/<YYYY-MM>.jsonl as {"d": day, "e": event, "b": bucket}.
The browser does not send it when Do Not Track / Global Privacy Control is on, or when the person turned usage counts off.
Read with: python -m app.api.metrics
"""
from __future__ import annotations

import json
import time
from collections import Counter

from fastapi import APIRouter, HTTPException, Request

from app import config
from app.api.textcap import ip as client_ip
from app.core import ratelimit

router = APIRouter(prefix="/api", tags=["metrics"])

# Upper edges in seconds -> label. Order matters.
BUCKETS = ((60, "<1m"), (300, "1-5m"), (900, "5-15m"), (3600, "15-60m"), (86400, "1-24h"), (7 * 86400, "1-7d"))


def bucket(secs: float) -> str:
    for edge, label in BUCKETS:
        if secs < edge:
            return label
    return ">7d"


def _folder():
    return config.DATA / "metrics"


@router.post("/metrics")
def post_metric(body: dict, request: Request):
    if body.get("event") != "first_print":
        raise HTTPException(400, "Unknown event.")
    try:
        secs = float(body.get("secs"))
    except (TypeError, ValueError):
        raise HTTPException(400, "secs must be a number.")
    if not 0 <= secs < 10 ** 9:
        raise HTTPException(400, "secs out of range.")
    # The IP is used only for this in-memory limit; it is never written.
    if not config.TESTING_MODE and not ratelimit.hit("metrics:" + client_ip(request), 20, 3600):
        raise HTTPException(429, "Too many.")
    f = _folder(); f.mkdir(parents=True, exist_ok=True)
    rec = {"d": time.strftime("%Y-%m-%d", time.gmtime()), "e": "first_print", "b": bucket(secs)}
    with open(f / (rec["d"][:7] + ".jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return {"ok": True}


def summary() -> dict:
    """Counts of first_print per time bucket, all months."""
    c: Counter = Counter()
    for p in sorted(_folder().glob("*.jsonl")) if _folder().exists() else []:
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("e") == "first_print":
                c[r.get("b")] += 1
    order = [l for _, l in BUCKETS] + [">7d"]
    return {"first_print": {k: c[k] for k in order if c[k]}, "total": sum(c.values())}


if __name__ == "__main__":
    print(json.dumps(summary(), indent=2))
