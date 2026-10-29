"""Exit, Done, and New build outside CAD. Showcase stays a separate action."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
BAR = (ROOT / "static" / "workspace-bar.js").read_text(encoding="utf-8")
HAND = (ROOT / "static" / "handoff.js").read_text(encoding="utf-8")
EDIT = (ROOT / "static" / "edit.js").read_text(encoding="utf-8")
APP = (ROOT / "static" / "app.js").read_text(encoding="utf-8")


def _between(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def _bars(chunk):
    return re.findall(r'<div class="wsbar"[^>]*>.*?</div>', chunk, flags=re.S)


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_workspace_control_decisions():
    r = subprocess.run(
        ["node", "--test", str(ROOT / "tests/js/workspace-controls.test.mjs"), str(ROOT / "tests/js/studio-library.test.mjs")],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_outside_cad_bars_keep_exit_done_new_build_and_return_off_showcase():
    sections = {
        "lithophane": _between(HTML, 'id="viewCreate"', 'id="viewEdit"'),
        "slicer": _between(HTML, 'id="viewEdit"', 'id="viewShowcase"'),
        "torchc0": _between(HTML, 'id="viewTorch"', 'id="viewAi3d"'),
        "ai3d": _between(HTML, 'id="viewAi3d"', 'id="viewFix"'),
    }
    for name, chunk in sections.items():
        bars = _bars(chunk)
        assert len(bars) == 1, name
        bar = bars[0]
        assert f'data-ws="{name}"' in bar
        for act in ("exit", "done", "new-build", "return-studio"):
            assert f'data-ws-act="{act}"' in bar
        assert 'aria-label="Exit workspace"' in bar
        assert ">Done</button>" in bar
        assert ">New build</button>" in bar
        assert ">Return to Account</a>" in bar
        assert 'href="#account"' in bar
        assert 'href="#projects"' not in bar
        assert 'href="#account/studio"' not in bar
        assert "btnPublish" not in bar
        assert "sendToShowcase" not in bar
        assert 'data-to="showcase"' not in bar
        assert "publish=" not in bar
    create = sections["lithophane"]
    assert 'id="btnPublish"' in create
    assert "Send to Showcase" in create
    assert 'id="studioFromMe"' in create
    assert 'data-ws-act="return-studio"' in create
    assert "Return to Account" in create
    assert "Return to Projects" not in HTML
    assert HTML.count('<script type="module" src="/static/workspace-bar.js"></script>') == 1


def test_new_build_saves_or_asks_and_exit_uses_leave_without_publishing():
    assert "zeimSave.leave" in BAR
    assert "guardNewBuild" in BAR
    assert "sendToShowcase" not in BAR
    assert "zeimOpenShowcase" not in BAR
    assert "publish=" not in BAR
    assert 'guardNewBuild("slicer")' in EDIT
    assert "Open another model" not in EDIT
    assert "function clearSlicerWork" in EDIT
    assert "function clearLithoWork" in APP
    clear = APP[APP.index("function clearLithoWork"):APP.index('document.addEventListener("zeim:new-build"')]
    assert "sendToShowcase" not in clear and "/api/builds/" not in clear
    assert 'e.detail.publish' in APP
    assert "marker.studio" in HAND
    assert "isPublishUrl" in HAND
    assert "zeim:torchc0-forget" in HAND
