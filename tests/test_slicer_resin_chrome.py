"""Slicer bed chrome follows My printer. Resin hides the FDM label and process tools."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
KIND = (ROOT / "static" / "printkind.js").read_text(encoding="utf-8")


def _between(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def _tag(html, id_):
    m = re.search(rf"<[^>]*\bid=\"{re.escape(id_)}\"[^>]*>", html)
    assert m, id_
    return m.group(0)


def test_resin_kind_hides_fdm_only_slicer_chrome():
    assert "body:not([data-print-kind=resin]) [data-kind-only=resin],body[data-print-kind=resin] [data-kind-only=fdm]{display:none !important}" in CSS
    edit = _between(HTML, 'id="viewEdit"', 'id="dlgPrint"')
    head = _between(edit, 'class="bed-head', 'id="editSide"')
    assert 'class="bed-name" data-kind-only="fdm">FDM</span>' in head
    assert 'class="bed-name" data-kind-only="resin">Resin</span>' in head
    assert head.count(">FDM<") == 1
    bar = _between(edit, 'id="slicerBar"', 'id="fdmDone"')
    for id_ in ("bedFilament", "slicerSlice", "slicerPreview"):
        assert 'data-kind-only="fdm"' in _tag(bar, id_)
    assert 'data-bed-cat="process"' in bar and 'data-kind-only="fdm">Process</button>' in bar
    proc = _between(bar, 'data-for="process"', 'data-for="transform"')
    assert 'data-kind-only="fdm"' in proc.split(">", 1)[0]
    for label in ("Quality", "Strength", "Speed", "Cooling", "Support", "Infill", "Adhesion"):
        assert f'data-kind-only="fdm">{label}</button>' in proc
    assert 'data-for="filament"' in bar and 'data-kind-only="fdm"' in _between(bar, 'data-for="filament"', 'data-for="process"').split(">", 1)[0]
    sheet = _tag(edit, "processSheet")
    assert 'data-kind-only="fdm"' in sheet
    assert 'id="procHint"' in edit and 'data-kind-only="fdm"' in _tag(edit, "procHint")


def test_resin_keeps_import_repair_transform_and_offers_torchc0():
    edit = _between(HTML, 'id="viewEdit"', 'id="dlgPrint"')
    bar = _between(edit, 'id="slicerBar"', 'id="bedTools"')
    for token in (
        'data-bed-label="Printer"',
        'data-bed-label="Transform"',
        'data-bed-label="Import"',
        'id="slicerRepair"',
        'id="slicerSend"',
    ):
        assert token in bar
    for id_ in ("bedDevice", "slicerRepair", "slicerSend"):
        assert "data-kind-only" not in _tag(bar, id_)
    transform = bar.split('data-bed-cat="transform"', 1)[1].split(">", 1)[0]
    assert "data-kind-only" not in transform
    imported = bar.split('data-bed-cat="import"', 1)[1].split(">", 1)[0]
    assert "data-kind-only" not in imported
    torch = _tag(bar, "slicerTorch")
    assert 'href="#torchc0"' in torch and 'data-kind-only="resin"' in torch
    assert "Open in Resin (TorchC0)" in bar


def test_kind_paint_drops_fdm_drill_in_and_restores_it():
    apply = KIND.split("function apply()", 1)[1].split("function note()", 1)[0]
    assert "paintSlicerChrome()" in apply
    assert "document.body.dataset.printKind = kind" in apply
    paint = KIND.split("function paintSlicerChrome()", 1)[1].split("function apply()", 1)[0]
    assert 'cat === "filament" || cat === "process"' in paint
    assert 'catNow === "filament" || catNow === "process"' in paint
    assert "cats.hidden = false" in paint
    assert "tools.hidden = true" in paint
    assert 'title.textContent = resin ? "Slicer" : "FDM Slicer"' in paint
    assert "hold.drill" in paint and "pin.dataset.cat = hold.drill.cat" in paint
    assert "support-live" in paint and "paint-ready" in paint
