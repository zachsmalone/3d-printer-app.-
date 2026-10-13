"""Image-moderation hook for 'I printed this' photos: pluggable, default needs human review, never auto-approves."""
import io

import pytest
from PIL import Image

from app.community import imagemod, social
from app.community.store import PRINTS


def _png(color=(200, 100, 50)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _reset_hook():
    imagemod.set_review_hook(None)
    yield
    imagemod.set_review_hook(None)


def test_default_hook_needs_human_review():
    assert imagemod.default_review(_png(), {}) == imagemod.NEEDS_HUMAN_REVIEW
    assert imagemod.review_upload(_png(), {"item_id": "x"}) == imagemod.NEEDS_HUMAN_REVIEW


def test_add_print_records_pending_and_never_auto_approves(tmp_path, monkeypatch):
    monkeypatch.setattr(social, "PDIR", tmp_path)
    # Even a rogue hook that returns APPROVE must not skip human review.
    imagemod.set_review_hook(lambda data, meta: imagemod.APPROVE)
    rec = social.add_print("item1", "sid" * 8, "uid1", "maker", _png(), "png", "", False)
    assert rec["status"] == "pending"
    assert rec["moderation"] == imagemod.NEEDS_HUMAN_REVIEW
    assert (tmp_path / f"{rec['id']}.png").is_file()


def test_reject_hook_refuses_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(social, "PDIR", tmp_path)
    before = {p["id"] for p in PRINTS.read()}
    imagemod.set_review_hook(lambda data, meta: imagemod.REJECT)
    with pytest.raises(ValueError, match="refused"):
        social.add_print("item-reject", "sid" * 8, "uid1", "maker", _png(), "png", "", False)
    assert {p["id"] for p in PRINTS.read()} == before
    assert list(tmp_path.iterdir()) == []          # no file written on reject


def test_custom_hook_receives_meta(tmp_path, monkeypatch):
    monkeypatch.setattr(social, "PDIR", tmp_path)
    seen = {}

    def hook(data, meta):
        seen.update(meta)
        seen["nbytes"] = len(data)
        return imagemod.NEEDS_HUMAN_REVIEW

    imagemod.set_review_hook(hook)
    social.add_print("item99", "sid" * 8, "uid9", "maker", _png(), "png", "hi", True)
    assert seen["item_id"] == "item99" and seen["uid"] == "uid9" and seen["nbytes"] > 0


def test_unknown_hook_result_falls_back_to_needs_review():
    imagemod.set_review_hook(lambda data, meta: "weird")
    assert imagemod.review_upload(_png()) == imagemod.NEEDS_HUMAN_REVIEW
