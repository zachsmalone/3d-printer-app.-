"""Publish and challenge entry pick a project. A Showcase URL is not the happy path.

Exit, Done, and New build still never publish. Paste stays only as a collapsed fallback.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
COMM = (ROOT / "static" / "community.js").read_text(encoding="utf-8")
HAND = (ROOT / "static" / "handoff.js").read_text(encoding="utf-8")
TORCH = (ROOT / "static" / "torchc0.js").read_text(encoding="utf-8")
AI = (ROOT / "static" / "ai3d.js").read_text(encoding="utf-8")
CAD = (ROOT / "static" / "cad.js").read_text(encoding="utf-8")
LIB = (ROOT / "static" / "studio-library.js").read_text(encoding="utf-8")
BAR = (ROOT / "static" / "workspace-bar.js").read_text(encoding="utf-8")
CTRL = (ROOT / "static" / "workspace-controls.js").read_text(encoding="utf-8")


def _between(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def _bars(chunk):
    return re.findall(r'<div class="wsbar"[^>]*>.*?</div>', chunk, flags=re.S)


def test_remix_credit_is_a_picker_and_paste_is_advanced():
    box = _between(HTML, 'id="pubRemixBox"', 'id="pub_allow_remix"')
    assert "Use the project I just remixed" in box
    assert 'id="pubRemixSearch"' in box
    assert "Remixed from" in box
    adv = _between(box, 'id="pubRemixAdv"', "</details>")
    assert 'id="pub_remix"' in adv
    assert "Paste a Showcase link" in adv
    assert "optional: paste the Showcase link" not in HTML
    assert "rememberRemixIntent" in COMM
    assert "searchRemixSources" in COMM
    assert "Remixed from" in COMM
    assert "offerChallenge" in COMM
    assert 'id="dlgEnterOffer"' in HTML
    assert "Enter an open challenge?" in HTML


def test_challenge_enter_picks_a_remix_and_hides_the_url():
    assert "/eligible" in COMM
    assert "Your public credited remixes" in COMM
    assert "You don't have a public credited remix to enter yet." in COMM
    assert 'href="#lithophane"' in COMM and 'href="#showcase"' in COMM
    assert "chEnterPaste" in COMM
    assert "Your remix project id or /p/" not in COMM
    assert "Paste your remix's Showcase link" not in COMM
    # The id field still exists, inside the collapsed fallback.
    adv = COMM.split('id="chEnterAdv"', 1)[1].split("</details>", 1)[0]
    assert 'id="chEnterId"' in adv
    assert "Enter with a project id" in adv


def test_send_to_showcase_sits_where_work_finishes_not_on_leave_controls():
    sections = {
        "lithophane": _between(HTML, 'id="viewCreate"', 'id="viewEdit"'),
        "slicer": _between(HTML, 'id="viewEdit"', 'id="viewShowcase"'),
        "torchc0": _between(HTML, 'id="viewTorch"', 'id="viewAi3d"'),
        "ai3d": _between(HTML, 'id="viewAi3d"', 'id="viewFix"'),
    }
    for name, chunk in sections.items():
        for bar in _bars(chunk):
            assert "btnPublish" not in bar
            assert "editPublish" not in bar
            assert "sendToShowcase" not in bar
            assert 'data-to="showcase"' not in bar
            assert "publish=" not in bar
    assert 'id="btnPublish"' in sections["lithophane"] and "Send to Showcase" in sections["lithophane"]
    result = _between(sections["slicer"], 'id="editResult"', 'id="slicerDock"')
    assert 'id="editPublish"' in result and "Send to Showcase" in result
    assert "sendToShowcase" not in sections["slicer"]
    assert 'id="rzPublish"' in TORCH and 'id="rzPublishResult"' in TORCH
    assert "zeim:send-showcase" in TORCH and "zeim:send-showcase" in HAND
    assert '$("#editPublish")' in HAND and 'sendToShowcase("slicer")' in HAND
    assert 'id="a3Publish"' in AI and "zeimOpenShowcase" in AI
    assert "Those buttons do not send it to Showcase." in AI
    assert 'id="cwSendShowcase"' in (ROOT / "static" / "cad.html").read_text(encoding="utf-8")
    send = CAD.split('$("#cwSendShowcase")', 1)[1].split("cwToSlicer", 1)[0]
    assert "publish=" in send
    assert 'data-lib="showcase"' in LIB and "Send to Showcase" in LIB
    assert "action === \"showcase\"" in COMM
    assert "zeimOpenShowcase" not in BAR and "sendToShowcase" not in BAR
    assert "publish: false" in CTRL
    assert "plansNeverPublish" in CTRL
