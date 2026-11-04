# FEAT1 failure doctor — planning only (nothing built)

Goal: from an uploaded print photo plus the existing checkbox answers, suggest the likely failure (stringing, warping,
layer shift, under-extrusion, spaghetti, elephant foot...) and one fix. Box: e2-highmem-2 (2 vCPU, 16 GB, no GPU).

| Option | Licence | CPU cost on 2 vCPU | Privacy |
|---|---|---|---|
| A. Rules on the checkbox answers only (no image model) | ours | ~0 | photo not analysed |
| B. Small zero-shot image model, e.g. OpenCLIP ViT-B/32 | MIT code; check weight licence (LAION-trained) | estimate 0.5–2 s per photo, ~0.6 GB RAM; must be measured | stays on our server |
| C. Fine-tuned small classifier (e.g. MobileNetV3/EfficientNet-B0 on a print-failure dataset) | Apache-2.0 models; dataset licence must allow commercial use (many Roboflow/Kaggle sets are CC BY or NC — check each) | estimate <0.5 s per photo | stays on our server |
| D. Hosted vision API (e.g. Workers AI, others) | provider terms | none locally | photo leaves ZEIM; privacy page change + opt-in needed |

Numbers in the CPU column are estimates, not measurements. Measure before choosing.

Suggested path: ship A first (honest, instant), then trial B on prod-like hardware behind a flag, run in the off-peak/
low-priority thread pool with one job at a time and a queue, so slicing is never starved. Show results as "possible
causes", never as a certain diagnosis. Keep the NSFW blur and content filter in front of any image analysis. Don't keep
photos longer than the existing retention.
