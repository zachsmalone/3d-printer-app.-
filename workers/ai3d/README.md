# ZEIM 2D→3D worker (optional)

Turns one photo into a rough 3D figure or bust for the **2D→3D** tab. It is a separate container, so the main ZEIM image stays small. The app also has to set `ZEIM_2D3D_ENABLED=1` or the tab stays hidden and `POST /api/ai3d/jobs` does not run (the default is off). Without the worker, and with the flag on, the tab shows "engine not installed". The rest of ZEIM works as usual.

## Model and licences
- **TripoSR** (Stability AI + Tripo AI). Code: MIT, https://github.com/VAST-AI-Research/TripoSR/blob/main/LICENSE (pinned commit `107cefdc244c39106fa830359024f6a2f1c78871`). Weights: MIT, https://huggingface.co/stabilityai/TripoSR
- Background removal: **rembg** (MIT) with the u2net model.
- Marching cubes: scikit-image (BSD-3), so no CUDA compiler is needed.
- Weights (~1.7 GB + 176 MB) are **not** in the repo. `setup_weights.py` fetches them into the `/data` volume on first start.

## Hardware
- GPU (NVIDIA, about 6 GB of VRAM or more): a few seconds per model.
- CPU only: works. On an 8-core box with no GPU, measured about 28 s for the first figure (including the model load) and 9 s for a bust at resolution 192. Expect slower on smaller CPUs. Needs about 3–4 GB of free RAM.

## Install on Windows (Docker Desktop)
```
docker network create zeim              # once; also attach the ZEIM container to it
docker compose -f workers/ai3d/docker-compose.ai3d.yml up -d --build
```
For an NVIDIA GPU: build with `--build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu121` and uncomment the `deploy:` block in the compose file.

Then set these on the main ZEIM container and restart it:
```
ZEIM_AI3D_URL=http://zeim-ai3d:8765
ZEIM_AI3D_TOKEN=<optional shared secret, same value as on the worker>
```
To check it: `curl http://localhost:8765/health` should return `"ready": true`.

## Limits and quotas (main app)
`ZEIM_AI3D_PRO_ONLY` (off during testing), `ZEIM_AI3D_DAILY_CAP` (5), `ZEIM_AI3D_COOLDOWN_MIN` (5), `ZEIM_AI3D_COOLDOWN_STEP_MIN` (0 = flat 5 min, the default; a value >0 adds that many minutes after each paid model). `ZEIM_TESTING_MODE=1` lifts the pause between models. The daily cap stays unless `ZEIM_TESTING_ALLOW_PAID=1` as well. Neither flag charges a card. Photos are never logged by the worker.
