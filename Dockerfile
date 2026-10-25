# ZEIM (photo3d) container image. Build from the repo root:
#   docker build -t zeim:dev .
# NOTE (Engineering): this file has NOT been built in CI or on the dev box yet (no docker available there). Treat as
# reviewed-but-unbuilt until Ops runs the first build.
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
#                        It pulls in GUI libs (wxWidgets/GTK), so the layer is large (~1 GB). AGPL: unmodified, CLI only, see docs/licensing.md.
#  - fonts-dejavu-core : the "add text" edit feature uses DejaVu Sans / Serif / Mono (app/core/meshedit.py).
#  - fonts-dejavu-extra: bold variants.
#  - curl is not installed; the healthcheck uses Python.
# pillow-heif (iPhone HEIC photos) ships a manylinux wheel with libheif bundled, so no extra apt package is needed on this glibc base.
#   (On Alpine/musl you would need libheif-dev - not supported here.)
# All Python deps (numpy, scipy, trimesh, manifold3d, shapely, rtree, lxml ...) install from binary wheels
# on cp313/manylinux, so no compiler or -dev packages are needed (verified with a clean venv on 3.13).
RUN apt-get update \
 && apt-get install -y --no-install-recommends prusa-slicer fonts-dejavu-core fonts-dejavu-extra tini \
 && rm -rf /var/lib/apt/lists/*

# Non-root user with a fixed uid/gid so bind-mounted host dirs can be chown'ed to 10001:10001.
RUN groupadd --system --gid 10001 zeim \
 && useradd  --system --uid 10001 --gid zeim --home-dir /app --shell /usr/sbin/nologin zeim

WORKDIR /app

# Dependencies first for better layer caching. requirements.txt pins direct deps, constraints.txt pins the whole tree.
COPY requirements.txt constraints.txt ./
RUN pip install -r requirements.txt -c constraints.txt

# Application code, plus the repo's read-only catalogs. tests/, reports/, outputs/, previews/,
# and runtime files under data/ (accounts, uploads, keys) stay out via .dockerignore.
# Modules load catalogs with Path(__file__).parents[2] / "data" / ..., which is /app/data here.
# PHOTO3D_DATA=/data is user state and is a different tree. Do not copy that volume into the image.
COPY app ./app
COPY static ./static
COPY data ./data

# State lives OUTSIDE the image. config.py reads PHOTO3D_DATA / PHOTO3D_OUT.
ENV PHOTO3D_DATA=/data \
    PHOTO3D_OUT=/outputs \
    HOME=/tmp \
    PORT=8765
RUN mkdir -p /data /outputs && chown -R zeim:zeim /data /outputs /app/data
VOLUME ["/data", "/outputs"]

USER zeim
EXPOSE 8765

# /healthz: no auth, no data, no session cookie needed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=4).status==200 else 1)"

# ONE worker on purpose: state is JSON files with in-process locks only (no cross-process locking).
# --proxy-headers/--forwarded-allow-ips trust X-Forwarded-* from the Caddy container on the compose network.
ENTRYPOINT ["tini", "--"]
# HOST=0.0.0.0 is deliberate here: inside the container the app must be reachable by the proxy on the compose network;
# it is NOT published to the host (compose uses `expose`). The app logs a "no real authentication yet" warning at start-up.
# FORWARDED_ALLOW_IPS="*" trusts X-Forwarded-* from the proxy container on the private compose network only.
ENV HOST=0.0.0.0 FORWARDED_ALLOW_IPS="*"
CMD ["python", "-m", "app.serve"]
