import json
import pytest
from app import research_budget as budget


def plans():
    return {p["id"]: p for p in budget.load_plans()["plans"]}


def test_three_sourced_plans():
    data = budget.load_plans()
    assert data["checked_on"] == "2026-10-12"
    assert len(data["plans"]) == 3
    assert all(p["sources"] for p in data["plans"])


@pytest.mark.parametrize("pid,expected", [("digitalocean-basic-2g", "12.00"), ("vultr-regular-2g", "10.00"), ("render-1c-2g-hobby", "30.00")])
def test_base_prices(pid, expected):
    result = budget.estimate(plans()[pid])
    assert result["subtotal_monthly_usd"] == expected
    assert result["under_budget"]


def test_render_transfer():
    result = budget.estimate(plans()["render-1c-2g-hobby"], transfer_gb=105)
    assert result["subtotal_monthly_usd"] == "45.00"


def test_unknown_transfer_not_free():
    result = budget.estimate(plans()["vultr-regular-2g"], transfer_gb=100)
    assert "transfer overage rate unknown; not included" in result["exclusions"]


def test_fixed_capacity_rejected():
    with pytest.raises(ValueError):
        budget.estimate(plans()["vultr-regular-2g"], storage_gb=50, reserve_gb=10)


def test_domain_amortization():
    result = budget.estimate(plans()["vultr-regular-2g"], annual_domain_usd="11.08")
    assert result["subtotal_monthly_usd"] == "10.92"


def test_exact_budget_is_not_under():
    assert not budget.estimate(plans()["vultr-regular-2g"], budget_usd=10)["under_budget"]


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), True, None, "broken"])
def test_invalid_amount(bad):
    with pytest.raises(ValueError):
        budget.estimate(plans()["vultr-regular-2g"], storage_gb=bad)


def test_missing_sources(tmp_path, monkeypatch):
    data = budget.load_plans()
    data["plans"][0]["sources"] = []
    path = tmp_path / "data.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(budget, "DATA_FILE", path)
    with pytest.raises(ValueError):
        budget.load_plans()


def test_duplicate_id(tmp_path, monkeypatch):
    data = budget.load_plans()
    data["plans"][1]["id"] = data["plans"][0]["id"]
    path = tmp_path / "data.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(budget, "DATA_FILE", path)
    with pytest.raises(ValueError):
        budget.load_plans()
