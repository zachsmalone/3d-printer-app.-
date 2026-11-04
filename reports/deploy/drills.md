# Restore drills

These runs restore a backup into a scratch copy. They never touch the live data, and no cron is set up.

| When (CST) | Set | Result | Notes |
|---|---|---|---|
| 2026-11-03 6:46–6:53 PM | zeim-20261104T004613Z (made fresh for the drill) | PASS, 125 data files verified | `restore-drill.sh` dry run with `BACKUP_DIR=/tmp/zeim-drill-nosets`, no `--apply`. There was no backup set on the VM because nothing is scheduled to make backups, so the drill made one in scratch (data 421M, outputs 3.6G). Scratch dir `/tmp/zeim-drill.*` was removed afterwards and the site stayed 200 throughout. |

Open item: no backup cron exists in prod. Zach to decide.
