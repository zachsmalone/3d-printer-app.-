"""Delete one account's data (documented underage-account process). Dry run unless --confirm.
    python tools/delete_user_data.py <account id> [--confirm]
Run from the repo root with the same PHOTO3D_* environment as the server. See README "Underage accounts"."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.community import erase  # noqa: E402

if len(sys.argv) < 2:
    sys.exit(__doc__)
uid, go = sys.argv[1], "--confirm" in sys.argv[2:]
r = erase.erase(uid) if go else erase.plan(uid)
if r is None:
    sys.exit(f"no account with id {uid}")
print(("DELETED " if go else "DRY RUN (add --confirm to delete): ") + json.dumps(r))
