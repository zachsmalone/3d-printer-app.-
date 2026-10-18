import os
import stat

from app.community.store import backup_json_data, freeze_json_fallback


def test_backup_json_data_creates_timestamped_copy(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "users.json").write_text('{"a": 1}')
    monkeypatch.setattr("app.community.store.DATA", data)
    backup = backup_json_data()
    assert backup.exists()
    assert (backup / "users.json").read_text() == '{"a": 1}'


def test_json_fallback_is_read_only_after_freeze(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    p = data / "users.json"
    p.write_text('{"a": 1}')
    monkeypatch.setattr("app.community.store.DATA", data)
    changed = freeze_json_fallback()
    assert p in changed
    mode = stat.S_IMODE(p.stat().st_mode)
    assert mode & 0o222 == 0


def test_storage_mode_is_json_by_default(monkeypatch):
    monkeypatch.delenv("ZEIM_STORAGE", raising=False)
    monkeypatch.delenv("PHOTO3D_STORAGE", raising=False)
    import importlib
    import app.config as config
    importlib.reload(config)
    assert config.STORAGE_MODE == "json"


def test_storage_mode_accepts_db(monkeypatch):
    monkeypatch.setenv("ZEIM_STORAGE", "db")
    monkeypatch.delenv("PHOTO3D_STORAGE", raising=False)
    import importlib
    import app.config as config
    importlib.reload(config)
    assert config.STORAGE_MODE == "db"
    # restore the module for the rest of the session: without this reload the leaked
    # "db" mode silently changes storage behaviour for every later test file
    monkeypatch.delenv("ZEIM_STORAGE", raising=False)
    importlib.reload(config)
    assert config.STORAGE_MODE == "json"
