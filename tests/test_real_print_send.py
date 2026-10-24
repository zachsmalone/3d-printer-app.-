"""Real Moonraker / OctoPrint send path (mocked network) + honest Live API vs Simulated labels.

No live hardware required. Verifies:
- Moonraker upload + connection test hit real HTTP clients and return verification=Live API
- OctoPrint upload returns Live API
- Bambu stays Simulated
- Unconfigured / missing gcode never fakes a successful send
- UI strings stay honest (Live API for Moonraker/OctoPrint; Simulated for Bambu)
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import Response
from fastapi.testclient import TestClient

from app.services import printers, settings
from tests.b1 import ADULT, ADMIN, client as b1_client


def _free_port():
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def _mock_moonraker(port):
    m = FastAPI()
    state = {"uploads": [], "print": False, "klippy": "ready", "printer": "ready"}

    @m.get("/server/info")
    def info():
        return {"result": {"klippy_state": state["klippy"], "moonraker_version": "v0.9-mock"}}

    @m.get("/printer/info")
    def printer_info():
        return {"result": {"state": state["printer"]}}

    @m.get("/printer/objects/query")
    def objects(print_stats: str = "", heater_bed: str = "", extruder: str = "", display_status: str = ""):
        return {"result": {"status": {
            "print_stats": {"state": "printing" if state["print"] else "standby",
                            "filename": "photo3d_demo.gcode", "print_duration": 12, "total_duration": 12},
            "display_status": {"progress": 0.25},
            "heater_bed": {"temperature": 60, "target": 60},
            "extruder": {"temperature": 200, "target": 210},
        }}}

    @m.post("/server/files/upload")
    async def upload(request: Request, file: UploadFile):
        form = await request.form()
        data = await file.read()
        print_flag = str(form.get("print") or "false")
        state["uploads"].append({"name": file.filename, "n": len(data), "print": print_flag})
        if print_flag.lower() in ("true", "1"):
            state["print"] = True
        return {"result": {"item": {"path": f"gcodes/{file.filename}"}}}

    @m.post("/printer/print/pause")
    def pause():
        return {"result": "ok"}

    @m.post("/printer/print/resume")
    def resume():
        return {"result": "ok"}

    @m.post("/printer/print/cancel")
    def cancel():
        state["print"] = False
        return {"result": "ok"}

    srv = uvicorn.Server(uvicorn.Config(m, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    return state


def _mock_octo_upload(port):
    m = FastAPI()
    state = {"uploads": []}

    @m.get("/api/version")
    def version():
        return {"server": "mock-octo", "api": "0.1"}

    @m.post("/api/files/local")
    async def upload(request: Request, file: UploadFile):
        form = await request.form()
        data = await file.read()
        state["uploads"].append({"name": file.filename, "n": len(data),
                                 "print": str(form.get("print") or "false")})
        return {"files": {"local": {"name": file.filename}}}

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


def test_moonraker_send_and_test_live_api(adult, tmp_path, monkeypatch):
    monkeypatch.delenv("ZEIM_ENV", raising=False)
    assert printers.direct_control_enabled()
    port = _free_port()
    st = _mock_moonraker(port)
    r = adult.put("/api/settings", json={"printers": [{
        "name": "Zach K1 mock", "type": "moonraker", "profile": "creality_k1",
        "url": f"http://127.0.0.1:{port}", "api_key": "",
    }]}, headers=ADMIN)
    assert r.status_code == 200, r.text
    pid = r.json()["printers"][0]["id"]
    pr = settings.get_printer(pid)

    conn = printers.test(pr)
    assert conn["ok"], conn
    assert conn["verification"] == "Live API"
    assert "Live API" in conn["message"]
    assert conn.get("hardware_verified") is False

    gcode = tmp_path / "model.gcode"
    gcode.write_text("; ZEIM mock\nG28\nG1 X10\n")
    out = printers.send(pr, gcode, "photo3d_demo.gcode", start=True)
    assert out["ok"], out
    assert out["verification"] == "Live API"
    assert "Live API" in out["message"]
    assert "Hardware-tested" in out["message"]  # clarifies not yet
    assert st["uploads"] and st["uploads"][-1]["name"] == "photo3d_demo.gcode"
    assert st["print"] is True

    status = printers.status(pr)
    assert status["ok"] and status["verification"] == "Live API"

    ctl = printers.control(pr, "pause")
    assert ctl["ok"] and ctl["verification"] == "Live API"


def test_octoprint_send_live_api(tmp_path, monkeypatch):
    monkeypatch.delenv("ZEIM_ENV", raising=False)
    port = _free_port()
    st = _mock_octo_upload(port)
    pr = {"id": "o1", "name": "Octo", "type": "octoprint",
          "url": f"http://127.0.0.1:{port}", "api_key": "k"}
    gcode = tmp_path / "a.gcode"
    gcode.write_text("G28\n")
    out = printers.send(pr, gcode, "a.gcode", start=False)
    assert out["ok"] and out["verification"] == "Live API"
    assert st["uploads"] and st["uploads"][-1]["n"] > 0


def test_send_missing_gcode_never_fakes_success(monkeypatch):
    monkeypatch.delenv("ZEIM_ENV", raising=False)
    pr = {"id": "m1", "name": "K1", "type": "moonraker", "url": "http://127.0.0.1:9"}
    out = printers.send(pr, None, "x.gcode", False)
    assert out["ok"] is False
    assert out["verification"] == "Live API"
    assert "No G-code" in out["message"]


def test_bambu_stays_simulated(monkeypatch):
    monkeypatch.setenv("ZEIM_BAMBU_MOCK", "1")
    monkeypatch.delenv("ZEIM_ENV", raising=False)
    pr = {"id": "b1", "name": "Bambu", "type": "bambu",
          "url": "http://192.168.1.50", "api_key": "12345678", "serial": "01P"}
    out = printers.send(pr, None, "demo.gcode", True)
    assert out["ok"] and out["verification"] == "Simulated"
    assert printers.verification_tag("bambu") == "Simulated"


def test_ui_honesty_strings():
    html = Path("static/index.html").read_text()
    js = Path("static/app.js").read_text()
    board = Path("static/printboard.js").read_text()
    assert "Live API" in html
    assert "Simulated" in html
    assert "Creality K1" in html or "K1" in html
    assert "printer_honesty" in js or "Live API" in js
    assert "board.note" in board
    # Must not claim a universal Simulated-only story anymore
    assert "Simulated until a real-hardware pass. Tested with a pretend printer only." not in html
