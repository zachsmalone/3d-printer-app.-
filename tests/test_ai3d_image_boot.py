"""The main ZEIM image must boot with 2D→3D off.

app/core/ai3d_prep.py loads workers/ai3d/prep.py at import, before the feature flag is checked.
The image only COPY's app, static, data, and that one prep file. The rest of the TripoSR worker
stays out. A checkout where workers/ exists will not catch a missing COPY.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY_LINE = "COPY workers/ai3d/prep.py ./workers/ai3d/prep.py"


def test_dockerfile_copies_the_prep_file_the_loader_opens():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    loader = (ROOT / "app" / "core" / "ai3d_prep.py").read_text(encoding="utf-8")
    assert COPY_LINE in dockerfile
    assert 'parents[2] / "workers" / "ai3d" / "prep.py"' in loader
    ignored = [
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert "workers" not in ignored
    assert "workers/**" not in ignored
    assert (ROOT / "workers" / "ai3d" / "prep.py").is_file()


def test_import_succeeds_in_an_image_layout_with_2d3d_off(tmp_path):
    """Same files the Dockerfile puts in /app, and no other workers/ files."""
    for name in ("app", "static", "data"):
        shutil.copytree(
            ROOT / name,
            tmp_path / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            symlinks=False,
        )
    dest = tmp_path / "workers" / "ai3d"
    dest.mkdir(parents=True)
    shutil.copy2(ROOT / "workers" / "ai3d" / "prep.py", dest / "prep.py")
    assert not (dest / "server.py").exists()
    assert not (dest / "Dockerfile").exists()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    env["ZEIM_2D3D_ENABLED"] = "0"
    env["PHOTO3D_MODE"] = "local"
    env["PHOTO3D_DATA"] = str(tmp_path / "rt-data")
    env["PHOTO3D_OUT"] = str(tmp_path / "rt-out")
    (tmp_path / "rt-data").mkdir()
    (tmp_path / "rt-out").mkdir()
    ran = subprocess.run(
        [sys.executable, "-c", "from app.main import app; assert app is not None"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert ran.returncode == 0, ran.stdout + "\n" + ran.stderr


def test_import_fails_when_the_prep_file_is_missing(tmp_path):
    """The failure that took zeim-prod down: app copied, workers/ai3d/prep.py not."""
    shutil.copytree(
        ROOT / "app",
        tmp_path / "app",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        symlinks=False,
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    env["ZEIM_2D3D_ENABLED"] = "0"
    env["PHOTO3D_MODE"] = "local"
    env["PHOTO3D_DATA"] = str(tmp_path / "rt-data")
    env["PHOTO3D_OUT"] = str(tmp_path / "rt-out")
    (tmp_path / "rt-data").mkdir()
    (tmp_path / "rt-out").mkdir()
    ran = subprocess.run(
        [sys.executable, "-c", "from app.main import app"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert ran.returncode != 0
    assert "workers/ai3d/prep.py" in ran.stderr
    assert "FileNotFoundError" in ran.stderr or "No such file" in ran.stderr
