# ZEIM 2D->3D engine (optional). Build:  docker build -t zeim-ai3d workers/ai3d
# GPU build: docker build --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu121 -t zeim-ai3d workers/ai3d
FROM python:3.11-slim
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN apt-get update && apt-get install -y --no-install-recommends git libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /worker
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url ${TORCH_INDEX} && pip install --no-cache-dir -r requirements.txt
COPY server.py setup_weights.py prep.py ./
# Weights live in a volume (/data), fetched on first start, never baked into an image.
ENV ZEIM_AI3D_CODE=/data/TripoSR ZEIM_AI3D_WEIGHTS=/data/weights U2NET_HOME=/data/u2net HF_HOME=/data/hf
VOLUME /data
EXPOSE 8765
CMD ["sh", "-c", "python setup_weights.py && python server.py"]
