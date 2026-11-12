"""CAD edits must not stall /healthz, and a stale slot write must not 500.

A heavy step used to os.fork() the web process while other threads were inside
NumPy. Python 3.12 stops the world for that fork and waits forever on an
OpenBLAS thread, so the async /healthz probe never ran. The slot write raced
the step and raised "Those parts don't match this model."
"""
import json
import os
import shutil
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import trimesh
import uvicorn
from fastapi.testclient import TestClient

from app.core import guard, meshparts
from app.main import app
from app.services import editproj
from app.services.history import store

pytestmark = pytest.mark.filterwarnings("ignore:Using `httpx` with `starlette.testclient`:DeprecationWarning")


def _rss_mb() -> float:
    with open("/proc/self/status") as fh:
        for line in fh:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    return 0.0


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


def _boxes(n: int, radius_faces: int) -> bytes:
    spheres = []
    for i in range(n):
        sphere = trimesh.creation.icosphere(subdivisions=radius_faces, radius=8)
        sphere.apply_translation((i * 30, 0, 0))
        spheres.append(sphere)
    return trimesh.util.concatenate(spheres).export(file_type="stl")


def test_stale_slot_ids_match_the_current_mesh():
    """Ids from before the part list stopped matching the mesh are ignored, not a 500."""
    client = TestClient(app)
    opened = client.post("/api/edit/new", files={"file": ("two.stl", _boxes(2, 2), "model/stl")}, data={"title": "Two"})
    assert opened.status_code == 200, opened.text
    bid = opened.json()["id"]
    detected = client.post(f"/api/edit/{bid}/parts/detect")
    assert detected.status_code == 200, detected.text
    old_ids = [p["id"] for p in detected.json()["parts"]]
    assert len(old_ids) >= 2
    meta = store.get(bid)
    meta["parts"][0]["mesh"]["runs"] = [[0, 1]]
    store.save(meta)
    editproj._STATES.pop(bid, None)
    stale = client.put(f"/api/edit/{bid}/parts/slots", json={
        "action": "assign", "ids": old_ids + ["gone"], "slot": 2, "slot_count": 4,
        "colours": ["#FFFFFF", "#FF0000", "#00AA00", "#0000FF"],
    })
    assert stale.status_code == 200, stale.text
    assert "don't match" not in stale.text
    n_faces = len(editproj.mesh_at(bid).faces)
    saved = store.get(bid).get("parts")
    assert meshparts.validate(saved, n_faces), saved
    gone = client.put(f"/api/edit/{bid}/parts/slots", json={
        "action": "assign", "ids": ["gone"], "slot": 1, "slot_count": 4,
    })
    assert gone.status_code == 200, gone.text
    assert meshparts.validate(store.get(bid).get("parts"), n_faces)


def test_healthz_answers_during_concurrent_edits(tmp_path, monkeypatch):
    """op, scene, slots and undo together keep /healthz under a second and the heap bounded.

    The heavy step's process must be a fresh interpreter: it does not see a mark set only
    on the server's loaded module.
    """
    report = tmp_path / "guard"
    monkeypatch.setenv("ZEIM_GUARD_REPORT", str(report))
    guard._inherited_mark = "web"
    server, thread, port = _serve()
    base = f"http://127.0.0.1:{port}"
    bid = None
    try:
        with httpx.Client(base_url=base, timeout=120) as setup:
            opened = setup.post("/api/edit/new", files={"file": ("parts.stl", _boxes(4, 4), "model/stl")}, data={"title": "Parts"})
            assert opened.status_code == 200, opened.text
            bid = opened.json()["id"]
            assert opened.json()["analysis"]["triangles"] >= 20_000
            detected = setup.post(f"/api/edit/{bid}/parts/detect")
            assert detected.status_code == 200, detected.text
            assert len(detected.json()["parts"]) >= 2
            cookies = dict(setup.cookies)
        base_rss = _rss_mb()
        stop = threading.Event()
        health = {"slow": [], "codes": [], "rss": [base_rss]}

        def probe():
            with httpx.Client(base_url=base, timeout=1.0) as client:
                while not stop.is_set():
                    started = time.perf_counter()
                    try:
                        response = client.get("/healthz")
                    except httpx.TimeoutException:
                        health["slow"].append(1.0)
                        health["codes"].append(0)
                        continue
                    elapsed = time.perf_counter() - started
                    health["codes"].append(response.status_code)
                    if elapsed >= 1.0:
                        health["slow"].append(elapsed)
                    health["rss"].append(_rss_mb())
                    time.sleep(0.05)

        watcher = threading.Thread(target=probe, daemon=True)
        watcher.start()
        outcomes = []
        barrier = threading.Barrier(4)

        def hammer():
            barrier.wait(10)
            with httpx.Client(base_url=base, timeout=120, cookies=cookies) as client:
                calls = (
                    ("POST", f"/api/edit/{bid}/op", {"op": "translate", "params": {"dx": 1, "dy": 0, "dz": 0}}),
                    ("GET", f"/api/cad/{bid}/scene", None),
                    ("PUT", f"/api/edit/{bid}/parts/slots", {
                        "action": "prepare", "slot_count": 4,
                        "colours": ["#FFFFFF", "#FF0000", "#00AA00", "#0000FF"],
                    }),
                    ("POST", f"/api/edit/{bid}/undo", {}),
                )
                for method, url, payload in calls:
                    if method == "GET":
                        response = client.get(url)
                    elif method == "PUT":
                        response = client.put(url, json=payload)
                    else:
                        response = client.post(url, json=payload or {})
                    outcomes.append((method, response.status_code, response.text[:240]))

        workers = [threading.Thread(target=hammer, daemon=True) for _ in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(180)
        stop.set()
        watcher.join(2)
        assert all(not worker.is_alive() for worker in workers), "an edit never returned"
        assert health["codes"], "health probe never ran"
        assert not health["slow"], health["slow"]
        assert set(health["codes"]) == {200}
        assert max(health["rss"]) - base_rss < 400, (base_rss, max(health["rss"]))
        bad = [row for row in outcomes if row[1] >= 500 and row[1] != 503]
        assert not bad, bad
        assert any(row[1] == 200 for row in outcomes), outcomes
        reports = list(Path(report).glob("*.json"))
        assert reports, "the heavy step never left the web process"
        for path in reports:
            info = json.loads(path.read_text(encoding="utf-8"))
            assert info["spawn_mark"] is None
            assert info["pid"] != os.getpid()
        still = httpx.get(base + "/healthz", timeout=1.0)
        assert still.status_code == 200 and still.elapsed.total_seconds() < 1.0
    finally:
        guard._inherited_mark = None
        _stop(server, thread)
        if bid:
            shutil.rmtree(store.dir(bid), ignore_errors=True)
