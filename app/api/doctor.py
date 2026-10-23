"""Failure photo doctor API (Smart Fix).

GET  /api/doctor/problems     the problem list (name + symptoms) the maker can pick from
POST /api/doctor/diagnose     picked problems + own words (+ optional photo, + printer/nozzle/material) -> plain-words
                              fixes with real PrusaSlicer keys. The photo goes through the same checks as every upload
                              (permission box, content sniffing, re-encode that strips EXIF/GPS, size caps, image-moderation
                              hook) and is NOT stored. Nothing is applied here; the browser asks before changing any setting.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.api.textcap import text_in
from app.community.identity import Actor, get_actor
from app import config
from app.core import imagesafe, ratelimit
from app.services import doctor

router = APIRouter(prefix="/api/doctor", tags=["doctor"])
MAX_PHOTO = 25 * 1024 * 1024


@router.get("/problems")
def problems():
    return {"problems": doctor.problems_public()}


@router.post("/diagnose")
def diagnose(request: Request, actor: Actor = Depends(get_actor), photo: Optional[UploadFile] = File(None),
             problems: str = Form(""), text: str = Form(""), photo_ack: bool = Form(False),
             printer_id: Optional[str] = Form(None), nozzle: Optional[str] = Form(None), material: Optional[str] = Form(None)):
    ip = request.client.host if request.client else "?"
    if not config.TESTING_MODE and not (ratelimit.hit("doctor:" + actor.sid, 60, 3600) and ratelimit.hit("doctorip:" + ip, 200, 3600)):
        raise HTTPException(429, "That's a lot of checks for one hour. Please wait a while.")
    try:
        words = text_in(text, 500, "Description")
        picked = [p for p in text_in(problems, 2000, "Problems").split(",") if p]
    except ValueError as e:
        raise HTTPException(400, str(e))
    photo_checked = False
    if photo is not None and photo.filename:
        data = photo.file.read(MAX_PHOTO + 1)
        if len(data) > MAX_PHOTO:
            raise HTTPException(413, "Photo too large (max 25 MB).")
        try:
            imagesafe.check_ack(data, photo_ack)
            clean, _ext, _im = imagesafe.sanitize(data)
        except imagesafe.ImageRefused as e:
            raise HTTPException(415, str(e))
        from app.community import imagemod
        if imagemod.review_upload(clean, {"kind": "doctor", "uid": (actor.user or {}).get("id")}) == imagemod.REJECT:
            raise HTTPException(415, "That photo was refused. Please try a different one.")
        photo_checked = True                    # checked, then dropped: never written to disk
    if not picked and not words.strip():
        raise HTTPException(400, "Pick what went wrong, or describe it in a few words.")
    out = doctor.diagnose(picked, words, printer_id, nozzle, material)
    out["photo"] = {"checked": photo_checked, "kept": False, "note": doctor.PHOTO_NOTE if photo_checked else None}
    return out
