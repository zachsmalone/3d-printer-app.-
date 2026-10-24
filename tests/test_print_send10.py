"""Print-send10: status, control, camera, bambu limits, spool, queue, board, alerts, timelapse (Simulated)."""
from __future__ import annotations

import os
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, UploadFile
from fastapi.responses import Response
from fastapi.testclient import TestClient

from app.main import app
from app.services import printers, print_queue, print_watch, settings
from tests.b1 import ADULT, ADMIN, client as b1_client


def _free_port():
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def _mock_octo(port):
    m = FastAPI()
    state = {"job": "Printing", "paused": False}

    @m.get("/api/version")
    def version():
        return {"server": "mock-1.0", "api": "0.1"}

    @m.get("/api/job")
    def job():
        return {"state": state["job"], "job": {"file": {"name": "demo.gcode"}},
                "progress": {"completion": 42.5, "printTime": 100, "printTimeLeft": 200}}

    @m.get("/api/printer")
    def printer():
        return {"state": {"text": state["job"], "flags": {"printing": state["job"] == "Printing"}},
                "temperature": {"tool0": {"actual": 200, "target": 210}, "bed": {"actual": 60, "target": 60}}}

    @m.get("/api/settings")
    def sett():
        return {"webcam": {"snapshotUrl": "/webcam/?action=snapshot"}}

    @m.get("/webcam/")
    def cam(action: str = ""):
        # minimal JPEG (1x1)
        return Response(bytes.fromhex(
            "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707"
            "070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c"
            "1c2837292c30313434341f27393d38323c2e333432ffdb0043010909090c0b0c180d"
            "0d1832211c2132323232323232323232323232323232323232323232323232323232"
            "323232323232323232323232323232323232323232ffc00011080001000103011100"
            "021101031101ffc40014000100000000000000000000000000000000ffc400141001"
            "00000000000000000000000000000000ffda000c0301000210031000003f00bf80ffd9"
        ), media_type="image/jpeg")

    @m.post("/api/job")
    async def control(body: dict):
        cmd = body.get("command")
        if cmd == "cancel":
            state["job"] = "Operational"
        elif cmd == "pause":
            act = body.get("action")
            if act == "pause":
                state["job"] = "Paused"; state["paused"] = True
            elif act == "resume":
                state["job"] = "Printing"; state["paused"] = False
        return Response(status_code=204)

    @m.post("/api/files/local")
    async def upload(file: UploadFile):
        await file.read()
        return {"done": True}

    srv = uvicorn.Server(uvicorn.Config(m, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    return state


@pytest.fixture
def adult():
    return b1_client(ADULT)


def test_bambu_limits_document_developer_mode(adult):
    r = adult.get("/api/bambu/limits").json()
    assert r["needs_developer_mode_for_control"] is True
    assert r["fallback"] == "Open in Bambu Studio"
    assert r["verification"] == "Simulated"
    assert "Developer Mode" in r["note"]


def test_status_control_camera_spool_queue_board(adult, tmp_path, monkeypatch):
    monkeypatch.delenv("ZEIM_ENV", raising=False)
    assert printers.direct_control_enabled()
    port = _free_port()
    _mock_octo(port)
    r = adult.put("/api/settings", json={"printers": [{
        "name": "Mock Octo", "type": "octoprint",
        "url": f"http://127.0.0.1:{port}", "api_key": "k",
        "spool_remaining_g": 500, "alert_done": True, "alert_failed": True,
        "watch_failures": False, "timelapse": True,
    }]}, headers=ADMIN)
    assert r.status_code == 200, r.text
    pid = r.json()["printers"][0]["id"]

    st = adult.get(f"/api/printers/{pid}/status").json()
    assert st["ok"] and st["state"] == "Printing" and st["progress_pct"] == 42.5
    assert st["verification"] == "Simulated"

    cam = adult.get(f"/api/printers/{pid}/camera")
    assert cam.status_code == 200 and cam.headers["content-type"].startswith("image/")
    assert cam.headers.get("X-ZEIM-Verification") == "Simulated"
    assert len(cam.content) > 50

    fd = {"action": "pause"}
    pause = adult.post(f"/api/printers/{pid}/control", data=fd).json()
    assert pause["ok"] and pause["action"] == "pause"
    st2 = adult.get(f"/api/printers/{pid}/status").json()
    assert st2["state"] == "Paused"
    assert adult.post(f"/api/printers/{pid}/control", data={"action": "resume"}).json()["ok"]

    # spool unit
    pr = settings.get_printer(pid)
    assert printers.spool_check(pr, 100)["ok"] is True
    bad = printers.spool_check(pr, 900)
    assert bad["ok"] is False and bad["checked"] is True

    # queue
    # need a real build id — create a minimal history entry
    from app.services.history import store
    bid = "abcd1234"
    d = store.dir(bid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "model.gcode").write_text("; fake gcode\nG1 X0\n")
    # meta_for may require history entry
    try:
        store.add({"id": bid, "title": "q", "mode": "relief", "beginner": True})
    except Exception:
        pass

    # enqueue via API may 404 without real build — test service layer
    q = print_queue.enqueue(pid, bid, name="queued job")
    assert q["ok"], q
    jobs = print_queue.list_jobs()["jobs"]
    assert any(j["id"] == q["job"]["id"] for j in jobs)
    started = print_queue.start_job(q["job"]["id"])
    assert started["ok"], started

    board = adult.get("/api/printers/board").json()
    assert board["verification"] == "Simulated"
    assert any(p["id"] == pid for p in board["printers"])

    tl = adult.post(f"/api/printers/{pid}/timelapse/start").json()
    assert tl["ok"] and tl["verification"] == "Simulated"
    tick = adult.post(f"/api/printers/{pid}/timelapse/tick").json()
    assert tick["ok"] and tick["frames"] >= 1
    assert adult.post(f"/api/printers/{pid}/timelapse/stop").json()["ok"]


def test_bambu_mock_send_and_control(adult, monkeypatch):
    monkeypatch.setenv("ZEIM_BAMBU_MOCK", "1")
    r = adult.put("/api/settings", json={"printers": [{
        "name": "Bambu", "type": "bambu",
        "url": "http://192.168.1.50", "api_key": "12345678", "serial": "01P00ATEST0001",
    }]}, headers=ADMIN)
    assert r.status_code == 200, r.text
    pid = r.json()["printers"][0]["id"]
    pr = settings.get_printer(pid)
    out = printers.send(pr, None, "demo.gcode", True)
    assert out["ok"] and out.get("mock") and out["verification"] == "Simulated"
    assert out["fallback"] == "bambu_studio"
    st = printers.status(pr)
    assert st["ok"] and st["type"] == "bambu"
    ctl = printers.control(pr, "pause")
    assert ctl["ok"] and ctl["action"] == "pause"


def test_failure_watch_pauses_only(monkeypatch):
    monkeypatch.setenv("ZEIM_BAMBU_MOCK", "1")
    # Direct unit: error state → pause, never cancel
    calls = []
    pr = {"id": "x1", "name": "P", "type": "bambu", "url": "http://192.168.1.9",
          "api_key": "12345678", "serial": "S1", "watch_failures": True}

    def fake_control(p, action):
        calls.append(action)
        return {"ok": True, "action": action}

    monkeypatch.setattr(printers, "control", fake_control)
    # seed prev printing state
    print_watch._save_state({"printers": {"x1": {"state": "printing", "progress_pct": 10, "ts": time.time() - 5}}, "alerts": []})
    paused = print_watch._maybe_pause_on_failure(pr, {"ok": True, "state": "error", "progress_pct": 10})
    assert paused and paused["pause"]["action"] == "pause"
    assert calls == ["pause"]
    assert "cancel" not in calls


def test_verification_tag_default_simulated():
    assert printers.HARDWARE_VERIFIED is False
    assert printers.verification_tag() == "Simulated"


def test_settings_exposes_direct_control_and_bambu(adult):
    s = adult.get("/api/settings", headers=ADMIN).json()
    assert "direct_control" in s and "printer_verification" in s and "bambu_limits" in s
    assert any(t["type"] == "bambu" and t["implemented"] for t in s["printer_types"])
