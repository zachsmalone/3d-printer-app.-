# Offline test notes (2026-10-04, Ren Okabe). Nothing was exposed publicly; the tunnel was replaced by a stand-in script that only prints a fake address.

Setup: `ZEIM_CLOUDFLARED=<stand-in>`, `ZEIM_SKIP_PUBLIC_CHECK=1`, ports 18480/18766, `--snapshot` (git archive of HEAD 322dd31), scratch run folder outside the repo.

| Check | Result |
|---|---|
| `bash -n` start.sh stop.sh check-logs.sh lib.sh probe-tunnel.sh | OK |
| `caddy validate` on the rendered Caddyfile (done inside start.sh) | OK (Caddy 2.11.6) |
| `start.sh` without `--haruto-confirmed` | refuses, exit 3, creates nothing |
| unknown option | exit 2 |
| Caddy without passcode / wrong password / wrong user | 401 (also OPTIONS and static files) |
| Caddy with passcode: `/`, `/healthz` | 200 |
| App (18766) and Caddy (18480) reached via this computer's non-loopback address | connection refused (both bound to 127.0.0.1) |
| Listeners | only 127.0.0.1:18480 (caddy) and 127.0.0.1:18766 (uvicorn) |
| Fresh data dir: app created its files in the scratch `data/` | yes (users.json, projects.json, projects/, classroom_projects/) |
| Settings write through the proxy without admin token | 403 (S-01 gate working in shared mode) |
| `PHOTO3D_PUBLIC_BASE_URL` | `/api/settings` returned the stand-in address with `public_base_url_locked: true` |
| Caddy trusts forwarded headers from loopback only | `X-Forwarded-For` became `client_ip` in the log |
| Caddy access log redaction | `/f/<token>/abc/model.stl?token=...&code=...` logged as `/f/REDACTED/abc/model.stl?REDACTED`; no Authorization/Cookie |
| Passcode on any command line (`ps`) or in the Caddyfile | not found |
| `check-logs.sh` on the clean run | all zeros, exit 0 |
| `check-logs.sh` on planted fake token/query/Basic header/passcode | all detected, exit 1, values not printed |
| Auto-shutoff timer (6 s test override) | stopped by itself; ports free; passcode and URL files deleted; log report written |
| `stop.sh` | stops cloudflared, Caddy, app, timer; confirms ports free; deletes passcode, URL, hash; `--purge-data` removes data |
| File modes | run dir 700, passcode/url/hash/logs 600 |
| Existing `/workspace/photo3d/data` and `outputs` | not read or written by the test run (their contents changed during the window only because other agents use the live app) |

NOT tested: real tunnel (blocked/unknown from this computer, see RUNBOOK), real iOS Safari, a photo build through the proxy, public-address 401 check (needs the real tunnel).

## Update 2026-10-04 (probe run)
- Real tunnel probe run (empty port, about 25 s per variant): cloudflared allocates an address but never registers (auto, http2 and quic all fail). The old probe/start logic gave a false "yes"; fixed to require `Registered tunnel connection`. Probe now correctly prints "no".
- After the edit: `bash -n` OK on probe-tunnel.sh and start.sh. The new gate loop was checked on its own with fake logs (registered: proceeds; address only: fails safe). `start.sh` itself was NOT re-run end to end (not allowed), so an offline stand-in must now also print a line containing `Registered tunnel connection`.
- Other tunnels (localtunnel, ssh-based, bore, Tunnelmole) fail from this computer: only TLS on port 443 gets out. See RUNBOOK.
