"""Central paths and limits."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__import__("os").environ.get("PHOTO3D_OUT") or ROOT / "outputs")      # one directory per build (history)
DATA = Path(__import__("os").environ.get("PHOTO3D_DATA") or ROOT / "data")        # settings, users, etc. (never zipped)
STATIC = ROOT / "static"
MAX_BUILDS = 5              # history limit
MAX_UPLOAD = 25 * 1024 * 1024
PREVIEW_RES = 220
for d in (OUT, DATA):  # noqa
    d.mkdir(parents=True, exist_ok=True)

# ---- community / policy constants (single source of truth) ----
MIN_SIGNUP_AGE = 13          # no accounts under 13 (COPPA-style). Under-13s use the education center
                             # without an account, via a teacher's classroom code + nickname only.
ADULT_AGE = 18               # teen (13-17) accounts get safer defaults; teachers must be adults
ADMIN_TOKEN = __import__("os").environ.get("PHOTO3D_ADMIN_TOKEN", "")   # moderation queue access
