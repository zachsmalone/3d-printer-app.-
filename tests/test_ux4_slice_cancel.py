from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / "static" / "printer.js").read_text()


def test_slice_has_elapsed_and_cancel():
    assert "signal: ctl.signal" in JS
    assert "editBusyCancel" in JS
    assert "Stopped waiting for this slice" in JS
    assert "clearInterval(tick)" in JS
