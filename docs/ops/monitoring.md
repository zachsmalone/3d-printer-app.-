# Monitoring and alerting

ZEIM is a one-person operation, so this is deliberately minimal and free-tier-first.
Every alert must have a runbook entry below — an alert without a runbook is noise.

## What we run

| concern | tool (free tier is fine) | what pages a human |
|---|---|---|
| Uptime | UptimeRobot (5-min checks) on `https://<domain>/healthz` | any 2 consecutive failures |
| Error rate | Sentry (self-hosted or SaaS free tier) via `loguru`/logging integration, or plain log scan | new CRITICAL log entries: `zeim.audit`, `zeim.uploads`, unhandled exceptions |
| Disk | `df` on the host via cron | disk under 10% free |
| Moderation SLA | `/api/moderation/queue` (admin token) exposes `oldest_open_age_s`; poll it with a small cron script | breach when the oldest open report exceeds 24h (slicer queue-depth monitoring itself is still outstanding — /healthz does not expose it today) |
| Backups | `scripts/backup.py` exit code + monthly restore drill | non-zero exit, failed drill |

Cron sketch (the host, not the container):

```
17 3 * * *  cd /srv/zeim && docker compose exec app python -m scripts.backup --data /data --out /outputs --backup-root /data/backups || curl -s "https://uptime.example.org/alert?msg=backup-failed"
```

## Runbooks

**healthz failing / site down**
1. `docker compose ps` — are the containers up?
2. `docker compose logs app --tail 100` — look for the startup failure (production fail-closed auth errors appear here).
3. If disk full: `df -h`, free space (the retention sweep only removes unstarred builds — check `/outputs`).
4. Rollback: `git log --oneline -5` in the deploy dir, check out the previous release, restart.

**Error spike**
1. Sentry (or `docker compose logs app --tail 500 | grep -i error`).
2. Common causes: upload gate rejections (429/415 in `data/uploads.log.jsonl` — expected under attack), slicer OOM (RLIMIT_AS kills show as slice failures — the cap is worker protection, not a fix; if legitimate jobs hit it, raise `PHOTO3D_SLICE_MEM_MB` on a host with more RAM).
3. If abuse: the upload gate and report rate limits are the first brake; PHOTO3D_UPLOADS_PER_HOUR can be lowered live in env.

**Moderation SLA breach (oldest open report > 24h)**
1. Open `/api/moderation/queue` with the admin token.
2. Triage `minor_safety` / `underage_user` first (they auto-hide, but need decisions).
3. CSAM suspicion: follow docs/legal/ncmec-procedure.md exactly — preserve, escalate, human files with the CyberTipline within 24h.

**Backup failed**
1. Check disk space in the backup root first (retention removes old backups automatically).
2. Run the backup manually with the same command; read the JSON report.
3. Do NOT let a failed backup slide past 48h — the off-site copy is the whole point.

## What is deliberately not built yet

No log aggregation service (ELK/Datadog) — one person cannot justify the cost or the noise.
Container stdout + `docker compose logs` + the audit log cover launch needs. Revisit at
~1,000 weekly users. The UptimeRobot/Sentry/cron entries above are the PROPOSED launch
setup — none of it is configured until a real host exists.
