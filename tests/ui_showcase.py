from playwright.sync_api import sync_playwright
errs=[]
with sync_playwright() as p:
    b=p.chromium.launch(channel="chrome"); pg=b.new_page(viewport={"width":1400,"height":900})
    pg.on("pageerror",lambda e:errs.append(str(e))); pg.on("console",lambda m: errs.append(m.text) if m.type=="error" else None)
    pg.goto("http://localhost:8765/"); pg.wait_for_timeout(800)
    pg.click('#mainNav [data-view=showcase]'); pg.wait_for_timeout(800)
    print("cards", pg.locator("#shGrid .pcard").count())
    pg.click('#shTabs [data-tab=free]'); pg.wait_for_timeout(500); print("free", pg.locator("#shGrid .pcard").count())
    pg.fill('#shSearch','dino'); pg.wait_for_timeout(800); print("search", pg.locator("#shGrid .pcard").count())
    pg.locator("#shGrid .pcard").first.click(); pg.wait_for_timeout(500)
    print("like btn", pg.locator("#itLike").count())
    pg.click("#itLike"); pg.wait_for_timeout(500); print(pg.locator("#itLike").inner_text())
    pg.screenshot(path="previews/ui_showcase_like.png")
    pg.keyboard.press("Escape")
    pg.click('#mainNav [data-view=learn]'); pg.wait_for_timeout(800); print("lessons", pg.locator("#lessonGrid .pcard").count())
    pg.goto("http://localhost:8765/#join/ABCDE"); pg.wait_for_timeout(800)
    b.close()
print("errors",errs)
