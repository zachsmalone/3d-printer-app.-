"""FEAT2: send / status / pause against local Moonraker and OctoPrint simulators.

These are simulators on 127.0.0.1, not printers. Passing here does not mean the K1 works;
HARDWARE_VERIFIED_TYPES stays empty until Zach runs docs/plans/feat2-feat10-printer-connectivity.md.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app import config
from app.services import printers


class _Sim(BaseHTTPRequestHandler):
    calls: list = []
    state = {"printing": None}

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        _Sim.calls.append(("POST", self.path, raw))
        if self.path == "/server/files/upload":
            if b'name="print"\r\n\r\ntrue' in raw:
                _Sim.state["printing"] = "cube.gcode"
            return self._send(201, {"result": {"item": {"path": "cube.gcode"}}})
        if self.path == "/api/files/local":
            if b'name="print"\r\n\r\ntrue' in raw:
                _Sim.state["printing"] = "cube.gcode"
            return self._send(201, {"done": True})
        if self.path.startswith("/printer/print/"):
            return self._send(200, {"result": "ok"})
        if self.path == "/api/job":
            return self._send(204, {})
        return self._send(404, {})

    def do_GET(self):
        _Sim.calls.append(("GET", self.path, b""))
        if self.path.startswith("/printer/objects/query"):
            p = _Sim.state["printing"]
            return self._send(200, {"result": {"status": {
                "print_stats": {"state": "printing" if p else "standby", "filename": p or ""},
                "display_status": {"progress": 0.1 if p else 0},
                "extruder": {"temperature": 210, "target": 210}, "heater_bed": {"temperature": 60, "target": 60}}}})
        if self.path == "/api/job":
            p = _Sim.state["printing"]
            return self._send(200, {"state": "Printing" if p else "Operational", "job": {"file": {"name": p}},
                                    "progress": {"completion": 10 if p else None}})
        if self.path == "/api/printer":
            return self._send(200, {"temperature": {"tool0": {"actual": 210, "target": 210}, "bed": {"actual": 60, "target": 60}}})
        return self._send(404, {})


@pytest.fixture
def sim(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEIM_PRINTER_DIRECT", "1")
    monkeypatch.setattr(config, "BLOCK_PRIVATE_PRINTERS", False, raising=False)
    monkeypatch.setattr(config, "MODE", "local", raising=False)
    _Sim.calls.clear()
    _Sim.state["printing"] = None
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Sim)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    g = tmp_path / "cube.gcode"
    g.write_text("G28\nG1 X10 Y10\n")
    yield f"http://127.0.0.1:{srv.server_address[1]}", g
    srv.shutdown()


def test_direct_is_off_on_production_by_default(monkeypatch):
    monkeypatch.delenv("ZEIM_PRINTER_DIRECT", raising=False)
    monkeypatch.setenv("ZEIM_ENV", "production")
    r = printers.send({"type": "moonraker", "url": "http://127.0.0.1:1"}, None, "x.gcode", True)
    assert r["ok"] is False and "download" in r["message"].lower()


@pytest.mark.parametrize("ptype", ["moonraker", "octoprint"])
def test_upload_without_start_does_not_start(sim, ptype):
    url, g = sim
    r = printers.send({"type": ptype, "url": url, "name": "Sim"}, g, "cube.gcode", False)
    assert r["ok"] and r["start"] == "not_requested"
    assert _Sim.state["printing"] is None


@pytest.mark.parametrize("ptype", ["moonraker", "octoprint"])
def test_upload_and_start_is_confirmed_only_by_status(sim, ptype):
    url, g = sim
    r = printers.send({"type": ptype, "url": url, "name": "Sim"}, g, "cube.gcode", True)
    assert r["ok"] and r["transfer"] == "accepted"
    assert r["start"] == "confirmed"
    assert "Not Hardware-tested" in r["message"]


def test_moonraker_pause_is_accepted_not_confirmed(sim):
    url, _ = sim
    r = printers.control({"type": "moonraker", "url": url}, "pause")
    assert r["ok"] and r["accepted"] and r["confirmed"] is False
    assert ("POST", "/printer/print/pause", b"") in _Sim.calls


def test_hardware_verified_is_still_empty():
    assert printers.HARDWARE_VERIFIED_TYPES == set()
