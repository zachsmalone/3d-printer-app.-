"""Fetch the TripoSR code (pinned commit) and weights (~1.7 GB, Hugging Face stabilityai/TripoSR, MIT) for the ZEIM 2D->3D worker.
Run once at worker setup. Nothing is stored in the ZEIM repository.   python setup_weights.py [--code DIR] [--weights DIR]"""
import argparse, os, subprocess, sys

REPO = "https://github.com/VAST-AI-Research/TripoSR.git"
COMMIT = "107cefdc244c39106fa830359024f6a2f1c78871"
HF_REPO = "stabilityai/TripoSR"
HERE = os.path.dirname(os.path.abspath(__file__))

p = argparse.ArgumentParser()
p.add_argument("--code", default=os.environ.get("ZEIM_AI3D_CODE", os.path.join(HERE, "TripoSR")))
p.add_argument("--weights", default=os.environ.get("ZEIM_AI3D_WEIGHTS", os.path.join(HERE, "weights")))
a = p.parse_args()
if not os.path.isdir(os.path.join(a.code, "tsr")):
    subprocess.check_call(["git", "clone", "--quiet", REPO, a.code])
    subprocess.check_call(["git", "-C", a.code, "checkout", "--quiet", COMMIT])
from huggingface_hub import hf_hub_download
for f in ("config.yaml", "model.ckpt"):
    hf_hub_download(HF_REPO, f, local_dir=a.weights)
import rembg
rembg.new_session("u2net")          # background-removal model (~170 MB) into the rembg cache
print("ZEIM 2D->3D engine ready:", a.code, a.weights)
