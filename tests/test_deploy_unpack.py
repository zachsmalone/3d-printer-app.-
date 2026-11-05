"""Release unpack replaces static/ so a file deleted from the release does not linger."""
import io
import os
import stat
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "reports" / "deploy" / "unpack.sh"


def _tar(path: Path, root: Path):
    with tarfile.open(path, "w") as tar:
        for dirpath, _dirs, filenames in os.walk(root):
            for name in filenames:
                f = Path(dirpath) / name
                tar.add(f, arcname=str(f.relative_to(root)))


def test_replaces_static_and_keeps_env(tmp_path):
    src = tmp_path / "src"
    (src / "static").mkdir(parents=True)
    (src / "static" / "app.js").write_text("new")
    (src / "app").mkdir()
    (src / "app" / "main.py").write_text("code")
    (src / ".env").write_text("FROM_ARCHIVE=1\n")
    archive = tmp_path / "rel.tar"
    _tar(archive, src)
    dest = tmp_path / "opt" / "zeim"
    (dest / "static").mkdir(parents=True)
    (dest / "static" / "agegate.js").write_text("old gate")
    (dest / "static" / "app.js").write_text("old")
    (dest / ".env").write_text("SECRET=1\n")
    (dest / "notes.txt").write_text("keep")
    r = subprocess.run(["bash", str(SCRIPT), str(archive), str(dest)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout
    assert not (dest / "static" / "agegate.js").exists()
    assert (dest / "static" / "app.js").read_text() == "new"
    assert (dest / "app" / "main.py").read_text() == "code"
    assert (dest / ".env").read_text() == "SECRET=1\n"
    assert (dest / "notes.txt").read_text() == "keep"
    assert not (dest / "static.new").exists()


def test_wrapped_archive_and_missing_static_leaves_the_live_tree(tmp_path):
    wrapped = tmp_path / "wrap" / "zeim" / "static"
    wrapped.mkdir(parents=True)
    (wrapped / "app.js").write_text("wrapped")
    archive = tmp_path / "wrap.tar"
    with tarfile.open(archive, "w") as tar:
        tar.add(tmp_path / "wrap" / "zeim", arcname="zeim")
    dest = tmp_path / "live"
    (dest / "static").mkdir(parents=True)
    (dest / "static" / "agegate.js").write_text("gone")
    r = subprocess.run(["bash", str(SCRIPT), str(archive), str(dest)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (dest / "static" / "app.js").read_text() == "wrapped"
    assert not (dest / "static" / "agegate.js").exists()

    bare = tmp_path / "bare.tar"
    with tarfile.open(bare, "w") as tar:
        info = tarfile.TarInfo("README")
        data = b"hi\n"
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    (dest / "static" / "keep.js").write_text("stay")
    r = subprocess.run(["bash", str(SCRIPT), str(bare), str(dest)], capture_output=True, text=True)
    assert r.returncode != 0
    assert (dest / "static" / "keep.js").read_text() == "stay"


def test_refuses_a_path_that_escapes_the_archive(tmp_path):
    archive = tmp_path / "bad.tar"
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo("../static/agegate.js")
        data = b"nope"
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    dest = tmp_path / "live"
    dest.mkdir()
    (dest / "static").mkdir()
    (dest / "static" / "ok.js").write_text("ok")
    r = subprocess.run(["bash", str(SCRIPT), str(archive), str(dest)], capture_output=True, text=True)
    assert r.returncode != 0
    assert "unsafe" in r.stderr
    assert (dest / "static" / "ok.js").read_text() == "ok"
    assert stat.S_ISDIR(os.stat(dest / "static").st_mode)
