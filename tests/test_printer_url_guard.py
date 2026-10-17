import pytest

from app import config
from app.services import printers


@pytest.mark.parametrize("url", ["http://169.254.169.254/latest", "******10.0.0.5", "ftp://10.0.0.5", "http://0.0.0.0:80"])
def test_always_blocked(url):
    with pytest.raises(ValueError):
        printers.check_url(url)


def test_lan_allowed_by_default_and_blocked_when_hosted(monkeypatch):
    printers.check_url("http://192.168.1.20:7125")
    monkeypatch.setattr(config, "BLOCK_PRIVATE_PRINTERS", True)
    for u in ("http://192.168.1.20", "http://127.0.0.1:7125"):
        with pytest.raises(ValueError):
            printers.check_url(u)


def test_send_and_test_refuse_metadata():
    p = {"type": "octoprint", "url": "http://169.254.169.254", "name": "x"}
    assert printers.test(p)["ok"] is False
    assert printers.send(p, None, "a.gcode", False)["ok"] is False
