"""Local photo check: approve, reject, hold on error, and report thresholds. The detector is mocked except one opt-in load."""
import io
import os

import pytest
from PIL import Image

from app.community import imagemod, moderation, social
from app.community.store import ACTIVITY, MODERATION, PRINTS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _png(size=32, color=(200, 100, 50)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (size, size) if isinstance(size, int) else size, color).save(buf, "PNG")
    return buf.getvalue()


def _hits(label, score):
    return [{"class": label, "score": score, "box": [0, 0, 10, 10]}]


@pytest.fixture(autouse=True)
def _use_the_model_path_unless_a_test_sets_a_hook():
    """conftest holds every photo. This module turns that off, and each test sets what it needs."""
    imagemod.set_review_hook(None)
    yield
    imagemod.set_review_hook(None)


def test_default_hook_needs_human_review_and_a_broken_checker_never_approves():
    assert imagemod.default_review(_png(), {}) == imagemod.NEEDS_HUMAN_REVIEW
    imagemod.set_review_hook(imagemod.default_review)
    assert imagemod.review_upload(_png(), {"item_id": "x"}) == imagemod.NEEDS_HUMAN_REVIEW

    def boom(data, meta):
        raise RuntimeError("onnx failed")

    imagemod.set_review_hook(boom)
    meta = {}
    assert imagemod.review_upload(_png(), meta) == imagemod.NEEDS_HUMAN_REVIEW
    assert "could not run" in meta["check_note"]


def test_unknown_hook_result_falls_back_to_needs_review():
    imagemod.set_review_hook(lambda data, meta: "weird")
    assert imagemod.review_upload(_png()) == imagemod.NEEDS_HUMAN_REVIEW


def test_clean_detection_approves_and_counts_for_trending(tmp_path, monkeypatch):
    monkeypatch.setattr(social, "PDIR", tmp_path)
    monkeypatch.setattr(imagemod, "_detect", lambda data: [])
    rec = social.add_print("item1", "sid" * 8, "uid1", "maker", _png(), "png", "", False, nsfw=False)
    assert rec["status"] == "approved" and rec["nsfw"] is False
    assert rec["moderation"] == imagemod.APPROVE
    assert (tmp_path / f"{rec['id']}.png").is_file()
    assert any(e["k"] == "printed" and e["i"] == "item1" for e in ACTIVITY.read())


def test_uploader_nsfw_tag_is_kept_when_the_photo_is_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(social, "PDIR", tmp_path)
    monkeypatch.setattr(imagemod, "_detect", lambda data: [])
    rec = social.add_print("item-tag", "sid" * 8, "uid1", "maker", _png(), "png", "", False, nsfw=True)
    assert rec["status"] == "approved" and rec["nsfw"] is True


def test_mild_detection_approves_and_forces_the_nsfw_tag(tmp_path, monkeypatch):
    monkeypatch.setattr(social, "PDIR", tmp_path)
    monkeypatch.setattr(imagemod, "_detect", lambda data: _hits("FEMALE_BREAST_EXPOSED", 0.8))
    rec = social.add_print("item-mild", "sid" * 8, "uid1", "maker", _png(), "png", "", False, nsfw=False)
    assert rec["status"] == "approved" and rec["nsfw"] is True
    assert rec["check_note"] == "Marked as mature content."
    # a weak hit stays a normal photo
    monkeypatch.setattr(imagemod, "_detect", lambda data: _hits("BUTTOCKS_EXPOSED", 0.4))
    quiet = social.add_print("item-quiet", "sid" * 8, "uid1", "maker", _png(), "png", "", False, nsfw=False)
    assert quiet["status"] == "approved" and quiet["nsfw"] is False


def test_explicit_detection_rejects_even_when_the_uploader_tagged_nsfw(tmp_path, monkeypatch):
    monkeypatch.setattr(social, "PDIR", tmp_path)
    before = {p["id"] for p in PRINTS.read()}
    monkeypatch.setattr(imagemod, "_detect", lambda data: _hits("MALE_GENITALIA_EXPOSED", 0.9))
    with pytest.raises(ValueError, match="guidelines"):
        social.add_print("item-reject", "sid" * 8, "uid1", "maker", _png(), "png", "", False, nsfw=True)
    assert {p["id"] for p in PRINTS.read()} == before
    assert list(tmp_path.iterdir()) == []
    monkeypatch.setattr(imagemod, "_detect", lambda data: _hits("ANUS_EXPOSED", 0.5))
    with pytest.raises(ValueError, match="guidelines"):
        social.add_print("item-reject-2", "sid" * 8, "uid1", "maker", _png(), "png", "", False, nsfw=False)


def test_checker_error_holds_the_photo_and_does_not_approve(tmp_path, monkeypatch):
    monkeypatch.setattr(social, "PDIR", tmp_path)

    def boom(data):
        raise RuntimeError("model missing")

    monkeypatch.setattr(imagemod, "_detect", boom)
    rec = social.add_print("item-err", "sid" * 8, "uid1", "maker", _png(), "png", "", False, nsfw=False)
    assert rec["status"] == "pending"
    assert rec["moderation"] == imagemod.NEEDS_HUMAN_REVIEW
    assert "could not run" in rec["check_note"]
    assert (tmp_path / f"{rec['id']}.png").is_file()
    assert not any(e["k"] == "printed" and e["i"] == "item-err" for e in ACTIVITY.read())


def test_reject_hook_refuses_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(social, "PDIR", tmp_path)
    before = {p["id"] for p in PRINTS.read()}
    imagemod.set_review_hook(lambda data, meta: imagemod.REJECT)
    with pytest.raises(ValueError, match="guidelines"):
        social.add_print("item-hook", "sid" * 8, "uid1", "maker", _png(), "png", "", False)
    assert {p["id"] for p in PRINTS.read()} == before
    assert list(tmp_path.iterdir()) == []


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


def test_deep_check_uses_stricter_scores_and_several_crops(monkeypatch):
    calls = {"n": 0}

    def det(data):
        calls["n"] += 1
        return _hits("FEMALE_GENITALIA_EXPOSED", 0.40)

    monkeypatch.setattr(imagemod, "_detect", det)
    assert imagemod.review_upload(_png(200), {}) == imagemod.APPROVE          # 0.40 is under the normal cutoff
    calls["n"] = 0
    deep = {"deep": True}
    assert imagemod.review_upload(_png(200), deep) == imagemod.REJECT
    assert calls["n"] >= 5                                                    # full frame plus crops
    calls["n"] = 0
    monkeypatch.setattr(imagemod, "_detect", lambda data: _hits("BUTTOCKS_EXPOSED", 0.36))
    meta = {"deep": True}
    assert imagemod.review_upload(_png(200), meta) == imagemod.APPROVE
    assert meta.get("force_nsfw") is True


_photo_n = {"n": 0}


def _photo(tmp_path, monkeypatch):
    monkeypatch.setattr(social, "PDIR", tmp_path)
    monkeypatch.setattr(imagemod, "_detect", lambda data: [])
    _photo_n["n"] += 1
    return social.add_print(f"item-{_photo_n['n']}", "sid" * 8, "uid1", "maker", _png(80), "png", "", False, nsfw=False)


def _reporters(n, pid, reason="other"):
    out = None
    for i in range(n):
        out = moderation.report(social.mod_key(pid), f"person-{i}", reason, "")
    return out


def test_one_report_per_person_and_nine_people_do_not_remove(tmp_path, monkeypatch):
    rec = _photo(tmp_path, monkeypatch)
    key = social.mod_key(rec["id"])
    first = moderation.report(key, "person-a", "other", "")
    again = moderation.report(key, "person-a", "copyright", "second reason")
    assert again["duplicate"] is True and again["id"] == first["id"]
    assert moderation._distinct_reporters(key) == 1
    _reporters(8, rec["id"])
    assert moderation._distinct_reporters(key) == 9
    assert key not in MODERATION.read()["hidden"]
    assert social.get_print(rec["id"])["status"] == "approved"


def test_ten_reporters_run_one_deep_check_and_remove_only_if_it_flags(tmp_path, monkeypatch):
    rec = _photo(tmp_path, monkeypatch)
    key = social.mod_key(rec["id"])
    calls = {"n": 0}

    def hook(data, meta):
        if meta.get("deep"):
            calls["n"] += 1
            meta["force_nsfw"] = True
            return imagemod.APPROVE
        return imagemod.APPROVE

    imagemod.set_review_hook(hook)
    last = _reporters(moderation.IMAGE_DEEP_REPORTS, rec["id"])
    assert calls["n"] == 1
    assert last["auto_removed"] is True and key in MODERATION.read()["hidden"]
    assert social.get_print(rec["id"]).get("deep_checked") == "flagged"
    assert (tmp_path / f"{rec['id']}.png").is_file()          # hidden, not deleted; a moderator can still open it
    moderation.report(key, "person-later", "other", "")
    assert calls["n"] == 1                                     # a new person does not run it again


def test_ten_reporters_leave_a_clean_photo_up_and_an_error_does_not_remove_it(tmp_path, monkeypatch):
    clean = _photo(tmp_path, monkeypatch)
    calls = {"n": 0}

    def hook(data, meta):
        if meta.get("deep"):
            calls["n"] += 1
        return imagemod.APPROVE

    imagemod.set_review_hook(hook)
    last = _reporters(moderation.IMAGE_DEEP_REPORTS, clean["id"])
    assert calls["n"] == 1 and not last.get("auto_removed")
    assert social.mod_key(clean["id"]) not in MODERATION.read()["hidden"]
    assert social.get_print(clean["id"]).get("deep_checked") == "clean"
    moderation.report(social.mod_key(clean["id"]), "person-later", "other", "")
    assert calls["n"] == 1                                          # already checked clean: not run again

    broken = _photo(tmp_path, monkeypatch)

    def hook(data, meta):
        if meta.get("deep"):
            raise RuntimeError("detector down")
        return imagemod.APPROVE

    imagemod.set_review_hook(hook)
    last = _reporters(moderation.IMAGE_DEEP_REPORTS, broken["id"])
    assert not last.get("auto_removed")
    assert social.mod_key(broken["id"]) not in MODERATION.read()["hidden"]
    assert "deep_checked" not in social.get_print(broken["id"])
    again = moderation.report(social.mod_key(broken["id"]), "person-extra", "other", "")
    assert not again.get("auto_removed")                       # a later report retries, and still does not remove on error


def test_one_hundred_distinct_reporters_remove_the_photo(tmp_path, monkeypatch):
    rec = _photo(tmp_path, monkeypatch)
    imagemod.set_review_hook(lambda data, meta: imagemod.APPROVE)   # deep check says clean; the count still removes
    last = _reporters(moderation.IMAGE_REMOVE_REPORTS, rec["id"])
    key = social.mod_key(rec["id"])
    assert last["auto_removed"] is True and last["auto_hidden"] is True
    assert key in MODERATION.read()["hidden"]
    assert social.prints_for(rec["item_id"], "someone-else") == []


def test_minor_safety_still_hides_immediately(tmp_path, monkeypatch):
    rec = _photo(tmp_path, monkeypatch)
    out = moderation.report(social.mod_key(rec["id"]), "person-safe", "minor_safety", "")
    assert out["auto_hidden"] is True
    assert social.mod_key(rec["id"]) in MODERATION.read()["hidden"]
    assert not out.get("auto_removed")


def test_held_photo_is_listed_for_optional_review(tmp_path, monkeypatch):
    monkeypatch.setattr(social, "PDIR", tmp_path)

    def boom(data):
        raise RuntimeError("load failed")

    monkeypatch.setattr(imagemod, "_detect", boom)
    rec = social.add_print("item-q", "sid" * 8, "uid1", "maker", _png(), "png", "cap", False)
    from app.api.community import _pending_prints
    row = next(p for p in _pending_prints() if p["id"] == rec["id"])
    assert row["check_note"] and "could not run" in row["check_note"]
    assert "optional review" in open(os.path.join(ROOT, "static", "moderation.html"), encoding="utf-8").read()
    assert "held for optional review" in open(os.path.join(ROOT, "static", "moderation.js"), encoding="utf-8").read()


def test_report_button_and_honest_policy_text():
    js = open(os.path.join(ROOT, "static", "community.js"), encoding="utf-8").read()
    assert 'aria-label="Report this photo"' in js and "openReport(" in js and "Waiting for review" in js
    for name in ("static/COMMUNITY_GUIDELINES.html", "static/COMMUNITY_GUIDELINES.md", "static/privacy.html", "static/terms.html"):
        text = open(os.path.join(ROOT, name), encoding="utf-8").read().lower()
        assert "automatically" in text and "server" in text, name
        assert "99%" not in text and "100% accurate" not in text, name


def test_print_photo_report_is_rate_limited_and_one_per_person():
    from tests.b1 import ADMIN, client, photo_build

    owner = client({"display_name": "Photo Owner", "dob": "1990-01-01"})
    item = owner.post("/api/showcase", json={"build_id": photo_build(owner), "title": "Lamp", "accept_guidelines": True,
                                              "nsfw": False, "visibility": "public"}).json()
    imagemod.set_review_hook(lambda data, meta: imagemod.APPROVE)
    photo = owner.post(f"/api/showcase/{item['id']}/prints", files={"photo": ("p.png", _png(), "image/png")},
                       data={"nsfw": "no", "photo_ack": "true"})
    assert photo.status_code == 200, photo.text
    body = photo.json()
    assert body["pending"] is False and body["status"] == "approved"
    other = client({"display_name": "Reporter", "dob": "1991-02-02"})
    first = other.post(f"/api/prints/{body['id']}/report", json={"reason": "other", "details": ""})
    assert first.status_code == 200, first.text
    second = other.post(f"/api/prints/{body['id']}/report", json={"reason": "copyright", "details": ""})
    assert second.status_code == 200 and second.json()["duplicate"] is True and second.json()["id"] == first.json()["id"]
    # the limiter counts every post, including a duplicate
    codes = [other.post(f"/api/prints/{body['id']}/report", json={"reason": "other"}).status_code for _ in range(9)]
    assert codes[-1] == 429
    held = client().get("/api/moderation/queue", headers=ADMIN).json()["pending_prints"]
    assert body["id"] not in [p["id"] for p in held]


def test_bundled_model_approves_a_plain_photo_on_cpu():
    pytest.importorskip("nudenet")
    imagemod._detector = None
    meta = {}
    assert imagemod.review_upload(_png(64), meta) == imagemod.APPROVE
    assert not meta.get("force_nsfw")
    assert imagemod._detector.onnx_session.get_providers() == ["CPUExecutionProvider"]
