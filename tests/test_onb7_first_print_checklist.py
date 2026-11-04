"""ONB7: first-print checklist under each FDM slice result (client-only, nothing stored)."""
from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / "static" / "printer.js").read_text()


def test_checklist_rendered_after_slice_and_remembers_close_only():
    assert "${firstPrintChecklistHTML(r.settings.material)}" in JS
    fn = JS[JS.index("function firstPrintChecklistHTML"):]
    fn = fn[:fn.index("\n}\n")]
    assert 'id="fpCheck"' in fn and "zeim.fpcheck.closed" in fn
    assert "api(" not in fn and "fetch(" not in fn          # nothing is sent
    assert "level" in fn and "first layer" in fn
