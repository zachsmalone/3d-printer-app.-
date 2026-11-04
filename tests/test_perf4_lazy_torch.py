from pathlib import Path
def test_torchc0_not_eager():
    s=Path("static/index.html").read_text()
    assert 'src="/static/torchc0.js"' not in s and 'import("/static/torchc0.js")' in s
