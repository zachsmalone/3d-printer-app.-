"""Live bug 11/3: the print-photo form must show real Choose/Take photo buttons above the consent box, accept HEIC/JPEG/PNG, and preview picks."""
from pathlib import Path
JS = (Path(__file__).resolve().parents[1] / "static/community.js").read_text()


def test_buttons_above_ack_and_bound():
    form = JS[JS.index('<details class="prform">'):JS.index('id="prSend"')]
    assert form.index('label class="btn" for="prFile"') < form.index('id="prAck"')
    assert 'label class="btn" for="prCam"' in form and 'capture="environment"' in form
    for t in ("image/heic", ".heic", ".jpg", ".png"):
        assert t in form
    assert 'id="prThumbs"' in form


def test_no_datatransfer_dependency_and_nsfw_kept():
    assert "new DataTransfer()" not in JS.split('id="prSend"')[1].split("prSend\").onclick")[0]
    assert "prPicked" in JS and "URL.createObjectURL" in JS
    assert 'name="prNsfw" value="no"' in JS and 'name="prNsfw" value="yes"' in JS
