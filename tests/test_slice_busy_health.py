"""A second FDM slice of the same job is 409, and a heavy resin prepare does not stall /healthz."""
import json
import os
import shutil
import socket
import struct
import threading
import time
from pathlib import Path

import httpx
import pytest
import trimesh
import uvicorn

from app.main import app
from app.services import slice_engine as eng
from app.services import slice_inflight
from app.services.history import store

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.filterwarnings("ignore:Using `httpx` with `starlette.testclient`:DeprecationWarning")


def _stl_box(path: Path) -> None:
    tri = [(0, 0, 0), (30, 0, 0), (30, 30, 30)]
    data = b"\0" * 80 + struct.pack("<I", 1)
    data += struct.pack("<12fH", 0, 0, 1, *[c for v in tri for c in v], 0)
    path.write_bytes(data)


def _serve():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    return server, thread, port


def _stop(server, thread):
    server.should_exit = True
    thread.join(5)


def test_same_job_is_409_on_both_fdm_routes(monkeypatch):
    """While one slice of a job is inside the engine, both FDM routes refuse that job."""
    slice_inflight.reset()
    started = threading.Event()
    release = threading.Event()

    def fake_engine(*_a, **_k):
        if not started.is_set():
            started.set()
            assert release.wait(8)
        raise eng.SliceError("slice_failed", "stopped", 500)

    def fake_legacy(*_a, **_k):
        if not started.is_set():
            started.set()
            assert release.wait(8)
        return {"available": True, "ok": False, "message": "stopped"}

    monkeypatch.setattr(eng, "slice_model_path", fake_engine)
    monkeypatch.setattr("app.api.printing._slice", fake_legacy)
    server, thread, port = _serve()
    base = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(base_url=base, timeout=20) as setup:
            signed = setup.post("/api/me/signup", json={"display_name": "Ada Adult", "dob": "1985-05-05"})
            assert signed.status_code == 200, signed.text
            sid = setup.cookies["p3d_sid"]
        for bid in ("jobbusy01", "jobbusy02"):
            folder = store.dir(bid)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "meta.json").write_text(json.dumps({
                "id": bid, "owner_sid": sid, "visibility": "private",
                "created": "2020-01-01T00:00:00+00:00",
            }))
            _stl_box(folder / "model.stl")
        cookies = {"p3d_sid": sid}
        holder = {}

        def lead():
            with httpx.Client(base_url=base, timeout=20, cookies=cookies) as client:
                holder["response"] = client.post("/api/slice", data={"model_id": "jobbusy01"})

        worker = threading.Thread(target=lead, daemon=True)
        worker.start()
        assert started.wait(8), "the first slice never reached the engine"
        with httpx.Client(base_url=base, timeout=5, cookies=cookies) as client:
            other = client.post("/api/slice", data={"model_id": "jobbusy02"})
            again = client.post("/api/slice", data={"model_id": "jobbusy01"})
            legacy = client.post("/api/slice/jobbusy01", data={"layer_height": "0.2"})
        assert other.status_code != 409 or other.json().get("detail", {}).get("code") != "busy"
        assert again.status_code == 409 and again.json()["detail"]["code"] == "busy"
        assert "still working" in again.json()["detail"]["message"]
        assert legacy.status_code == 409 and legacy.json()["detail"]["code"] == "busy"
        assert "still working" in legacy.json()["detail"]["message"]
        release.set()
        worker.join(8)
        assert holder["response"].status_code == 500

        started.clear()
        release.clear()

        def legacy_lead():
            with httpx.Client(base_url=base, timeout=20, cookies=cookies) as client:
                holder["legacy"] = client.post("/api/slice/jobbusy01", data={"layer_height": "0.2"})

        worker = threading.Thread(target=legacy_lead, daemon=True)
        worker.start()
        assert started.wait(8), "the legacy slice never started"
        with httpx.Client(base_url=base, timeout=5, cookies=cookies) as client:
            modern = client.post("/api/slice", data={"model_id": "jobbusy01"})
        assert modern.status_code == 409 and modern.json()["detail"]["code"] == "busy"
        release.set()
        worker.join(8)
        assert holder["legacy"].status_code == 200
    finally:
        release.set()
        _stop(server, thread)
        slice_inflight.reset()
        for bid in ("jobbusy01", "jobbusy02"):
            shutil.rmtree(store.dir(bid), ignore_errors=True)


def test_healthz_stays_200_during_heavy_prepare(tmp_path, monkeypatch):
    """Prepare's CPU hold runs in a fresh process, so /healthz keeps answering 200."""
    from app.api import resin as resin_api
    report = tmp_path / "worker.json"
    resin_api._HEAVY_PARENT_MARK = True
    monkeypatch.setenv("ZEIM_HEAVY_HOLD_S", "1.5")
    monkeypatch.setenv("ZEIM_HEAVY_REPORT", str(report))
    server, thread, port = _serve()
    base = f"http://127.0.0.1:{port}"
    done = threading.Event()
    result = {}
    try:
        mesh = trimesh.creation.box(extents=[10, 10, 10]).export(file_type="stl")

        def post():
            with httpx.Client(base_url=base, timeout=90) as client:
                response = client.post(
                    "/api/resin/prepare",
                    data={"hollow": "false", "supports": "false", "tilt_deg": "0"},
                    files={"file": ("cube.stl", mesh, "model/stl")},
                )
                result["status"] = response.status_code
                result["body"] = response.text[:800]
            done.set()

        threading.Thread(target=post, daemon=True).start()
        statuses = []
        latencies = []
        deadline = time.perf_counter() + 60
        with httpx.Client(base_url=base, timeout=1.0) as client:
            while not done.is_set():
                if time.perf_counter() > deadline:
                    raise AssertionError("prepare did not finish: " + result.get("body", ""))
                started = time.perf_counter()
                health = client.get("/healthz")
                latencies.append(time.perf_counter() - started)
                statuses.append(health.status_code)
                time.sleep(0.05)
        assert result["status"] == 200, result["body"]
        assert len(statuses) >= 3
        assert set(statuses) == {200}
        assert max(latencies) < 1.0
        info = json.loads(report.read_text())
        assert info["saw_parent_mark"] is False
        assert info["pid"] != os.getpid()
    finally:
        resin_api._HEAVY_PARENT_MARK = False
        _stop(server, thread)


def test_slice_pages_show_still_working_instead_of_success():
    printer = (ROOT / "static" / "printer.js").read_text(encoding="utf-8")
    page = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    for src in (printer, page):
        assert 'detail?.code === "busy"' in src
        assert "This slice is still working." in src
        assert "still working" in src
