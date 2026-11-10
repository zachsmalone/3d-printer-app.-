"""Loaded TorchC0 uses the page width: the viewer is not stuck in the right half."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "static" / "torchc0.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def _panel():
    return JS.split("function panelHTML()", 1)[1].split("function ", 1)[0]


def test_viewer_is_not_capped_in_the_right_column():
    panel = _panel()
    assert 'class="field rzFileCol"' in panel
    assert 'id="rzPickView" class="rzView"' in panel
    assert "height:min(60vw,300px)" not in panel
    row = panel.split('class="grid2 rzRow"', 1)[1].split("</div></div>", 1)[0]
    assert 'id="rzSupEdit"' in row and 'id="rzMaterial"' not in row
    assert panel.index('id="rzPickView"') < panel.index('id="rzSupEdit"') < panel.index('id="rzMaterial"')
    assert panel.index('id="rzMaterial"') < panel.index('id="rzAdv"')


def test_wide_screen_puts_the_support_panel_beside_the_viewer():
    wide = CSS.split("@media (min-width:960px){", 1)[1].split("@media", 1)[0]
    assert "#viewTorch.has-model .rzFileCol" in wide
    assert "minmax(0,1fr) minmax(280px,min(400px,32%))" in wide
    assert '"view supports"' in wide
    assert "#viewTorch.has-model #rzPickView{grid-area:view" in wide
    assert "#viewTorch.has-model #rzSupEdit{grid-area:supports" in wide
    assert "@media (max-width:480px){.rzRow{grid-template-columns:1fr}" in CSS
