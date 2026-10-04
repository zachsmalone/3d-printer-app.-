# ZEIM deployment proposals (DRAFT, by Ren / DevOps)

Everything here is a **proposal**: nothing has been built, deployed, or pushed. No app code was changed.
Validated so far: `bash -n` on both scripts, `docker compose config` (v5.6), `caddy validate` (v2.11) and a local
backup, restore-drill, retention and checksum-failure test on a fake tree (incl. a WAL-mode SQLite DB).
**Not** validated: `docker build` and a real boot of the container (no Docker daemon on the dev box).

| File | Purpose |
|---|---|
| `Dockerfile` | Python 3.13 on Debian trixie, `prusa-slicer` 2.9.2, DejaVu fonts, non-root uid 10001, tini, healthcheck, single uvicorn worker |
| `docker-compose.yml` | `app` (internal port 8765 only) + `caddy` (80/443); bind-mounted `data/` and `outputs/`; read-only rootfs, caps dropped, mem/CPU limits |
| `Caddyfile` | Automatic HTTPS, 55 MB body cap, gzip/zstd, security headers, CSP in **report-only** mode, 660 s proxy timeout for slicing |
| `backup.sh` | Archives `data/` + `outputs/`, safe SQLite copies (`.backup`), sha256 sums, 14 daily + 8 weekly retention, optional `age` encryption and `rclone` off-site copy |
| `restore.sh` | Verifies checksums, extracts to a scratch dir (the **restore drill**), `--apply` swaps it in and keeps the old dirs as `*.pre-restore-<ts>` |
| `../../.env.example`, `../../.dockerignore` | Config template and a build context that excludes data, keys, tests, reports |

## Usage

```bash
# on the VPS, from the repo root
cp .env.example .env && chmod 600 .env     # set ZEIM_DOMAIN, ACME_EMAIL, PHOTO3D_ADMIN_TOKEN, PHOTO3D_SECRET_KEY
sudo install -d -o 10001 -g 10001 -m 750 /srv/zeim/data /srv/zeim/outputs
docker compose -f reports/deploy/docker-compose.yml --env-file .env up -d --build
docker compose -f reports/deploy/docker-compose.yml ps        # app should become "healthy"
```

First test with Let's Encrypt **staging** (uncomment `acme_ca` in the Caddyfile) to avoid rate limits.

Backups (host cron, as a user that can read `/srv/zeim`):

```bash
15 3 * * *  ZEIM_HOST_DIR=/srv/zeim BACKUP_DIR=/srv/zeim-backups AGE_RECIPIENT=age1... RCLONE_REMOTE=b2:zeim-backups \
            /opt/zeim/reports/deploy/backup.sh >> /var/log/zeim-backup.log 2>&1
```

Restore drill (do before launch, then quarterly):

```bash
reports/deploy/restore.sh /srv/zeim-backups/daily/zeim-<stamp>            # verify + extract to /tmp, touches nothing live
docker compose -f reports/deploy/docker-compose.yml stop app
reports/deploy/restore.sh /srv/zeim-backups/daily/zeim-<stamp> --apply    # swap in; old dirs kept
docker compose -f reports/deploy/docker-compose.yml start app
```

## Assumptions

- Single VPS (Option A), >= 2 vCPU / 4 GB RAM; app limited to 3 GB / 2 CPUs so Caddy and the OS keep headroom.
- **One uvicorn worker only.** State is JSON files guarded by in-process locks; two workers could corrupt them.
- State dirs come from the existing env vars `PHOTO3D_DATA` and `PHOTO3D_OUT` (`app/config.py`), pointed at `/data` and `/outputs`.
- The app has **no SQLite today**. `backup.sh` detects any SQLite file under `data/` and copies it with the backup API
  (`sqlite3 .backup`, or Python's `sqlite3` module if the CLI is missing), then runs `integrity_check`. Once Engineering moves to
  SQLite (WAL) this is already handled; if they pick Postgres, replace that step with `pg_dump`.
- JSON files are not written atomically by the app, so a backup could in rare cases catch one mid-write. `restore.sh` rejects
  JSON that does not parse; nightly timing (03:15) makes this unlikely. Atomic writes (temp file + rename) would remove the risk.
- Backups include secrets (`link.key`, `secret.key`, plain-text printer API keys in `settings.json`). Encrypt before off-site (`AGE_RECIPIENT`).
- Signed download links use `public_base_url` from settings, falling back to the request URL. Behind Caddy, uvicorn `--proxy-headers` makes that `https://<domain>`; still set `public_base_url` in Settings after launch.

## Open questions

1. **Hosting/region and domain** (Zach): placeholders `zeim.example.org` / `ops@example.org` must be replaced.
2. **`/healthz`** does not exist; healthchecks hit `/`. Engineering ask #7 stands.
3. **Pinned dependencies**: `requirements.txt` is unpinned (today: fastapi 0.142, numpy 2.5, trimesh 5.1...). Builds are not reproducible and a new numpy/skimage can break things (tests already emit NumPy 2.5 deprecation warnings from scikit-image).
4. **PrusaSlicer AGPL**: legal should confirm hosting obligations. The apt package adds roughly 1 GB (GUI libs); an alternative is a slimmer separate "slicer worker" image or the AppImage CLI.
5. **Uploads and worker limits**: Caddy caps bodies at 55 MB; per-job memory/time caps and a queue still need Engineering (blocker #5). Compose limits are a stopgap.
6. **Off-site target and retention**: Backblaze B2 + `rclone` assumed; who holds the `age` private key? (Store it offline, not on the server.)
7. **CSP**: report-only until tested in a browser against the UI (importmap + module scripts + `blob:` previews). Promote to enforcing after.
8. **Staging**: reuse this compose file with a different `ZEIM_HOST_DIR`, domain and seed data. Never copy production data there.
9. **Read-only mode / rollback**: not implemented. Rollback today = `docker compose up -d` with a previous image tag + `restore.sh`.
10. **Secrets**: `.env` on the host is a stopgap; move to a secrets manager when there is one. `link.key` should leave `data/` (Engineering ask #6); until then it travels inside every backup.
