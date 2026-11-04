from pathlib import Path
JS = Path("static/onb10.js").read_text()

def test_loaded_and_shown_once():
    assert '/static/onb10.js' in Path("static/index.html").read_text()
    assert 'localStorage.setItem(KEY' in JS and 'if (localStorage.getItem(KEY)) return' in JS

def test_challenge_only_when_open():
    assert 'c.status === "open"' in JS and '(ch ?' in JS
    assert 'window.zeimOpenChallenge = cid => openChallenge(cid);' in Path("static/community.js").read_text()
