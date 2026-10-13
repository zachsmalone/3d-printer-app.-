"""Ops basics: network binding default, /healthz, pinned requirements and deployment files."""
import os, shutil, socket, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from app import config
from tests.b1 import *

ROOT = config.ROOT


def _env(**kw):
    e = {k: v for k, v in os.environ.items() if k not in ("HOST", "PORT", "PHOTO3D_MODE")}
    e.update(kw); return e


def test_default_bind_is_localhost_only():
    out = subprocess.run([sys.executable, "-c", "from app import config; print(config.HOST)"], env=_env(), cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "127.0.0.1"
    sh = (ROOT / "run.sh").read_text()
    assert 'HOST=${HOST:-127.0.0.1}' in sh and '0.0.0.0' not in sh.replace("HOST=0.0.0.0 opens", "")
    assert '"${HOST:-0.0.0.0}"' not in sh


def test_non_loopback_host_logs_a_no_auth_warning():
    """Without strong auth secrets, a public bind must warn; localhost gets passkey login on with defaults."""
    out = subprocess.run([sys.executable, "-c", "import app.main"], env=_env(HOST="0.0.0.0"), cwd=ROOT, capture_output=True, text=True)
    text = (out.stderr + out.stdout).lower()
    assert "passkey/email login is off" in text or "no real authentication" in text
    quiet = subprocess.run([sys.executable, "-c", "import app.main"], env=_env(), cwd=ROOT, capture_output=True, text=True)
    q = (quiet.stderr + quiet.stdout).lower()
    assert "passkey/email login is off" not in q and "no real authentication" not in q


@pytest.mark.skipif(not shutil.which("ss"), reason="needs `ss`")
def test_server_listens_on_loopback_by_default():
    port = 18765 + os.getpid() % 200
    d = os.path.join(os.environ["PHOTO3D_DATA"], "serve-test")
    p = subprocess.Popen([sys.executable, "-m", "app.serve"], cwd=ROOT, env=_env(PORT=str(port), PHOTO3D_DATA=d + "/d", PHOTO3D_OUT=d + "/o"),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); break
            except OSError:
                time.sleep(0.25)
        ls = subprocess.run(["ss", "-ltnH", f"sport = :{port}"], capture_output=True, text=True).stdout
        assert f"127.0.0.1:{port}" in ls and f"0.0.0.0:{port}" not in ls and f"*:{port}" not in ls, ls
    finally:
        p.terminate(); p.wait(10)


def test_healthz_no_auth_no_data_no_cookie():
    c = TestClient(app); r = c.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"} and "set-cookie" not in r.headers


def test_pinned_requirements_and_ops_files():
    reqs = [l.split("#")[0].strip() for l in (ROOT / "requirements.txt").read_text().splitlines() if l.split("#")[0].strip()]
    assert reqs and all("==" in l for l in reqs)
    assert "pytest==" in (ROOT / "requirements-dev.txt").read_text()
    for f in ("Dockerfile", ".dockerignore", ".env.example", ".gitignore", ".github/workflows/ci.yml", "constraints.txt"):
        assert (ROOT / f).exists(), f
    gi = (ROOT / ".gitignore").read_text()
    for pat in ("data/", "outputs/", ".venv/", "server.log"):
        assert pat in gi
    dk = (ROOT / "Dockerfile").read_text()
    assert "healthz" in dk and "app.serve" in dk and "HOST=0.0.0.0" in dk
    assert "pytest" in (ROOT / ".github/workflows/ci.yml").read_text()
