"""Central paths, limits and policy flags (every flag is env-overridable so a decision can be reversed without a code change)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__import__("os").environ.get("PHOTO3D_OUT") or ROOT / "outputs")      # one directory per build (history)
DATA = Path(__import__("os").environ.get("PHOTO3D_DATA") or ROOT / "data")        # settings, users, etc. (never zipped)
STATIC = ROOT / "static"
STORAGE_MODE = (os.environ.get("ZEIM_STORAGE") or os.environ.get("PHOTO3D_STORAGE") or "json").strip().lower()
if STORAGE_MODE not in {"json", "db"}:
    STORAGE_MODE = "json"
# ZEIM Originals: 378 MB, not in git. Deploys must ship library/originals separately (or point PHOTO3D_ORIGINALS at it).
ORIGINALS = Path(os.environ.get("PHOTO3D_ORIGINALS", str(ROOT / "library" / "originals")))
MAX_BUILDS = int(__import__("os").environ.get("PHOTO3D_MAX_BUILDS", "20"))   # builds kept per person (oldest un-starred roll off; starred ones never do)
KEEP_UNSAVED_DAYS = int(__import__("os").environ.get("PHOTO3D_KEEP_UNSAVED_DAYS", "30"))   # ordinary builds: 30 days (launch checklist policy)
PENDING_MAX_AGE_DAYS = int(__import__("os").environ.get("PHOTO3D_PENDING_MAX_AGE_DAYS", "7"))  # parked (scanner-down) uploads are transient
KEEP_SAVED_DAYS = int(__import__("os").environ.get("PHOTO3D_KEEP_SAVED_DAYS", "30"))       # builds shared to the Showcase
DISK_MIN_FREE_MB = int(__import__("os").environ.get("PHOTO3D_DISK_MIN_FREE_MB", "500"))    # below this, new builds first trigger a sweep, then are refused
DISK_TARGET_FREE_MB = int(__import__("os").environ.get("PHOTO3D_DISK_TARGET_FREE_MB", "1000"))
MAX_UPLOAD = 25 * 1024 * 1024
PREVIEW_RES = 220
for d in (OUT, DATA):  # noqa
    d.mkdir(parents=True, exist_ok=True)


def harden_data_permissions() -> int:
    """Data directories 700 and data files 600 (accounts and printer settings must not be world-readable). Returns how many were changed."""
    import os
    n = 0
    for d in (OUT, DATA):
        try:
            if (d.stat().st_mode & 0o777) != 0o700:
                os.chmod(d, 0o700); n += 1
        except OSError:
            pass
    try:
        for f in DATA.iterdir():
            if f.is_file() and (f.stat().st_mode & 0o077):
                os.chmod(f, 0o600); n += 1
    except OSError:
        pass
    return n


harden_data_permissions()

# ---- community / policy constants (single source of truth) ----
# First-visit 18+ confirmation for every visitor. Test-only switch: PHOTO3D_AGE_GATE=0 (tests/conftest.py) skips it so
# automated UI tests are not stopped by the overlay. Never turn it off in production.
AGE_GATE = os.environ.get("PHOTO3D_AGE_GATE", "1") != "0"
MIN_SIGNUP_AGE = 18          # ZEIM accounts are 18+ only (owner decision 2026-10-12).
USERNAME_CHANGE_DAYS = int(os.environ.get("PHOTO3D_USERNAME_CHANGE_DAYS", "90"))      # one username change per this many days
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
#   signed-out and suspended sessions never get either.
# "local": one person on their own machine; behaves as before. ./run.sh sets this unless you override it.
MODE = (os.environ.get("PHOTO3D_MODE") or "shared").strip().lower()
if MODE not in ("shared", "local"):
    MODE = "shared"
# The URL put in join QR codes and slicer links. If set here, nobody can change it from the UI.
# Theft protection: hold a Showcase upload for a moderator when its geometry matches another maker's model (on by default)
DUPLICATE_CHECK = os.environ.get("PHOTO3D_DUPLICATE_CHECK", "1").strip().lower() not in ("0", "false", "no", "off")
PUBLIC_BASE_URL = (os.environ.get("PHOTO3D_PUBLIC_BASE_URL") or "").strip().rstrip("/")

# ---- Education CR-10 / Yami's decisions (2026-10-04) - reversible flags ----
# Likes need a signed-in account. Default OFF *until real authentication exists* (today an "account" is just a
# cookie-bound display name + date of birth, so requiring it would add friction without adding trust).
LIKES_REQUIRE_ACCOUNT = _flag("PHOTO3D_LIKES_REQUIRE_ACCOUNT", False)
LIKE_LIMIT_PER_HOUR = _int("PHOTO3D_LIKE_LIMIT_PER_HOUR", 30)        # per browser session
LIKE_LIMIT_PER_HOUR_IP = _int("PHOTO3D_LIKE_LIMIT_PER_HOUR_IP", 300)  # per network address (a whole household or library may share one)
SHOW_COUNTS_FOR_EXAMPLES = _flag("PHOTO3D_SHOW_COUNTS_FOR_EXAMPLES", False)   # invented numbers on EXAMPLE items

# ---- Education CR-5 ----
PHOTO_ACK_REQUIRED = _flag("PHOTO3D_PHOTO_ACK_REQUIRED", True)       # "I have permission" box before uploading a photo

# ---- Education CR-11 / CR-15: abuse limits ----
REPORT_LIMIT_PER_MIN = _int("PHOTO3D_REPORT_LIMIT_PER_MIN", 10)      # per browser session
REPORT_LIMIT_PER_MIN_IP = _int("PHOTO3D_REPORT_LIMIT_PER_MIN_IP", 60)
RECOVERY_FAIL_LIMIT = _int("PHOTO3D_RECOVERY_FAIL_LIMIT", 5)         # wrong recovery codes per 10 min (session and address)
SEAT_RESET_HOURS = _int("PHOTO3D_SEAT_RESET_HOURS", 24)

# ---- age gate (Safety S-04) ----
# SEND-3: the "Share..." / "Email it to myself" rows stay OFF until the share-sheet spike (/sharetest, SEND-0) has passed on a real iPhone/iPad.
SEND_SHARE_UI = _flag("PHOTO3D_SEND_SHARE", False)
# The 18+ check is limited PER BROWSER (session + marker cookie): after an under-18 result that browser can't retry for AGE_LOCK_HOURS.
# The network address only gets a SOFT limit, so one person can never lock out a whole home, office or library:
# it is locked only after MORE than AGE_IP_LOCK_AFTER refusals within AGE_IP_LOCK_MINUTES, and only for that short window. 0 = off.
AGE_IP_LOCK_AFTER = _int("PHOTO3D_AGE_IP_LOCK_AFTER", 10)
AGE_IP_LOCK_MINUTES = _int("PHOTO3D_AGE_IP_LOCK_MINUTES", 15)
AGE_LOCK_HOURS = _int("PHOTO3D_AGE_LOCK_HOURS", 24)
SIGNUP_ATTEMPTS_PER_HOUR_IP = _int("PHOTO3D_SIGNUP_ATTEMPTS_PER_HOUR_IP", 30)

# ---- network binding ----
# Used by run.sh and `python -m app.serve`. Default = this computer only. 0.0.0.0 is opt-in and logs a warning at start-up.
HOST = (os.environ.get("HOST") or "127.0.0.1").strip()
PORT = _int("PORT", 8765)
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
# "local" mode only trusts a request that really comes from this computer: peer address AND Host header are loopback and there
# are no proxy/tunnel headers. Anything else (a tunnel, a LAN visitor) is treated like shared mode.
LOCAL_CLIENTS = ("127.0.0.1", "::1", "localhost")
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
ADMIN_FAIL_LIMIT = _int("PHOTO3D_ADMIN_FAIL_LIMIT", 10)       # wrong admin tokens per 10 min per address, then 429 (even for the right one)

# ---- web hardening (Safety re-check 1) ----
BLOCK_PRIVATE_PRINTERS = _flag("PHOTO3D_BLOCK_PRIVATE_PRINTERS", False)   # hosted deployments: refuse printer URLs on loopback/private networks (SSRF)
# Shared mode: allow printer addresses in private LAN ranges (self-hosted on the printer's LAN). Loopback and
# link-local stay blocked. Local mode never restricts printer addresses (app/services/netguard.py).
LAN_PRINTERS = _flag("PHOTO3D_LAN_PRINTERS", False)
API_DOCS = _flag("PHOTO3D_API_DOCS", False)            # /docs, /redoc, /openapi.json are off unless asked for (they list every route)
COOKIE_SECURE = (os.environ.get("PHOTO3D_COOKIE_SECURE") or "auto").strip().lower()   # auto = Secure when the request arrived over https

# ---- upload gate (app/services/uploadgate.py) ----
# Per-account upload limit per hour (0 = off). Enforced at /api/generate; the counter is
# SQLite-backed in db mode (shared by all workers) and in-process in json mode.
UPLOADS_PER_HOUR = _int("PHOTO3D_UPLOADS_PER_HOUR", 10)
EDIT_UPLOADS_PER_HOUR = _int("PHOTO3D_EDIT_UPLOADS_PER_HOUR", 120)   # editor / CAD mesh imports (own budget)
# Optional local malware scan of uploads via clamd (INSTREAM). Nothing is ever sent anywhere
# else; if clamd is unreachable, uploads are allowed and the miss is logged.
CLAMAV = _flag("PHOTO3D_CLAMAV", False)
CLAMAV_SOCKET = (os.environ.get("PHOTO3D_CLAMAV_SOCKET") or "/var/run/clamav/clamd.ctl").strip()
