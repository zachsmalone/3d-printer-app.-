from pathlib import Path
def test_breadcrumb_on_both_pages():
    for p in ("static/index.html", "static/cad.html"):
        assert '/static/crumb.js' in Path(p).read_text()
    js = Path("static/crumb.js").read_text()
    for n in ("Slicer", "Resin", "Lithophane", "Fix", "CAD"): assert '"%s"' % n in js
    assert ".zcrumb" in Path("static/style.css").read_text()
