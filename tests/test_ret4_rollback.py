"""RET4: rollback.sh swaps a backup copy in, keeps the live .env (0600), and undoes itself when unhealthy."""
import os
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "reports" / "deploy" / "rollback.sh"


def _tree(d: Path, sha: str, env: str | None = None):
    (d / "reports/deploy").mkdir(parents=True)
    (d / "reports/deploy/docker-compose.yml").write_text("services: {}\n")
    (d / "Dockerfile").write_text("FROM scratch\n")
    (d / ".deploy-sha").write_text(sha + "\n")
    if env is not None:
        (d / ".env").write_text(env)


def _run(tmp: Path, code: str, *args):
    bin_ = tmp / "bin"; bin_.mkdir(exist_ok=True)
    (bin_ / "docker").write_text('#!/bin/sh\necho "docker $* in $(pwd)" >> "$LOG"\n')
    (bin_ / "curl").write_text(f"#!/bin/sh\nprintf {code}\n")
    (bin_ / "sleep").write_text("#!/bin/sh\n")
    for f in bin_.iterdir():
        f.chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_}:{os.environ['PATH']}", DEPLOY_DIR=str(tmp / "zeim"),
               HEALTH_TRIES="2", LOG=str(tmp / "log"))
    return subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True)


def test_list_and_good_rollback(tmp_path):
    _tree(tmp_path / "zeim", "bbbbbbb1", "SECRET=new\nZEIM_PLANS_ENABLED=0\n")
    _tree(tmp_path / "zeim.prev-aaaaaaa-120000", "aaaaaaa1", "SECRET=old\n")
    r = _run(tmp_path, 200, "--list")
    assert "zeim.prev-aaaaaaa-120000\taaaaaaa1" in r.stdout
    r = _run(tmp_path, 200, str(tmp_path / "zeim.prev-aaaaaaa-120000"))
    assert r.returncode == 0, r.stderr + r.stdout
    live = tmp_path / "zeim"
    assert (live / ".deploy-sha").read_text().startswith("aaaaaaa")
    assert (live / ".env").read_text() == "SECRET=new\nZEIM_PLANS_ENABLED=0\n"
    assert stat.S_IMODE((live / ".env").stat().st_mode) == 0o600
    assert (tmp_path / "zeim.prev-aaaaaaa-120000").is_dir()          # backup kept for another try
    assert list(tmp_path.glob("zeim.rolledback-bbbbbbb-*"))
    assert "up -d --build" in (tmp_path / "log").read_text()


def test_unhealthy_rollback_restores_original(tmp_path):
    _tree(tmp_path / "zeim", "bbbbbbb1", "SECRET=new\n")
    _tree(tmp_path / "zeim.prev-aaaaaaa-120000", "aaaaaaa1")
    r = _run(tmp_path, 502, str(tmp_path / "zeim.prev-aaaaaaa-120000"))
    assert r.returncode != 0
    assert (tmp_path / "zeim/.deploy-sha").read_text().startswith("bbbbbbb")


def test_refuses_non_deploy_dir_and_missing_env(tmp_path):
    _tree(tmp_path / "zeim", "bbbbbbb1")                              # no .env
    _tree(tmp_path / "zeim.prev-x", "aaaaaaa1")
    (tmp_path / "junk").mkdir()
    assert _run(tmp_path, 200, str(tmp_path / "junk")).returncode != 0
    assert _run(tmp_path, 200, str(tmp_path / "zeim.prev-x")).returncode != 0
    assert (tmp_path / "zeim/.deploy-sha").read_text().startswith("bbbbbbb")
