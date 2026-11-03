"""PERF1: large photos are shrunk client-side before upload; failures fall back to the original file."""
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "static" / "photo.js").read_text()


def test_give_downscales_before_handing_off():
    assert "onFile(await downscale(f))" in SRC


def test_downscale_is_bounded_and_safe():
    assert "MAX_SIDE = 3000" in SRC and "SHRINK_OVER" in SRC
    assert "image\\/(jpeg|png|webp)" in SRC        # HEIC and others pass through untouched
    assert "catch { return f; }" in SRC            # any failure sends the original
    assert "b.size >= f.size) return f" in SRC     # never upload something bigger
