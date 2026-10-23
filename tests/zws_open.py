"""Browser-test helper: start with the floating workspace panels open, as for a returning phone user who has
already tapped their chips once. C's phone layout starts them as chips; tests that drive the panel controls use
`zws_open.install()` (or install(("tools",)) to open just one, as a user taps one chip) so they test the controls, not the chip. The 18+ gate is unaffected."""
def script(panels=("settings", "result", "tools", "out")):
    return OPEN_PANELS.replace("__PANELS__", ", ".join(f"{p}: open" for p in panels))


OPEN_PANELS = """(() => { try {
  const open = { min: false, hidden: false };
  for (const ws of ["studio", "litho", "slicer", "torch", "torchc0", "cad"]) {
    const k = "zeim.ws.guest." + ws;
    if (!localStorage.getItem(k)) localStorage.setItem(k, JSON.stringify({ __PANELS__ }));
  }
} catch (e) {} })()"""


def install(panels=("settings", "result", "tools", "out")):
    """Add OPEN_PANELS to every browser context this script creates (call once, before launching)."""
    from playwright.sync_api import Browser
    if getattr(Browser, "_zws_open", False): return
    js = script(panels)
    nc, np_ = Browser.new_context, Browser.new_page
    def new_context(self, *a, **k):
        c = nc(self, *a, **k); c.add_init_script(js); return c
    def new_page(self, *a, **k):
        p = np_(self, *a, **k); p.context.add_init_script(js); return p
    Browser.new_context, Browser.new_page, Browser._zws_open = new_context, new_page, True
