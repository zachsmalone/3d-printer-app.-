"""Zach's report: 'the upload image doesn't work'. Diagnosis: iPhones/iPads send HEIC (accept=image/*), Pillow could not open it
('cannot read image: HEIF'), and the browser only showed a disappearing toast. Also covers EXIF/GPS stripping (CR-2/S-08),
rotation, size limits and the friendly messages."""
import io, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from PIL import Image
from app import config
from app.core import imagesafe
from tests.b1 import *

UNREADABLE = "We couldn't open that photo. Try a JPG or PNG."


def exif_gps(orientation=1):
    ex = Image.Exif()
    ex[0x010F] = "SecretCam"
    ex[0x0112] = orientation
    ex[0x8825] = {1: "N", 2: (41.0, 52.0, 0.0), 3: "W", 4: (87.0, 38.0, 0.0)}
    return ex


def jpeg(size=(60, 40), orientation=1, exif=True):
    im = Image.open(SAMPLE).convert("RGB").resize(size); b = io.BytesIO()
    im.save(b, "JPEG", exif=exif_gps(orientation) if exif else None); return b.getvalue()


def heic(size=(80, 60), exif=True):
    import pillow_heif
    pillow_heif.register_heif_opener()
    im = Image.open(SAMPLE).convert("RGB").resize(size); b = io.BytesIO()
    im.save(b, "HEIF", quality=80, exif=exif_gps().tobytes() if exif else None); return b.getvalue()


def stored(bid):
    f = next(p for p in (config.OUT / bid).iterdir() if p.name.startswith("source."))
    return f, f.read_bytes()


def clean(raw):
    assert b"SecretCam" not in raw and b"Exif" not in raw[:200]
    im = Image.open(io.BytesIO(raw)); assert not dict(im.getexif()) and not im.getexif().get_ifd(0x8825) and not im.info.get("xmp")


def test_heic_from_an_iphone_is_converted_not_rejected():
    c = client(); data = heic()
    assert data[4:12] == b"ftypheic" or b"ftyp" in data[:16]
    r = gen(c, name="IMG_0042.HEIC", data=data, ctype="image/heic"); assert r.status_code == 200, r.text
    f, raw = stored(r.json()["id"]); assert f.suffix == ".jpg" and Image.open(io.BytesIO(raw)).format == "JPEG"; clean(raw)
    # lower-case extension, wrong content type, and the Edit workspace too
    assert gen(c, name="photo.heif", data=heic(), ctype="application/octet-stream").status_code == 200
    e = c.post("/api/edit/new", files={"file": ("IMG_1.heic", heic(), "image/heic")}); assert e.status_code == 200, e.text
    f, raw = stored(e.json()["id"]); assert f.suffix == ".jpg"; clean(raw)


def test_malformed_heic_gets_the_friendly_unreadable_message():
    # a file with an HEIC-looking header but a broken body must not pass the gate as "heic"
    garbage_heic = b"\x00\x00\x00\x18ftypheic" + b"garbage" * 20
    r = gen(client(), name="IMG_1234.HEIC", data=garbage_heic, ctype="image/heic")
    assert r.status_code == 400 and r.json()["detail"] == UNREADABLE, r.text


def test_without_the_heif_plugin_the_message_is_friendly(monkeypatch):
    monkeypatch.setattr(imagesafe, "ALLOWED", imagesafe.ALLOWED - {"HEIF"})
    r = gen(client(), name="IMG.HEIC", data=heic(), ctype="image/heic")
    assert r.status_code == 400 and r.json()["detail"] == UNREADABLE


def test_gps_and_camera_info_are_stripped_from_jpeg_and_png_everywhere():
    c = client(); raw = jpeg()
    assert b"SecretCam" in raw
    r = gen(c, name="holiday.png", data=raw, ctype="image/png"); assert r.status_code == 200      # JPEG with a wrong name
    f, out = stored(r.json()["id"]); assert f.suffix == ".jpg"; clean(out)
    e = c.post("/api/edit/new", files={"file": ("pic.jpg", raw, "image/jpeg")}); assert e.status_code == 200
    f, out = stored(e.json()["id"]); clean(out)
    png = io.BytesIO(); im = Image.open(SAMPLE).convert("RGB"); from PIL import PngImagePlugin
    info = PngImagePlugin.PngInfo(); info.add_text("Comment", "SecretCam at home"); im.save(png, "PNG", pnginfo=info)
    r = gen(c, name="x.exe.jpg", data=png.getvalue(), ctype="image/jpeg"); f, out = stored(r.json()["id"])
    assert f.suffix == ".png" and b"SecretCam" not in out


def test_exif_rotation_is_applied_before_metadata_is_dropped():
    c = client()
    r = gen(c, name="r.jpg", data=jpeg((60, 40), orientation=6), ctype="image/jpeg"); assert r.status_code == 200
    f, out = stored(r.json()["id"]); w, h = Image.open(io.BytesIO(out)).size
    assert (w, h) == (40, 60)                                    # a phone photo taken in portrait stays portrait
    assert r.json()["stats"]["size_mm"][1] > r.json()["stats"]["size_mm"][0]


def test_unreadable_oversized_and_huge_images_get_clear_messages_fast():
    big = io.BytesIO(); Image.new("RGB", (12000, 12000), (200, 10, 10)).save(big, "PNG")          # 144 MP, tiny file (the B-14 case); made BEFORE the clock starts (making it takes ~4 s)
    c = client(); t0 = time.time()
    for name, data in (("a.jpg", b"not an image at all"), ("b.png", b""), ("c.jpg", b"\x89PNG\r\n\x1a\n" + b"0" * 50), ("d.txt", b"hello")):
        r = gen(c, name=name, data=data, ctype="image/jpeg"); assert r.status_code == 400 and r.json()["detail"] == UNREADABLE, (name, r.text)
    r = gen(c, name="huge.png", data=big.getvalue()); assert r.status_code == 400 and "very large" in r.json()["detail"]
    assert time.time() - t0 < 5
    wide = io.BytesIO(); Image.new("RGB", (6000, 3000), (10, 120, 200)).save(wide, "PNG")
    r = gen(c, name="wide.png", data=wide.getvalue()); assert r.status_code == 200
    f, out = stored(r.json()["id"]); assert max(Image.open(io.BytesIO(out)).size) == imagesafe.MAX_SIDE
    r = c.post("/api/generate", files={"file": ("big.jpg", b"0" * (config.MAX_UPLOAD + 10), "image/jpeg")}, data={"mode": "relief"})
    assert r.status_code == 413
    e = c.post("/api/edit/new", files={"file": ("bad.png", b"junk", "image/png")}); assert e.status_code == 415 and e.json()["detail"] == UNREADABLE


def test_png_jpg_webp_gif_bmp_still_work():
    c = client()
    for fmt in ("PNG", "JPEG", "WEBP", "GIF", "BMP"):
        b = io.BytesIO(); Image.open(SAMPLE).convert("RGB").resize((50, 40)).save(b, fmt)
        r = gen(c, name="x." + fmt.lower(), data=b.getvalue(), auto_delete_oldest="true"); assert r.status_code == 200, (fmt, r.text)
    rgba = io.BytesIO(); Image.new("RGBA", (40, 40), (0, 0, 0, 0)).save(rgba, "PNG")
    assert gen(c, name="t.png", data=rgba.getvalue(), auto_delete_oldest="true").status_code == 200


def test_photo_is_private_by_default_and_not_kept_until_build():
    c = client(); bid = photo_build(c)
    assert c.get("/api/builds").json()["builds"][-1]["visibility"] == "private"
    n = len(list(config.OUT.glob("*/meta.json")))
    gen(c, name="bad.jpg", data=b"junk")                      # a refused photo leaves nothing behind
    assert len(list(config.OUT.glob("*/meta.json"))) == n and not [p for p in config.OUT.iterdir() if p.is_dir() and not (p / "meta.json").exists()]
