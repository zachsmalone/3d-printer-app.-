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


def links(base_url: str, jid: str, token: str = "") -> list[dict]:
    out = []
    for key, (label, scheme, fmt, note) in SLICERS.items():
        file_url = (f"{base_url.rstrip('/')}/f/{token}/{jid}/model.{fmt}" if token
                    else f"{base_url.rstrip('/')}/files/{jid}/model.{fmt}")
        out.append({"slicer": key, "label": label, "format": fmt, "file_url": file_url,
                    "url": scheme + quote(file_url, safe=""), "note": note})
    return out
