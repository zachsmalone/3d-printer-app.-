# PROPOSAL - ZEIM (photo3d) container image. Build from the repo root:
#   docker build -f reports/deploy/Dockerfile -t zeim:dev .
#
# Debian 13 "trixie" is used on purpose: its prusa-slicer package is 2.9.2 (same as the dev box).
# Debian 12 ships 2.5.x, which may behave differently. Pin by digest before production.
FROM python:3.13-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps:
#  - prusa-slicer      : slicer CLI the app shells out to (app/services/slicer.py looks for "prusa-slicer" on PATH).
#                        It pulls in GUI libs (wxWidgets/GTK), so the layer is large (~1 GB). AGPL: see README.
#  - fonts-dejavu-core : the "add text" edit feature uses DejaVu Sans / Serif / Mono (app/core/meshedit.py).
#  - fonts-dejavu-extra: bold variants.
#  - curl is not installed; the healthcheck uses Python.
# All Python deps (numpy, scipy, trimesh, manifold3d, shapely, rtree, lxml ...) install from binary wheels
# on cp313/manylinux, so no compiler or -dev packages are needed (verified with a clean venv on 3.13).
RUN apt-get update \
 && apt-get install -y --no-install-recommends prusa-slicer fonts-dejavu-core fonts-dejavu-extra tini \
 && rm -rf /var/lib/apt/lists/*

# Non-root user with a fixed uid/gid so bind-mounted host dirs can be chown'ed to 10001:10001.
RUN groupadd --system --gid 10001 zeim \
 && useradd  --system --uid 10001 --gid zeim --home-dir /app --shell /usr/sbin/nologin zeim

WORKDIR /app

# Dependencies first for better layer caching. requirements.txt is unpinned today (open question:
# ask Engineering for a pinned file or lock file so builds are reproducible).
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Application code only (tests/, reports/, data/, outputs/, previews/ are excluded via .dockerignore).
COPY app ./app
COPY static ./static

# State lives OUTSIDE the image. config.py reads PHOTO3D_DATA / PHOTO3D_OUT.
ENV PHOTO3D_DATA=/data \
    PHOTO3D_OUT=/outputs \
    HOME=/tmp \
    PORT=8765
RUN mkdir -p /data /outputs && chown zeim:zeim /data /outputs
VOLUME ["/data", "/outputs"]

USER zeim
EXPOSE 8765

# There is no /healthz yet (Engineering ask #7). "/" serves static/index.html and is cheap.
# Switch to /healthz as soon as it exists.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/', timeout=4).status==200 else 1)"

# ONE worker on purpose: state is JSON files with in-process locks only (no cross-process locking).
# --proxy-headers/--forwarded-allow-ips trust X-Forwarded-* from the Caddy container on the compose network.
ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--workers", "1"]
