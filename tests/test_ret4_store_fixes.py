import logging
import os

import pytest

from app.community import store


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    (tmp_path / "a.json").write_text("{}")
    return tmp_path


def test_snapshot_names_are_unique_with_microseconds(data):
    names = {store.backup_json_data().name for _ in range(20)}
    assert len(names) == 20
    assert all(len(n.split("-")) >= 5 for n in names)   # date-time-micro-suffix


def test_snapshot_never_reuses_existing_dir(data, monkeypatch):
    first = store._backup_dir()
    (first / "keep.json").write_text("old")

    class FixedUUID:
        hex = first.name.rsplit("-", 1)[1] + "0" * 24

    calls = {"n": 0}
    real = store.uuid.uuid4

    def fake():
        calls["n"] += 1
        return FixedUUID if calls["n"] == 1 else real()

    class FixedDT:
        @staticmethod
        def now():
            import datetime as d
            parts = first.name.split("-")
            return d.datetime.strptime("-".join(parts[2:5]), "%Y%m%d-%H%M%S-%f")

    monkeypatch.setattr(store.uuid, "uuid4", fake)
    monkeypatch.setattr(store, "datetime", FixedDT)
    second = store._backup_dir()
    assert second != first
    assert (first / "keep.json").read_text() == "old"


def test_freeze_logs_and_raises_on_oserror(data, monkeypatch, caplog):
    def boom(*a, **k):
        raise PermissionError("nope")
    monkeypatch.setattr(store.os, "chmod", boom)
    with caplog.at_level(logging.ERROR), pytest.raises(OSError):
        store.freeze_json_fallback()
    assert "could not make" in caplog.text
