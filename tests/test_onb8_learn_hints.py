from pathlib import Path
import re


def test_each_hint_points_at_a_real_lesson():
    src = Path("app/community/education.py").read_text()
    html = Path("static/index.html").read_text() + Path("static/cad.html").read_text()
    hints = re.findall(r'data-learnq="([a-z0-9-]+)"', html)
    assert sorted(hints) == ["first-print", "intro-modeling", "lithophanes"]
    for h in hints:
        assert f'"{h}"' in src
