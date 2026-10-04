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

## Update 2026-10-04 evening: switched from cloudflared to ngrok (free plan)
UNTESTED ON REAL iOS. Nothing here was run from a phone.

- **ngrok agent**: v3.39.11 linux/amd64, installed at `/workspace/tools/ngrok`. Source `https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz`. ngrok publishes no checksum for it, so it was verified against ngrok's GPG-signed apt repo (`ngrok-agent.s3.amazonaws.com`, key fingerprint F027 1FCF 712C F2E3 9901 F1A3 0E61 D3BB AAEE 37FE; the key came from the same host, so trust-on-first-use): signature on `InRelease` good, `Packages` hash matches it, the `.deb` hash matches `Packages`, and the binary inside the `.deb` is byte-identical to the one installed.
- **Probe (empty port 9, ~15 s, per-run config, token from the 0600 file only)**: `client session established`, `tunnel session started`, `started tunnel`: YES, it connects over 443. No listener on 4040 (inspector off). No `~/.config/ngrok` created. Probe log shredded.
- Earlier probes failed for two reasons: (1) ngrok's default certificate-revocation check uses plain http:80 (blocked here) → fixed with `agent.crl_url: https://crl.ngrok-agent.com/ngrok.crl` (check stays on); (2) the `NGROK_AUTHTOKEN` env var held a wrong value → the token is now read from `/workspace/tools/.ngrok-authtoken`.
- **First full start attempts** (2026-10-04 18:14 CT):
  - Attempt 1: a script bug (`chmod` on a log file before it existed) aborted `start.sh` after ngrok and Caddy were up but before ZEIM was started. The tunnel pointed at the passcode-gated Caddy only, for under a minute; stopped with `stop.sh`; fixed.
  - Attempt 2: the built-in public check reported `200 without passcode` and `start.sh` stopped everything (fail-safe worked). Cause: Caddy's site address was `http://127.0.0.1:8480`, so requests carrying the public ngrok Host name matched no site and got an **empty 200 from Caddy before the passcode check**. No ZEIM content was involved (ZEIM had not been reached). Fix: site address `http://:8480` + `bind 127.0.0.1`. Offline re-test with Host `127.0.0.1:...` and a foreign Host: both 401 without passcode, 200 with. Not yet re-tested through the real tunnel.
  - That failed start also shredded the token file (old behaviour). Changed: a failed `start.sh` now keeps the token file (`stop.sh --keep-token`); only a deliberate stop or the timer shreds it.
- `bash -n` on all scripts: OK. Caddy config validated by `start.sh` on each run (OK).
- **Free-plan limits: documented by ngrok, NOT yet observed here**: one agent session at a time (ERR_NGROK_108 if a second is started), a browser warning page on first visit ("Visit Site"), bandwidth/request caps, no custom domain. Observed: nothing yet about timeouts or upload size through the tunnel.
- **Log note**: `grep -c` of two earlier probe logs for the (then wrong) env token returned 5 even though the displayed lines were `[REDACTED]`; those logs were shredded. With the correct token the probe log count was 0.

## Live run 2026-10-04 ~18:20 CT (ngrok, real tunnel; checks done from this computer with curl, NOT from a phone: UNTESTED ON REAL iOS)
- Started with `start.sh --haruto-confirmed` (shared mode, fresh data, app 127.0.0.1:18765, Caddy 127.0.0.1:8480). First live start (18:18) was restarted at 18:20 after finding that Caddy, ZEIM and the timer had inherited a stray, wrong `NGROK_AUTHTOKEN` from the box environment; `start.sh` now does `unset NGROK_AUTHTOKEN` and only the ngrok process gets the real token (verified via /proc environ: caddy/app/timer 0, ngrok 1 and equal to the file token).
- Through the public address: `/` 401 without passcode, 200 with; `/api/settings`, `/static/../app/main.py`, a fake `/f/<token>/..` link, `/sharetest`: 401 without; `/healthz` and `/` 200 with; encoded traversal with passcode 404. A request with a bogus Host header is refused by ngrok's edge itself (421) and never reaches Caddy; straight to Caddy locally a bogus Host gets 401.
- `/sharetest` 200 (title marker present); `static/photo.js` 200 with `capture="environment"` and `getUserMedia`; `index.html` has the photo hint markers.
- `/api/settings`: `mode` = shared, `public_base_url` equals the tunnel address, locked. (The `/api/me` send block also reports mode shared.)
- Photo build through the tunnel (POST /api/generate, `tests/sample.png` 16 KB, lithophane, beginner): HTTP 200 in ~2.5-2.9 s, watertight. STL download 14.1 MB in ~1.4 s. Also a 5.7 MB noisy JPEG upload: HTTP 200 in 5.4 s. No timeout, size or rate-limit problem seen at these sizes. (Test builds were removed from the run folder afterwards.)
- **ngrok free-plan interstitial confirmed**: a browser-like request (iPhone User-Agent, `Accept: text/html`, no skip header) gets HTTP 200 with ngrok's warning page, not the passcode prompt. Zach must tap "Visit Site" first. Scripted requests with `ngrok-skip-browser-warning: 1` skip it. Not observed: longer requests, bandwidth caps, rate limits.
- Listeners: only 127.0.0.1:18765 and 127.0.0.1:8480 from this run; port 4040 and any ngrok listener: none. Port 8765 instance (pid 281929, started 17:42) untouched.
- Secrets: no token/passcode/address in `ps` args, repo, or run-folder files other than `url.txt`, `passcode.txt`, `ngrok.log` (address) and the Caddy access log (host name). `check-logs.sh`: all zeros.
