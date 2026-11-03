"""ONB1: first-party time-to-first-print count. Stores only day, event and a coarse bucket."""
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DATA", tmp_path)
    from app.main import app
    return TestClient(app)


def test_records_bucket_only(client, tmp_path):
    r = client.post("/api/metrics", json={"event": "first_print", "secs": 420, "extra": "x"})
    assert r.status_code == 200
    lines = [json.loads(l) for f in (tmp_path / "metrics").glob("*.jsonl") for l in f.read_text().splitlines()]
    assert len(lines) == 1 and set(lines[0]) == {"d", "e", "b"} and lines[0]["b"] == "5-15m"
    from app.api import metrics
    assert metrics.summary() == {"first_print": {"5-15m": 1}, "total": 1}


def test_rejects_other_events_and_bad_numbers(client):
    assert client.post("/api/metrics", json={"event": "page_view", "secs": 1}).status_code == 400
    assert client.post("/api/metrics", json={"event": "first_print", "secs": "x"}).status_code == 400
    assert client.post("/api/metrics", json={"event": "first_print", "secs": -1}).status_code == 400


def test_buckets():
    from app.api.metrics import bucket
    assert [bucket(s) for s in (5, 100, 600, 1800, 7200, 200000, 10 ** 7)] == ["<1m", "1-5m", "5-15m", "15-60m", "1-24h", "1-7d", ">7d"]


def test_nps_score_only(client, tmp_path):
    for s in (10, 9, 3):
        assert client.post("/api/metrics", json={"event": "nps", "score": s, "who": "me"}).status_code == 200
    for bad in (11, -1, "7", 7.5, True):
        assert client.post("/api/metrics", json={"event": "nps", "score": bad}).status_code == 400
    lines = [json.loads(l) for f in (tmp_path / "metrics").glob("*.jsonl") for l in f.read_text().splitlines()]
    assert all(set(l) == {"d", "e", "s"} for l in lines)
    from app.api import metrics
    assert metrics.summary()["nps"] == {"answers": 3, "score": 33}
