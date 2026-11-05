"""Local photo check for user uploads ("I printed this" and other photos).

The default checker is NudeNet's 320n detector (an ONNX model, about 12 MB) run
in-process with onnxruntime on the CPU. The model is loaded on the first photo,
not at startup. Pixels are not sent anywhere.

Outcomes:
* exposed genitals or an exposed anus -> reject (the photo is not saved)
* exposed breasts or buttocks -> approve and force the existing NSFW tag (blurred)
* anything else -> approve
* the model missing, or any error -> needs_human_review (never an automatic approve)

NudeNet has no separate "sexual act" label. A sexual image is rejected when one of
the explicit labels above is detected. A `deep` check (used after many reports)
lowers the score cutoffs and also runs the same model on crops of the photo.

`set_review_hook` replaces the checker (tests). Pass None to use the model again.
"""
from __future__ import annotations

import io
import logging
import os
import threading

from PIL import Image

NEEDS_HUMAN_REVIEW = "needs_human_review"
REJECT = "reject"
APPROVE = "approve"

# Shown to the uploader. It does not name body parts.
REFUSED_MESSAGE = (
    "This photo wasn't saved because it doesn't follow the community guidelines. "
    "Please choose a different photo."
)
HELD_NOTE = "The automatic check could not run, so this photo is held."

# NudeNet's own post-process keeps detections from about 0.2 up. These cutoffs
# sit above that. Deep-check cutoffs are lower on purpose (stricter).
EXPLICIT = frozenset({
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "ANUS_EXPOSED",
})
MILD = frozenset({
    "FEMALE_BREAST_EXPOSED",
    "BUTTOCKS_EXPOSED",
})
REJECT_AT = 0.45
MILD_AT = 0.50
DEEP_REJECT_AT = 0.30
DEEP_MILD_AT = 0.35

_log = logging.getLogger("zeim.imagemod")
_lock = threading.Lock()
_detector = None
_hook = None


def default_review(data: bytes, meta: dict | None = None) -> str:
    """Hold the photo. Used when a caller asks for the old safe default, and by tests."""
    return NEEDS_HUMAN_REVIEW


def set_review_hook(fn) -> None:
    """Replace the checker. Pass None to use the local model again."""
    global _hook
    _hook = fn


def review_upload(data: bytes, meta: dict | None = None) -> str:
    """Check uploaded image bytes. `meta` may hold item_id, uid, and deep=True.

    A checker that sets meta['force_nsfw'] is asking the caller to apply the
    existing mature-content tag. Errors become needs_human_review.
    """
    if meta is None:
        meta = {}
    fn = _hook or _model_review
    try:
        result = fn(data, meta)
    except Exception:
        _log.exception("image check failed")
        meta["check_note"] = HELD_NOTE
        return NEEDS_HUMAN_REVIEW
    if result not in (NEEDS_HUMAN_REVIEW, REJECT, APPROVE):
        return NEEDS_HUMAN_REVIEW
    return result


def _model_path() -> str:
    # Imported here so the process does not load onnxruntime or OpenCV until a photo arrives.
    import nudenet
    return os.path.join(os.path.dirname(nudenet.__file__), "320n.onnx")


def _load_detector():
    """One CPU session, created on first use. Raises if the weights are missing."""
    global _detector
    if _detector is not None:
        return _detector
    import onnxruntime as ort
    from nudenet import NudeDetector

    path = _model_path()
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    # Build the detector without NudeDetector.__init__, which would open a second session
    # and does not pin the provider list (that argument is unused in nudenet 3.4.2).
    det = NudeDetector.__new__(NudeDetector)
    det.onnx_session = ort.InferenceSession(path, sess_options=options, providers=["CPUExecutionProvider"])
    providers = det.onnx_session.get_providers()
    if not providers or providers[0] != "CPUExecutionProvider":
        raise RuntimeError("photo check must use the CPU")
    det.input_width = 320
    det.input_height = 320
    det.input_name = det.onnx_session.get_inputs()[0].name
    _detector = det
    _log.info("nudity detector loaded: model=nudenet-320n providers=%s", ",".join(providers))
    return _detector


def _detect(data: bytes) -> list[dict]:
    """Run the model on one image (bytes). Tests replace this. Raises on failure."""
    with _lock:
        found = _load_detector().detect(data)
    return list(found or [])


def _tile_bytes(data: bytes) -> list[bytes]:
    """Center crop plus a 2x2 of overlapping tiles. The full frame is scanned separately."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size
    boxes: list[tuple[int, int, int, int]] = []
    cw, ch = int(w * 0.70), int(h * 0.70)
    if cw >= 32 and ch >= 32:
        left, top = (w - cw) // 2, (h - ch) // 2
        boxes.append((left, top, left + cw, top + ch))
    tw, th = int(w * 0.62), int(h * 0.62)
    if tw >= 32 and th >= 32 and w >= 64 and h >= 64:
        for x in (0, max(0, w - tw)):
            for y in (0, max(0, h - th)):
                boxes.append((x, y, min(w, x + tw), min(h, y + th)))
    out: list[bytes] = []
    seen: set[tuple[int, int, int, int]] = set()
    for box in boxes:
        if box in seen:
            continue
        seen.add(box)
        buf = io.BytesIO()
        im.crop(box).save(buf, format="JPEG", quality=90)
        out.append(buf.getvalue())
    return out


def _scan(data: bytes, *, deep: bool) -> list[dict]:
    hits = _detect(data)
    if deep:
        for tile in _tile_bytes(data):
            hits.extend(_detect(tile))
    return hits


def _policy(hits: list[dict], *, deep: bool) -> str:
    """'reject', 'mild', or 'approve'. Explicit wins over mild."""
    reject_at = DEEP_REJECT_AT if deep else REJECT_AT
    mild_at = DEEP_MILD_AT if deep else MILD_AT
    mild = False
    for hit in hits:
        label = hit.get("class") or ""
        try:
            score = float(hit.get("score") or 0)
        except (TypeError, ValueError):
            continue
        if label in EXPLICIT and score >= reject_at:
            return "reject"
        if label in MILD and score >= mild_at:
            mild = True
    return "mild" if mild else "approve"


def _model_review(data: bytes, meta: dict) -> str:
    deep = bool(meta.get("deep"))
    kind = _policy(_scan(data, deep=deep), deep=deep)
    if kind == "reject":
        _log.info("image check: result=reject deep=%s", deep)
        return REJECT
    if kind == "mild":
        meta["force_nsfw"] = True
        meta["check_note"] = "Marked as mature content."
        _log.info("image check: result=approve nsfw=1 deep=%s", deep)
        return APPROVE
    _log.info("image check: result=approve deep=%s", deep)
    return APPROVE
