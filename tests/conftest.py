"""Shared test setup: temp data dirs + local mode by default (individual tests switch to shared mode explicitly)."""
import os, tempfile
_tmp = tempfile.mkdtemp(prefix="zeim-tests-")
os.environ.setdefault("PHOTO3D_OUT", _tmp + "/out")
os.environ.setdefault("PHOTO3D_DATA", _tmp + "/data")
os.environ.setdefault("PHOTO3D_ADMIN_TOKEN", "t0k")
os.environ.setdefault("PHOTO3D_MODE", "local")

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.core import ratelimit
    ratelimit.reset()
    yield
    ratelimit.reset()


@pytest.fixture(autouse=True)
def _test_client_counts_as_this_computer(monkeypatch):
    """In local mode only loopback requests are the owner; the TestClient presents itself as host 'testserver' / peer 'testclient'."""
    from app import config
    monkeypatch.setattr(config, "LOCAL_CLIENTS", tuple(config.LOCAL_CLIENTS) + ("testclient",))
    monkeypatch.setattr(config, "LOCAL_HOSTS", tuple(config.LOCAL_HOSTS) + ("testserver",))
    monkeypatch.setattr(config, "AGE_IP_LOCK_MINUTES", 0)       # the per-address age lock is tested explicitly; the many tests that share the address "testclient" must not trip it
    yield
