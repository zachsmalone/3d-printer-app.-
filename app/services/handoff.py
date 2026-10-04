"""Deep links that open a hosted model file in a desktop slicer."""
from __future__ import annotations

from urllib.parse import quote

# scheme, preferred file format, note
SLICERS = {
    "prusaslicer": ("PrusaSlicer", "prusaslicer://open?file=", "3mf", ""),
    "bambustudio": ("Bambu Studio", "bambustudio://open?file=", "3mf", ""),
    "orcaslicer": ("OrcaSlicer", "orcaslicer://open?file=", "3mf", ""),
    "cura": ("Cura", "cura://open?file=", "stl",
             "Best effort: needs a cura:// URL handler; otherwise download the STL and drag it in."),
}


def links(base_url: str, jid: str, make_token=None) -> list[dict]:
    """`make_token(file_name)` -> a signed token for that one file (None = plain /files/ URL)."""
    out = []
    for key, (label, scheme, fmt, note) in SLICERS.items():
        file_url = (f"{base_url.rstrip('/')}/f/{make_token(f'model.{fmt}')}/{jid}/model.{fmt}" if make_token
                    else f"{base_url.rstrip('/')}/files/{jid}/model.{fmt}")
        out.append({"slicer": key, "label": label, "format": fmt, "file_url": file_url,
                    "url": scheme + quote(file_url, safe=""), "note": note})
    return out
