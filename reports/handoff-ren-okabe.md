# Handoff - Ren Okabe (Deployment & DevOps)

## What I did
- Local git repo at /workspace/photo3d (branch main, no remote, nothing pushed). Baseline commit 6f605cd; CI proposal e83c465 (.github/workflows/ci.yml, Python 3.13, runs tests/test_app.py and tests/test_features.py). 101 tests passed at that time.
- Deploy drafts in reports/deploy/: Dockerfile (Engineering later moved it to the repo root), docker-compose.yml, Caddyfile, backup.sh, restore.sh, README.md. Validated with bash -n, docker compose config, caddy validate. NOT tested: docker build or a real container boot (no Docker daemon on the box).
- reports/deploy/local-https/: Caddy `tls internal` option for testing from iPhone/iPad on home Wi-Fi. Untested on real iOS.
- reports/deploy/iphone-test/ (+ reports/deploy/phone-test.md pointer): temporary passcode-protected ngrok tunnel kit (start.sh, stop.sh, check-logs.sh, probe-tunnel.sh, lib.sh, Caddyfile.template, RUNBOOK.md, TEST-NOTES.md). Conditions built in: Caddy basic auth in front, app on 127.0.0.1, shared mode, PHOTO3D_PUBLIC_BASE_URL = tunnel URL, X-Forwarded-For overwrite, fresh data folder, 120-minute max (last run shut off 20:19:42 CT), token-redacted logs, stop.sh runs the log check and shreds passcode/URL/token files. Cloudflare tunnel does not work from this box (outbound 7844 blocked); ngrok works over 443. Last run was commit 59b205d; kit commits c79b754, 0e24f74, 756901c, 375f9c4.
- Committed other agents' reports on request: accessibility.md (204c9bf), filter-redteam.md (20a160d).
- Findings sent to Daichi earlier: Fly.io estimate in operations.md looks low (~$104+), Hetzner ranges don't match Hetzner's price page, Option D unpriced, R2 and other recurring costs unverified.

## Unfinished / open
- The running test link: I did not touch it; Mr. Yami Kato handles shutdown (stop.sh, or the timer). After shutdown: run check-logs.sh, confirm /workspace/zeim-test-run/CURRENT passcode.txt and url.txt are gone, and confirm /workspace/tools/.ngrok-authtoken is shredded. Zach should reset his ngrok authtoken (an earlier wrong env value may have been echoed once into a probe log that was deleted).
- Env var NGROK_AUTHTOKEN on the box holds a wrong value; the valid token is only in /workspace/tools/.ngrok-authtoken.
- docker build / real container boot untested. operations.md may still say /healthz doesn't exist (it does).
- Not done: monitoring/alerts, pinned dependencies (requirements.txt is unpinned), hosting/domain/budget decisions (Zach's), mail service for email-to-self.
- One test in tests/test_b1_edit_text.py fails with a 422 (stale after text-placement change); test_b1_ui.py browser results were not fully read. Haruto should check.
- Leftover scratch: /workspace/zeim-scratch-59b205d (mine), /workspace/zeim-test-run/* (run folders; remove with stop.sh --purge-data after the test). Binaries in /workspace/tools: ngrok 3.39.11, cloudflared, caddy 2.11.6.

## Where files are
reports/deploy/, reports/deploy/iphone-test/, reports/deploy/local-https/, .github/workflows/ci.yml, .env.example, .dockerignore.
