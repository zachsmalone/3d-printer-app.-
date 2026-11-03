"""RET2: the visible Saved work list (studio-library.js) warns about builds removed within 7 days, with Keep it (= Star)."""
import pathlib, subprocess, shutil, pytest

LIB = pathlib.Path(__file__).resolve().parents[1] / "static" / "studio-library.js"


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_exp_soon_in_library_rows():
    js = f"""
import({str(LIB.as_uri())!r}).then(m => {{
  const now = Date.now(), iso = d => new Date(now + d * 864e5).toISOString(), id = "0123456789ab";
  const row = m.libraryHTML([{{id, title: "t", expires: iso(3)}}], {{}});
  console.log(JSON.stringify([
    row.includes("Removed in 3 days") && row.includes('class="btn small keepbtn" data-lib="star"'),
    m.expSoon({{id, expires: iso(20)}}) === "",
    m.expSoon({{id, favorite: true, expires: iso(1)}}) === "",
    m.expSoon({{id, expires: null}}) === "",
  ]));
}});"""
    out = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[true,true,true,true]"
