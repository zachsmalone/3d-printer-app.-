"""RET2: the build list warns about builds removed within 7 days and offers one-click Keep (star)."""
import pathlib, subprocess, shutil, pytest

JS = pathlib.Path(__file__).resolve().parents[1] / "static" / "app.js"


def _fn():
    s = JS.read_text()
    a = s.index("function expSoon(b)"); b = s.index("\n}\n", a) + 3
    return s[a:b]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_exp_soon_only_for_unstarred_builds_within_7_days():
    day = 86400000
    js = _fn() + f"""
const now = Date.now(), iso = d => new Date(now + d).toISOString();
console.log(JSON.stringify([
  expSoon({{id:"a", expires: iso(3*{day})}}).includes("Removed in 3 days"),
  expSoon({{id:"a", expires: iso(3*{day})}}).includes('data-fav="a"'),
  expSoon({{id:"a", expires: iso(20*{day})}}) === "",
  expSoon({{id:"a", favorite: true, expires: iso(1*{day})}}) === "",
  expSoon({{id:"a", expires: null}}) === "",
]));"""
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[true,true,true,true,true]"
