"""Click through an automatic photo check and the per-photo Report button.
python tests/ui_photo_check.py URL OUTDIR
"""
import os
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1].rstrip("/")
OUT = sys.argv[2]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PNG = open(os.path.join(ROOT, "static", "sample.jpg"), "rb").read()
bad = []


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name, extra)
    if not cond:
        bad.append(name)


def shot(page, name):
    page.screenshot(path=os.path.join(OUT, name), full_page=True)


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        owner = browser.new_context()
        api = owner.request
        signup = api.post(URL + "/api/me/signup", data={"display_name": "Ada", "dob": "1985-05-05"})
        ok("owner can sign up", signup.ok, signup.text()[:200])
        gen = api.post(URL + "/api/generate", multipart={
            "file": {"name": "a.jpg", "mimeType": "image/jpeg", "buffer": PNG},
            "mode": "relief", "photo_ack": "true",
        })
        ok("a photo build is accepted", gen.ok, gen.text()[:240])
        if not gen.ok:
            browser.close()
            return
        item = api.post(URL + "/api/showcase", data={
            "build_id": gen.json()["id"], "title": "Checked lamp", "description": "",
            "tags": [], "accept_guidelines": True, "nsfw": False, "visibility": "public",
        }).json()
        up = api.post(URL + f"/api/showcase/{item['id']}/prints", multipart={
            "photo": {"name": "print.jpg", "mimeType": "image/jpeg", "buffer": PNG},
            "caption": "It printed", "photo_ack": "true", "nsfw": "no",
        })
        ok("clean photo is accepted", up.ok, up.text()[:300])
        if up.ok:
            body = up.json()
            ok("clean photo is visible immediately", body.get("pending") is False and body.get("status") == "approved", body)
            pid = body["id"]
        else:
            pid = ""
        viewer = browser.new_context(viewport={"width": 1280, "height": 900})
        page = viewer.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(URL + "/#showcase")
        page.wait_for_selector("#shGrid .pcard", timeout=20000)
        page.fill("#shSearch", "Checked lamp")
        page.press("#shSearch", "Enter")
        page.wait_for_selector("#shGrid .pcard:has-text('Checked lamp')", timeout=15000)
        page.click("#shGrid .pcard:has-text('Checked lamp')")
        page.wait_for_selector("#prGallery", timeout=10000)
        page.wait_for_selector("#prGallery [aria-label='Report this photo']", timeout=10000)
        gallery = page.inner_text("#prGallery")
        ok("approved photo has no waiting pill", "Waiting for review" not in gallery, gallery[:240])
        shot(page, "photo-gallery.png")
        page.click("#prGallery [aria-label='Report this photo']")
        page.wait_for_selector("#dlgReport[open]", timeout=5000)
        ok("report dialog is about the photo", "Report this photo" in page.inner_text("#dlgReport"))
        shot(page, "photo-report-dialog.png")
        page.click("#dlgReport label.choice:has-text('Something else')")
        page.click("#repSend")
        page.wait_for_timeout(1200)
        ok("report is thanked and the dialog closes", page.locator("#dlgReport[open]").count() == 0 and "Thank you" in page.inner_text("#toasts"))
        shot(page, "photo-reported.png")
        page.goto(URL + "/legal/community-guidelines")
        rules = page.inner_text("body")
        ok("guidelines say photos are checked on our server", "checked automatically on our server" in rules)
        ok("guidelines say many reports can remove a photo", "many different people" in rules and "remove a photo" in rules)
        shot(page, "guidelines.png")
        page.goto(URL + "/admin/moderation")
        page.fill("#tok", "t0k")
        page.click("#tokForm button")
        page.wait_for_selector("#plist", timeout=8000)
        queue = page.inner_text("body")
        ok("queue offers optional review of held photos", "held for optional review" in queue)
        ok("the approved photo is not sitting in that queue", pid not in queue)
        shot(page, "moderation-queue.png")
        ok("no page errors", not errors, errors)
        viewer.close()
        owner.close()
        browser.close()


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    run()
    sys.exit(1 if bad else 0)
