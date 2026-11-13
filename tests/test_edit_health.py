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


def _nap(seconds):
    time.sleep(seconds)


def _pid():
    return os.getpid()


def _heavy_sphere():
    mesh = trimesh.creation.icosphere(subdivisions=5, radius=10)
    assert len(mesh.faces) == 20_480
    return mesh


def test_editor_busy_only_when_the_queue_is_full():
    """A full queue still says the same thing. A free place waits instead of refusing."""
    from app.services import editlane
    assert editlane.BUSY == "The editor is busy with other steps. Try again in a moment."
    release = threading.Event()

    def hold():
        release.wait(5)

    threads = [threading.Thread(target=lambda n=i: editlane.run(f"p{n}", hold)) for i in range(editlane.ADMIT)]
    for worker in threads:
        worker.start()
    try:
        deadline = time.monotonic() + 5
        while editlane.admitted() < editlane.ADMIT:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        with pytest.raises(editlane.Busy):
            editlane.run("overflow", lambda: None)
    finally:
        release.set()
        for worker in threads:
            worker.join(5)
        assert all(not worker.is_alive() for worker in threads)
    editlane.run("after", lambda: None)


def test_one_project_runs_one_edit_at_a_time_and_two_projects_overlap():
    from app.services import editlane
    order = []
    gate = threading.Lock()

    def work(tag):
        def inner():
            with gate:
                order.append("start")
            time.sleep(0.05)
            with gate:
                order.append("end")
        editlane.run("same", inner)

    pair = [threading.Thread(target=work, args=(n,)) for n in (1, 2)]
    for worker in pair:
        worker.start()
    for worker in pair:
        worker.join(5)
    assert order == ["start", "end", "start", "end"]

    started = threading.Barrier(2)

    def together(project):
        def inner():
            started.wait(2)
        editlane.run(project, inner)

    both = [threading.Thread(target=together, args=(name,)) for name in ("a", "b")]
    for worker in both:
        worker.start()
    for worker in both:
        worker.join(5)
    assert all(not worker.is_alive() for worker in both)


def test_warm_pool_heavy_translate_is_under_half_a_second():
    """After the workers have imported, a 20,480-face move stays well under half a second."""
    from app.core import meshedit
    guard.warm()
    assert guard.worker_pids()
    assert all(pid != os.getpid() for pid in guard.worker_pids())
    from app.core import cadops
    mesh = _heavy_sphere()
    started = time.perf_counter()
    raw, _ = meshedit.op_translate(mesh, {"dx": 1, "dy": 0, "dz": 0})
    cadops.preserve_body_ids(mesh, meshedit._check(raw))
    in_process = time.perf_counter() - started
    meshedit.apply(mesh, "translate", {"dx": 0, "dy": 0, "dz": 0})
    samples = []
    for i in range(5):
        started = time.perf_counter()
        out, _ = meshedit.apply(mesh, "translate", {"dx": 1, "dy": 0, "dz": 0})
        samples.append(time.perf_counter() - started)
        assert len(out.faces) == 20_480
        assert abs(float(out.vertices[:, 0].mean() - mesh.vertices[:, 0].mean()) - 1) < 1e-6
    mean = sum(samples) / len(samples)
    print(
        f"WARM_POOL_TRANSLATE_S in_process={in_process:.4f} "
        f"min={min(samples):.4f} mean={mean:.4f} max={max(samples):.4f} "
        f"samples={[round(t, 4) for t in samples]}"
    )
    assert max(samples) < 0.5, samples


def test_worker_timeout_respawns_and_healthz_stays_up():
    """A stuck task is killed, the next task runs on a new worker, and /healthz stays under a second."""
    guard.warm()
    before = set(guard.worker_pids())
    assert before
    server, thread, port = _serve()
    base = f"http://127.0.0.1:{port}"
    stop = threading.Event()
    slow = []
    codes = []

    def probe():
        with httpx.Client(base_url=base, timeout=1.0) as client:
            while not stop.is_set():
                started = time.perf_counter()
                try:
                    response = client.get("/healthz")
                except httpx.TimeoutException:
                    slow.append(1.0)
                    codes.append(0)
                    continue
                if time.perf_counter() - started >= 1.0:
                    slow.append(time.perf_counter() - started)
                codes.append(response.status_code)
                time.sleep(0.05)

    watcher = threading.Thread(target=probe, daemon=True)
    watcher.start()
    try:
        with pytest.raises(guard.Tripped) as caught:
            guard.run(_nap, 30, timeout=0.4)
        assert caught.value.args[0] == "timeout"
        again = guard.run(_pid)
        assert again != os.getpid()
        assert again not in before
        assert guard.run(abs, -2) == 2
        stop.set()
        watcher.join(2)
        assert codes and set(codes) == {200}
        assert not slow, slow
        still = httpx.get(base + "/healthz", timeout=1.0)
        assert still.status_code == 200 and still.elapsed.total_seconds() < 1.0
    finally:
        stop.set()
        _stop(server, thread)


def test_worker_recycles_after_its_task_budget(monkeypatch):
    monkeypatch.setenv("PHOTO3D_HEAVY_TASKS", "1")
    guard.warm()
    first = guard.run(_pid)
    second = guard.run(_pid)
    assert first != os.getpid() and second != os.getpid()
    assert first != second


def test_one_user_rapid_edits_are_not_busy():
    """More than two overlapping calls for one project wait, and none come back busy."""
    from app.core import meshedit
    server, thread, port = _serve()
    base = f"http://127.0.0.1:{port}"
    bid = None
    stop = threading.Event()
    slow = []
    codes = []
    try:
        stl = _heavy_sphere().export(file_type="stl")
        with httpx.Client(base_url=base, timeout=120) as setup:
            opened = setup.post("/api/edit/new", files={"file": ("sphere.stl", stl, "model/stl")}, data={"title": "Sphere"})
            assert opened.status_code == 200, opened.text
            bid = opened.json()["id"]
            assert opened.json()["analysis"]["triangles"] >= 20_000
            cookies = dict(setup.cookies)
        watcher = threading.Thread(target=lambda: _probe(base, stop, slow, codes), daemon=True)
        watcher.start()
        barrier = threading.Barrier(6)
        outcomes = []

        def one(kind, n):
            barrier.wait(5)
            with httpx.Client(base_url=base, timeout=60, cookies=cookies) as client:
                if kind == "op":
                    response = client.post(f"/api/edit/{bid}/op", json={"op": "translate", "params": {"dx": 1, "dy": 0, "dz": 0}})
                elif kind == "scene":
                    response = client.get(f"/api/cad/{bid}/scene")
                else:
                    response = client.put(f"/api/edit/{bid}/parts/slots", json={
                        "action": "prepare", "slot_count": 4,
                        "colours": ["#FFFFFF", "#FF0000", "#00AA00", "#0000FF"],
                    })
                outcomes.append((kind, n, response.status_code))

        kinds = ("op", "op", "op", "scene", "scene", "slots")
        workers = [threading.Thread(target=one, args=(kind, i)) for i, kind in enumerate(kinds)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(60)
        assert all(not worker.is_alive() for worker in workers)
        assert len(outcomes) == 6
        busy = [row for row in outcomes if row[2] == 503]
        bad = [row for row in outcomes if row[2] >= 500]
        assert not busy and not bad, outcomes
        with httpx.Client(base_url=base, timeout=30, cookies=cookies) as client:
            rapid = []
            for _ in range(4):
                started = time.perf_counter()
                response = client.post(f"/api/edit/{bid}/op", json={"op": "translate", "params": {"dx": 1, "dy": 0, "dz": 0}})
                rapid.append((response.status_code, time.perf_counter() - started))
            print(f"RAPID_HTTP_TRANSLATE {rapid}")
            assert all(code == 200 for code, _elapsed in rapid), rapid
        stop.set()
        watcher.join(2)
        assert codes and set(codes) == {200}
        assert not slow, slow
        assert meshedit.HEAVY_MIN_FACES == 20_000
    finally:
        stop.set()
        _stop(server, thread)
        if bid:
            shutil.rmtree(store.dir(bid), ignore_errors=True)


def _probe(base, stop, slow, codes):
    with httpx.Client(base_url=base, timeout=1.0) as client:
        while not stop.is_set():
            started = time.perf_counter()
            try:
                response = client.get("/healthz")
            except httpx.TimeoutException:
                slow.append(1.0)
                codes.append(0)
                continue
            if time.perf_counter() - started >= 1.0:
                slow.append(time.perf_counter() - started)
            codes.append(response.status_code)
            time.sleep(0.05)
