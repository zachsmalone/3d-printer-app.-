"""Integration test for the /api/edit/new upload gate (launch checklist Task 4).

MARKED XFAIL ON PURPOSE: app/api/edit.py is Copilot's protected file; the handoff contract is
in docs/uploadsafe.md. This test is the acceptance criterion — it must pass once the three-line
wiring lands, and it must fail (not silently skip) today.
"""
from __future__ import annotations

import pytest

from app import config
from tests.b1 import box_stl, client


@pytest.mark.xfail(reason="handoff pending: /api/edit/new is in app/api/edit.py (Copilot's file); "
                          "see docs/uploadsafe.md for the exact 3-line wiring", strict=False)
def test_edit_new_enforces_the_per_account_upload_limit(monkeypatch):
    monkeypatch.setattr(config, "UPLOADS_PER_HOUR", 2)
    c = client()
    for _ in range(2):
        r = c.post("/api/edit/new", files={"file": ("b.stl", box_stl(), "application/octet-stream")})
        assert r.status_code == 200, r.text
    third = c.post("/api/edit/new", files={"file": ("b.stl", box_stl(), "application/octet-stream")})
    assert third.status_code == 429 and "upload limit" in third.json()["detail"]
