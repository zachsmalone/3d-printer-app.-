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
