from app.services import slicer_warm as w
from app.services import slice_engine as se

def test_off_switch_and_test_suite_default(monkeypatch):
    monkeypatch.delenv("ZEIM_SLICER_WARM", raising=False)
    assert w.enabled() is False                      # never slices in the background under pytest
    monkeypatch.setenv("ZEIM_SLICER_WARM", "0"); assert w.enabled() is False and w.start_background() is None
    monkeypatch.setenv("ZEIM_SLICER_WARM", "1"); assert w.enabled() is True

def test_warm_once_never_raises(monkeypatch):
    monkeypatch.setattr(se, "find_engine", lambda: None)
    assert w.warm_once() is None
    monkeypatch.setattr(se, "find_engine", lambda: "/bin/false")
    def boom(*a, **k): raise RuntimeError("x")
    monkeypatch.setattr(se, "slice_model_path", boom)
    assert w.warm_once() is None

def test_idle_minutes(monkeypatch):
    monkeypatch.setenv("ZEIM_SLICER_WARM_MIN", "bad"); assert w.idle_minutes() == 20.0
    monkeypatch.setenv("ZEIM_SLICER_WARM_MIN", "0"); assert w.idle_minutes() == 1.0
