"""iOS greys out files in the picker when an input's accept list has bare extensions it can't map
to a type (.3mf, .obj, often .stl). Every model file input follows the Slicer's #editFile: no accept
list. The file type is checked by name in JS (where there is a hint) and by content on the server."""
import re
from pathlib import Path

S = Path(__file__).resolve().parents[1] / "static"


def _input(text, iid):
    m = re.search(r'<input[^>]*\bid="%s"[^>]*>' % iid, text)
    assert m, iid
    return m.group(0)


def test_model_inputs_have_no_accept_list():
    for f, iid in [("torchc0.js", "rzFile"), ("cad.html", "cwFile"), ("repair.html", "rpFile"), ("index.html", "editFile")]:
        tag = _input((S / f).read_text(encoding="utf-8"), iid)
        assert 'type="file"' in tag and "accept=" not in tag, (f, tag)


def test_torchc0_still_checks_the_name_in_js():
    assert re.search(r"okType = f => /\\\.\(stl\|3mf\|obj\)", (S / "torchc0.js").read_text(encoding="utf-8"))
