"""UX2: too-detailed models get a size message (413), not the 'file type' one; the resin limit message
only mentions hollowing when hollowing was on."""
import pathlib
import pytest
from app.services import uploadgate
from tests.test_uploadsafe import binary_stl


def test_too_many_faces_is_not_called_a_file_type_problem():
    with pytest.raises(uploadgate.GateError) as e:
        uploadgate.gate(binary_stl(faces=50), "ux2-test", max_faces=10)
    assert e.value.status == 413
    msg = str(e.value)
    assert "file type" not in msg and "too much detail" in msg


def test_resin_limit_message_mentions_hollowing_only_when_on():
    src = (pathlib.Path(__file__).resolve().parents[1] / "app/api/resin.py").read_text()
    assert 'if s.get("hollow") else' in src
    assert "Simplify it, or turn hollowing off.\")" not in src
