from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / "static" / "printer.js").read_text()


def test_first_slice_offers_printer_picker_without_blocking():
    i = JS.index("ONB4")
    block = JS[i:i + 1500]
    assert "if (!P.chosen)" in block
    assert 'pickerHTML("spFirst")' in block and "savePref(pref)" in block
    assert "Not now" in block
    # shown after the slice result, so the slice itself (and the FDM quick buttons) is unchanged
    assert JS.index('api("/api/slice"') < i
