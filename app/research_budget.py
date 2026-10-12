"""Offline pilot cost estimator. Never provisions resources or guesses unknown fees."""
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlsplit

DATA_FILE = Path(__file__).resolve().parent / "data" / "research" / "pilot_hosting.json"


def number(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not an amount")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid amount") from None
    if not result.is_finite() or result < 0:
        raise ValueError("Expected a finite nonnegative amount")
    return result


def load_plans():
    with DATA_FILE.open(encoding="utf-8") as stream:
        data = json.load(stream)
    if data.get("currency") != "USD" or not isinstance(data.get("plans"), list):
        raise ValueError("Expected USD plan data")
    ids = set()
    for plan in data["plans"]:
        if plan["id"] in ids:
            raise ValueError("Duplicate plan ID")
        ids.add(plan["id"])
        for key in ("base_monthly_usd", "included_storage_gb", "disk_usd_per_gb_month"):
            number(plan[key])
        for key in ("included_transfer_gb", "transfer_usd_per_gb"):
            if plan[key] is not None:
                number(plan[key])
        if not plan.get("sources"):
            raise ValueError("Missing sources")
        for url in plan["sources"]:
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError("Invalid source URL")
    return data


def estimate(plan, *, storage_gb=20, transfer_gb=None, reserve_gb=0,
             extra_monthly_usd=0, annual_domain_usd=0, budget_usd=80):
    """Return a base subtotal plus explicit exclusions and strict budget result.

    reserve_gb is caller-supplied OS/app headroom on a shared VM disk. It is
    not a verified provider requirement. Unknown transfer prices stay unknown.
    """
    storage = number(storage_gb) + number(reserve_gb)
    included = number(plan["included_storage_gb"])
    rate = number(plan["disk_usd_per_gb_month"])
    overflow = max(Decimal(0), storage - included)
    if overflow and not rate:
        raise ValueError("Requested capacity exceeds this fixed disk plan")
    disk_cost = overflow * rate
    total = number(plan["base_monthly_usd"]) + disk_cost
    exclusions = ["taxes", "unpriced backups/database/workers", "performance not benchmarked"]
    if transfer_gb is None:
        exclusions.append("transfer overage not assessed")
    else:
        requested = number(transfer_gb)
        if plan["included_transfer_gb"] is None or plan["transfer_usd_per_gb"] is None:
            exclusions.append("transfer overage rate unknown; not included")
        else:
            total += max(Decimal(0), requested - number(plan["included_transfer_gb"])) * number(plan["transfer_usd_per_gb"])
    total += number(extra_monthly_usd) + number(annual_domain_usd) / Decimal(12)
    return {"id": plan["id"], "subtotal_monthly_usd": str(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "under_budget": total < number(budget_usd), "exclusions": exclusions,
            "sources": list(plan["sources"])}


if __name__ == "__main__":
    print(json.dumps([estimate(p) for p in load_plans()["plans"]], indent=2))
