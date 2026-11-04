from pathlib import Path

def test_lithophane_and_drain_warnings_wired():
    app = Path("static/app.js").read_text(); t = Path("static/torchc0.js").read_text()
    assert 'id="lithThkWarn"' in Path("static/index.html").read_text()
    assert "[0.5, 3.0] : [0.8, 3.2]" in app and "lithThkWarn" in app
    assert 'id="rzDrainWarn"' in t and "drainWarn" in t
