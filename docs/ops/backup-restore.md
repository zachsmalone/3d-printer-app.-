# Backup and restore

Scope: the community database (`data/zeim.sqlite3`), the auth database (`data/auth.sqlite3`),
the JSON data files (json storage mode / rollback source for db mode), and the per-build
files under `outputs/`.

## What we run

```
# daily (cron, 03:17 local) — on the server:
python -m scripts.backup --data data --out outputs --backup-root backups
```

Each run creates `backups/zeim-YYYYMMDD-HHMMSS/` containing:

| file | what it is |
|---|---|
| `zeim.sqlite3` | live-safe snapshot via SQLite's backup API (correct with WAL) |
| `auth.sqlite3` | same, for passkey/email accounts and sessions |
| `*.json` | the community JSON files |
| `outputs.manifest.json` | every build file with size + sha256 |
| `backup.json` | checksums of everything above (self-verification) |

Retention is automatic: newest 14 daily + 8 weekly (Sunday) backups, older ones removed.

## Encryption at rest and off-site copies

The backup script deliberately stops at the local directory. Two more steps, in order:

```
# 1. encrypt (age, public key in the environment — the server can decrypt, attackers who only
#    get a disk image cannot without the key file):
tar -C backups -c zeim-YYYYMMDD-HHMMSS | age -r age1<public-key> > offsite/zeim-YYYYMMDD.tar.age

# 2. copy off the machine (any of: restic to B2/S3, rclone, borg):
rclone copy offsite/zeim-YYYYMMDD.tar.age b2:zeim-backups/
```

The off-site copy is what makes a ransomware or host-loss event survivable. Local backups alone
do not.

## Restore and verify

```
# restore into a scratch target first — NEVER the live dir without stopping the app:
python -m scripts.restore_verify --backup backups/zeim-YYYYMMDD-HHMMSS --target /tmp/drill-data
```

The script refuses to restore a backup that fails verification (checksums or
`PRAGMA integrity_check`). `--verify-outputs outputs` additionally diffs the live outputs tree
against the manifest.

Real restore, briefly: stop the app → restore DBs + JSON into `data/` → restore build files
from your disk/object snapshot → `verify-outputs` → start the app → smoke test (sign in, list
builds, open a showcase page).

## RTO / RPO

| | target | notes |
|---|---|---|
| RPO | 24 hours | daily backup; build files on the same host share the backup's fate — off-site daily |
| RTO | 2 hours | copy back + restore + verify + restart; practice it, don't estimate it |

## Monthly drill

```
python -m scripts.restore_verify --backup backups/<newest> --target /tmp/drill-$(date +%m)
```

Log the result (date, backup id, pass/fail, time taken). A restore that has never been
practiced is a hypothesis, not a backup.


## Encryption at rest (age) — done in the script, not a manual step

`scripts/backup.py --encrypt-to <AGE_RECIPIENT>` (or env `ZEIM_BACKUP_AGE_RECIPIENT`) replaces
the plaintext backup directory with `zeim-<ts>.tar.age` — an age-encrypted tarball. The plaintext
copy is removed only after the archive exists and is non-empty; if age is missing or fails the
run exits 1 (never a silent plaintext backup). Retention (14 daily + 8 weekly) prunes the
archives the same way it pruned directories.

Key management: `age-keygen` makes the keypair; the PUBLIC key (age1...) goes in the env/cron
on the server, the PRIVATE key file lives ONLY off-site (password manager / offline USB). Restoring:

```
python -m scripts.restore_verify --backup backups/zeim-...tar.age --identity /path/to/age.key --target /tmp/drill
```

Drill expectation: decrypt -> checksums -> DB integrity -> app-readable, same as a plaintext drill.
