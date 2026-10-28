"""ZEIM 2D->3D engine: a small, separate worker around TripoSR (MIT code + MIT weights, Stability AI / Tripo AI).

Runs on its own (Docker service or plain Python), never inside the main ZEIM image. GPU (CUDA) when available, CPU otherwise.
No network calls at request time: the weights are fetched once by setup_weights.py. Photos are processed in memory and never
written to disk or logged.

  GET  /health    -> {"ok": true, "engine": "TripoSR", "device": "cpu"|"cuda", "ready": bool}
  POST /generate  body = image bytes (PNG/JPEG), header X-Mode: figure|bust, X-Resolution: 96..320  -> binary PLY mesh

Listens on ZEIM_AI3D_HOST:ZEIM_AI3D_PORT (default 0.0.0.0:8765). Only ZEIM should be able to reach it (keep it on the
Docker network, do not publish the port to the internet). Optional shared secret: ZEIM_AI3D_TOKEN (header X-Token).
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from prep import prepare_image
CODE = os.environ.get("ZEIM_AI3D_CODE", os.path.join(HERE, "TripoSR"))
WEIGHTS = os.environ.get("ZEIM_AI3D_WEIGHTS", os.path.join(HERE, "weights"))
TOKEN = os.environ.get("ZEIM_AI3D_TOKEN", "")
MAX_BODY = 25 * 1024 * 1024
_lock = threading.Lock()          # one generation at a time: CPU and small GPUs cannot run two
_model = None
_device = "cpu"


def _shim_marching_cubes():
    """TripoSR imports torchmcubes (needs a C++/CUDA build). scikit-image does the same job on CPU with no compiler."""
    if "torchmcubes" in sys.modules:
        return
    try:
        import torchmcubes  # noqa: F401  (use the real one when it is installed)
        return
    except ImportError:
        pass
    import torch
    from skimage import measure
    mod = types.ModuleType("torchmcubes")

    def marching_cubes(vol, level):
        v, f, _, _ = measure.marching_cubes(vol.detach().cpu().numpy(), level)
        v = v[:, ::-1].copy()     # torchmcubes returns (x, y, z) = (axis2, axis1, axis0)
        return torch.from_numpy(v.astype(np.float32)), torch.from_numpy(f[:, ::-1].astype(np.int64).copy())
    mod.marching_cubes = marching_cubes
    sys.modules["torchmcubes"] = mod


def load():
    global _model, _device
    if _model is not None:
        return _model
    import torch
    _shim_marching_cubes()
    sys.path.insert(0, CODE)
    from tsr.system import TSR
    _device = "cuda" if torch.cuda.is_available() and os.environ.get("ZEIM_AI3D_DEVICE", "auto") != "cpu" else "cpu"
    if _device == "cpu":
        torch.set_num_threads(max(1, int(os.environ.get("ZEIM_AI3D_THREADS", os.cpu_count() or 4))))
    m = TSR.from_pretrained(WEIGHTS, config_name="config.yaml", weight_name="model.ckpt")
    m.renderer.set_chunk_size(8192 if _device == "cpu" else 131072)
    _model = m.to(_device)
    return _model


def ready() -> bool:
    return os.path.isfile(os.path.join(WEIGHTS, "model.ckpt")) and os.path.isdir(os.path.join(CODE, "tsr"))


def _cutout_alpha(im: Image.Image):
    """rembg when it is installed. None lets prep fall back to a border-colour mask."""
    try:
        import rembg
    except ImportError:
        return None
    cut = rembg.remove(im, session=_session())
    arr = np.asarray(cut)
    if arr.ndim != 3 or arr.shape[-1] != 4:
        return None
    return arr[..., 3]


def prepare(data: bytes, mode: str, *, crop: bool = True, tone: bool = True, grey: bool = True, prepared: bool = False):
    """Photo TripoSR should see, at 512 px.

    prepared=True: ZEIM already cropped and toned this photo. Do not cut or crop it again.
    Otherwise: the shared prep (crop, light, grey), using rembg for the cut-out when it imports.
    """
    if prepared:
        im = Image.open(io.BytesIO(data)).convert("RGB")
        return im.resize((512, 512), Image.Resampling.LANCZOS), []
    png, notes = prepare_image(data, mode, crop=crop, tone=tone, grey=grey, alpha_fn=_cutout_alpha)
    im = Image.open(io.BytesIO(png)).convert("RGB").resize((512, 512), Image.Resampling.LANCZOS)
    return im, notes


_rs = None


def _session():
    global _rs
    if _rs is None:
        import rembg
        _rs = rembg.new_session("u2net")
    return _rs


def generate(data: bytes, mode: str, res: int, *, crop: bool = True, tone: bool = True, grey: bool = True, prepared: bool = False) -> bytes:
    import torch
    img, _notes = prepare(data, mode, crop=crop, tone=tone, grey=grey, prepared=prepared)
    with _lock:
        m = load()
        with torch.no_grad():
            codes = m([img], device=_device)
        mesh = m.extract_mesh(codes, False, resolution=res)[0]
    # TripoSR is Y-up-ish with the camera on +X; ZEIM prints Z-up. Rotate so the subject stands on the bed.
    import trimesh
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1]))
    return mesh.export(file_type="ply")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):        # never log request details (photos stay private)
        pass

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _auth(self):
        return not TOKEN or self.headers.get("X-Token") == TOKEN

    def do_GET(self):
        if self.path != "/health":
            return self._json(404, {"error": "not found"})
        try:
            import torch
            dev = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            dev = "unknown"
        self._json(200, {"ok": True, "engine": "TripoSR", "device": dev, "ready": ready(), "busy": _lock.locked()})

    def do_POST(self):
        if self.path not in ("/generate", "/prepare") or not self._auth():
            return self._json(404 if self.path not in ("/generate", "/prepare") else 403, {"error": "no"})
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY:
            return self._json(413, {"error": "The photo is too large."})
        data = self.rfile.read(n)
        mode = "bust" if self.headers.get("X-Mode") == "bust" else "figure"
        crop = self.headers.get("X-Prep-Crop", "1") != "0"
        tone = self.headers.get("X-Prep-Tone", "1") != "0"
        grey = self.headers.get("X-Prep-Bg", "grey") != "keep"
        prepared = self.headers.get("X-Prepared") == "1"
        if self.path == "/prepare":
            try:
                _im, notes = prepare(data, mode, crop=crop, tone=tone, grey=grey, prepared=False)
                buf = io.BytesIO()
                _im.save(buf, format="PNG")
            except ValueError as e:
                return self._json(422, {"error": str(e)})
            except Exception as e:
                return self._json(500, {"error": "The engine could not prepare this photo.", "kind": type(e).__name__})
            return self._json(200, {"ok": True, "png_b64": base64.b64encode(buf.getvalue()).decode(), "notes": notes})
        res = max(96, min(320, int(self.headers.get("X-Resolution") or 192)))
        try:
            out = generate(data, mode, res, crop=crop, tone=tone, grey=grey, prepared=prepared)
        except ValueError as e:
            return self._json(422, {"error": str(e)})
        except Exception as e:     # message only, no photo data
            return self._json(500, {"error": "The engine could not make a model from this photo.", "kind": type(e).__name__})
        self.send_response(200); self.send_header("Content-Type", "application/octet-stream"); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)


if __name__ == "__main__":
    if not ready():
        print("Weights not found. Run: python setup_weights.py", file=sys.stderr)
    host, port = os.environ.get("ZEIM_AI3D_HOST", "0.0.0.0"), int(os.environ.get("ZEIM_AI3D_PORT", "8765"))
    ThreadingHTTPServer((host, port), H).serve_forever()
