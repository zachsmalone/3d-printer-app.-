"""Central paths, limits and policy flags (every flag is env-overridable so a decision can be reversed without a code change)."""
import os
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


def _flag(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None or v.strip() == "" else v.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


# ---- deployment mode (Education CR-1) ----
# "shared" (DEFAULT): a server other people use. Server-wide settings (printers, public base URL, linked accounts)
#   need the admin token (X-Admin-Token); sending to a printer needs an adult account or the admin token;
#   class-student sessions never get either.
# "local": one person on their own machine; behaves as before. ./run.sh sets this unless you override it.
MODE = (os.environ.get("PHOTO3D_MODE") or "shared").strip().lower()
if MODE not in ("shared", "local"):
    MODE = "shared"
# The URL put in join QR codes and slicer links. If set here, nobody can change it from the UI.
PUBLIC_BASE_URL = (os.environ.get("PHOTO3D_PUBLIC_BASE_URL") or "").strip().rstrip("/")

# ---- Education CR-10 / Yami's decisions (2026-10-04) - reversible flags ----
# Likes need a signed-in account. Default OFF *until real authentication exists* (today an "account" is just a
# cookie-bound display name + date of birth, so requiring it would add friction without adding trust).
LIKES_REQUIRE_ACCOUNT = _flag("PHOTO3D_LIKES_REQUIRE_ACCOUNT", False)
LIKE_LIMIT_PER_HOUR = _int("PHOTO3D_LIKE_LIMIT_PER_HOUR", 30)        # per browser session
LIKE_LIMIT_PER_HOUR_IP = _int("PHOTO3D_LIKE_LIMIT_PER_HOUR_IP", 300)  # per network address (a whole school may share one)
SHOW_COUNTS_FOR_EXAMPLES = _flag("PHOTO3D_SHOW_COUNTS_FOR_EXAMPLES", False)   # invented numbers on EXAMPLE items
TEEN_PUBLIC_ENABLED = _flag("PHOTO3D_TEEN_PUBLIC_ENABLED", False)    # accounts 13-17 may publish Public
HIDE_COUNTS_FOR_MINORS = _flag("PHOTO3D_HIDE_COUNTS_FOR_MINORS", True)  # no like/download numbers on under-18 creators' items

# ---- Education CR-5 ----
PHOTO_ACK_REQUIRED = _flag("PHOTO3D_PHOTO_ACK_REQUIRED", True)       # "I have permission" box before uploading a photo

# ---- Education CR-11 / CR-15: abuse limits ----
REPORT_LIMIT_PER_MIN = _int("PHOTO3D_REPORT_LIMIT_PER_MIN", 10)      # per browser session
REPORT_LIMIT_PER_MIN_IP = _int("PHOTO3D_REPORT_LIMIT_PER_MIN_IP", 60)
RECOVERY_FAIL_LIMIT = _int("PHOTO3D_RECOVERY_FAIL_LIMIT", 5)         # wrong recovery codes per 10 min (session and address)
SEAT_RESET_HOURS = _int("PHOTO3D_SEAT_RESET_HOURS", 24)
