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


def test_preview_dock_sits_above_the_scrolling_tools():
    panel = _panel()
    assert 'id="rzPreviewDock"' in panel and 'id="rzTools"' in panel
    assert panel.index('id="rzPreviewDock"') < panel.index('id="rzPickView"') < panel.index('id="rzTools"')
    assert panel.index('id="rzTools"') < panel.index('id="rzSupEdit"')
    assert "minmax(280px,min(400px,32%))" not in CSS
    assert "main.zws #torchPanel .rzPreviewDock{flex:1 1 42%" in CSS
    assert "main.zws #torchPanel .rzTools{flex:1 1 auto" in CSS
    assert "@media (max-width:480px){.rzRow{grid-template-columns:1fr}" in CSS
