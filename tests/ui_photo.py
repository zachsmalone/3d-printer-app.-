"""Headless Chrome check of the photo start (Studio + Edit): choose / take / sample, HEIC, bad file, camera blocked, phone layout.
Needs Chrome + playwright (not part of pytest).  python tests/ui_photo.py http://127.0.0.1:8799   (use a TEMP-data server, not 8765)"""
import io, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8799"
T = tempfile.mkdtemp(); R = []
def ok(name, cond, extra=""): R.append((name, bool(cond), extra)); print(("PASS " if cond else "FAIL ") + name, extra)

jpg = T + "/p.jpg"; Image.open(os.path.join(os.path.dirname(__file__), "sample.png")).convert("RGB").save(jpg, "JPEG")
import pillow_heif; pillow_heif.register_heif_opener()
heic = T + "/IMG_0001.HEIC"; Image.open(jpg).save(heic, "HEIF")
bad = T + "/bad.jpg"; open(bad, "wb").write(b"this is not a photo")
os.makedirs("previews", exist_ok=True)
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

with sync_playwright() as p:
    args = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
    # ---------------- phone, 390x844
    b = p.chromium.launch(channel="chrome", args=args)
    ctx = b.new_context(viewport={"width": 390, "height": 844}, user_agent=IPHONE, has_touch=True, is_mobile=True, device_scale_factor=2)
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL); pg.wait_for_timeout(700)
    for sel in ("#sChoose", "#sTake", "#sSample"):
        bx = pg.locator(sel).bounding_box(); ok(f"phone: {sel} visible, >=44px tall, inside viewport", bx and bx["height"] >= 44 and bx["x"] >= 0 and bx["x"] + bx["width"] <= 391, str(bx))
    ok("phone: privacy + permission lines under the buttons", "stay private to you" in pg.inner_text("#sPick") and "ask first" in pg.inner_text("#sPick"))
    ok("phone: capture input present", pg.locator('#sCam[capture="environment"]').count() == 1)
    pg.screenshot(path="previews/photo_phone_start.png")
    pg.set_input_files("#sFile", jpg)
    pg.wait_for_selector("#result:not([hidden])", timeout=60000); pg.wait_for_timeout(500)
    ok("phone: Beginner auto-builds after choosing a photo", pg.locator("#result").is_visible())
    ok("phone: 'Change photo' link visible", pg.locator("#changePhoto").is_visible())
    pg.screenshot(path="previews/photo_phone_built.png")
    pg.set_input_files("#sFile", heic); pg.wait_for_timeout(300); pg.wait_for_function("document.querySelector('#makingLine').hidden", timeout=60000)
    ok("phone: HEIC photo builds (no error message)", pg.locator("#sMsg").is_hidden())
    pg.set_input_files("#sFile", bad); pg.wait_for_selector("#sMsg:not([hidden])", timeout=30000); pg.wait_for_timeout(2500)
    ok("phone: unreadable photo -> persistent inline message", "couldn't open that photo" in pg.inner_text("#sMsg") and pg.locator("#sMsg").is_visible(), pg.inner_text("#sMsg"))
    pg.screenshot(path="previews/photo_phone_error.png")
    ok("phone: no horizontal scroll", pg.evaluate("document.documentElement.scrollWidth") <= 390)
    ok("phone: no page errors", not errs, str(errs))
    ctx.close(); b.close()

    # ---------------- desktop WITH a (fake) camera
    b = p.chromium.launch(channel="chrome", args=args + ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
    ctx = b.new_context(viewport={"width": 1280, "height": 800}, permissions=["camera"]); pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL); pg.wait_for_timeout(800)
    ok("desktop+camera: Take a photo is shown", pg.locator("#sTake").is_visible())
    pg.click("#sTake"); pg.wait_for_selector("#sCamPanel:not([hidden])", timeout=10000); pg.wait_for_timeout(1200)
    pg.screenshot(path="previews/photo_desktop_camera_live.png")
    pg.click("#sSnap"); pg.wait_for_selector("#sUse:not([hidden])"); pg.screenshot(path="previews/photo_desktop_camera_captured.png")
    ok("desktop: stream stopped right after capture", pg.evaluate("!document.querySelector('#sVideo').srcObject || document.querySelector('#sVideo').srcObject.getTracks().every(t => t.readyState === 'ended')"))
    pg.click("#sRetake"); pg.wait_for_selector("#sSnap:not([hidden])", timeout=10000); pg.click("#sSnap"); pg.click("#sUse")
    pg.wait_for_selector("#result:not([hidden])", timeout=60000)
    ok("desktop: camera photo -> built", pg.locator("#result").is_visible())
    pg.click("#sCamCancel") if pg.locator("#sCamPanel").is_visible() else None
    # Edit
    pg.click('#mainNav [data-view=edit]'); pg.wait_for_timeout(400)
    ok("edit: 3D-file input only takes mesh files", pg.get_attribute("#editFile", "accept") == ".stl,.obj,.3mf")
    ok("edit: photo buttons present", pg.locator("#eChoose").is_visible() and pg.locator("#eTake").is_visible())
    pg.screenshot(path="previews/photo_edit_start.png")
    pg.set_input_files("#eFile", heic); pg.wait_for_selector("#editPanel:not([hidden])", timeout=60000)
    ok("edit: HEIC photo opens as a project", pg.locator("#editPanel").is_visible())
    ok("desktop: no page errors", not errs, str(errs))
    ctx.close(); b.close()

    # ---------------- desktop, camera permission denied / no camera
    b = p.chromium.launch(channel="chrome", args=args)
    ctx = b.new_context(viewport={"width": 1280, "height": 800}); pg = ctx.new_page()
    pg.add_init_script("""const o = navigator.mediaDevices; if (o) { o.enumerateDevices = async () => [{kind:'videoinput', deviceId:'x', label:''}];
      o.getUserMedia = async () => { throw new DOMException('denied', 'NotAllowedError'); }; }""")
    pg.goto(URL); pg.wait_for_timeout(800)
    pg.click("#sTake"); pg.wait_for_selector("#sMsg:not([hidden])")
    ok("camera denied: calm persistent message + Choose button right there", pg.inner_text("#sMsg") == "ZEIM can't use the camera. You can choose a photo instead." and pg.locator("#sChoose").is_visible())
    pg.screenshot(path="previews/photo_camera_blocked.png")
    pg.click("#sSample"); pg.wait_for_selector("#result:not([hidden])", timeout=60000)
    ok("one-click sample image builds", pg.locator("#result").is_visible())
    ctx.close()
    ctx = b.new_context(viewport={"width": 1280, "height": 800}); pg = ctx.new_page()
    pg.add_init_script("if (navigator.mediaDevices) navigator.mediaDevices.enumerateDevices = async () => [];")
    pg.goto(URL); pg.wait_for_timeout(800)
    ok("desktop with no camera device: Take a photo is hidden", pg.locator("#sTake").is_hidden() and pg.locator("#sChoose").is_visible() and pg.locator("#sSample").is_visible())
    ctx.close(); b.close()
bad_ = [r for r in R if not r[1]]
print(f"\n{len(R) - len(bad_)}/{len(R)} checks passed"); sys.exit(1 if bad_ else 0)
