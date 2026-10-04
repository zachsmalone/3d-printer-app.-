# Runbook: temporary passcode-protected HTTPS address so Zach can test ZEIM on his iPhone

For Mr. Yami Kato (operator). Written by Ren Okabe (DevOps). **PROPOSAL. Prepared, NOT switched on.**
**Everything here is UNTESTED ON REAL iOS.** The ngrok tunnel itself was probed from this computer (registers OK, empty port); the full start has been exercised only up to the public passcode check (see TEST-NOTES).

## What this sets up

```
iPhone Safari --https--> ngrok (free plan) --> Caddy 127.0.0.1:8480 (passcode check) --> ZEIM 127.0.0.1:18765 (PHOTO3D_MODE=shared)
```
- The tunnel points only at Caddy. ZEIM and Caddy listen on `127.0.0.1` only. Nothing else on this computer is exposed. The ngrok local inspector/API is switched off (`web_addr: false`), so nothing listens on port 4040.
- The passcode (HTTP basic auth, user `zach`) is checked by Caddy **in front of** the app. Every path needs it, including `/healthz` and static files. Caddy matches any Host name (the tunnel forwards the public name); an earlier template that matched only `127.0.0.1` answered an empty 200 for other hosts before the passcode check. `start.sh`'s public check caught it and it is fixed; keep the `http://:PORT` form.
- ZEIM starts from a **brand-new empty data folder** `/workspace/zeim-test-run/<timestamp>/{data,outputs}`. It never reads or writes `/workspace/photo3d/data` or `outputs`. The normal instance on port 8765 is not touched.
- `PHOTO3D_MODE=shared` is set on purpose (no admin token): Settings, printers and linked accounts stay locked.
- `start.sh` starts the tunnel first, reads the address from ngrok's JSON log (`"msg":"started tunnel"`), then starts ZEIM with `PHOTO3D_PUBLIC_BASE_URL=<that address>` (locked in the UI; join QR codes and signed links use it).
- Caddy overwrites `X-Forwarded-For` with the real client address and drops `X-Real-IP`; it trusts forwarded headers only from loopback (ngrok's agent).
- Auto-shutoff after 120 minutes (`--max-minutes N`, 5 to 480). `stop.sh` stops it sooner.

### The ngrok authtoken (secret)
Zach's token is stored ONLY in `/workspace/tools/.ngrok-authtoken` (mode 0600). Do not use the `NGROK_AUTHTOKEN` environment variable (it holds a wrong value on this box).
- `start.sh`/`probe-tunnel.sh` read the file and give the token to the ngrok process only (`NGROK_AUTHTOKEN=... ngrok ...` for that one command). It is never exported to other programs, never on a command line (`ps` shows no secret), never written to a config file (the per-run `ngrok.yml` has no token). ngrok masks it as `[REDACTED]` in its own log; scripts also count (never print) token text in the ngrok log and `check-logs.sh` counts it too.
- `stop.sh` (manual or from the timer) **shreds the token file**. If `start.sh` itself fails, it stops everything but KEEPS the file so a fixed script can be re-run. After the test Zach should rotate the token in the ngrok dashboard anyway.
- Tools live in `/workspace/tools` (not in git): `ngrok` 3.39.11 (verified against ngrok's GPG-signed apt repo; see TEST-NOTES), `caddy` 2.11.6. `cloudflared` is no longer used (see "Why not Cloudflare").

## Why not Cloudflare (history)
This computer's outbound network passes only TLS on port 443. `cloudflared` needs TCP/UDP 7844, so it never registers a tunnel (probed 2026-10-04); localtunnel, ssh-based tunnels, bore and Tunnelmole fail too. ngrok's agent connects over 443 and works, with two settings: `agent.crl_url: https://crl.ngrok-agent.com/ngrok.crl` (ngrok's certificate-revocation check defaults to plain http on port 80, which is blocked here; this keeps the check ON, over https) and a version "3" config file. Cloudflare support was removed from `start.sh`, not kept.

## Preconditions (the gate)
Do not start until **Haruto has confirmed in HQ** that the first-batch fixes are live: S-01 settings gate, signed-link/base-URL, camera button. `start.sh` refuses to run without `--haruto-confirmed`, so only add that flag after you have seen his confirmation. (Code check on 2026-10-04: the S-01 gate and `PHOTO3D_PUBLIC_BASE_URL` already exist in the repo; the camera button I did not look for.)

Also confirm with Kenji's conditions:
1. Passcode in front of the app. Done by Caddy, nothing to do.
2. Short-lived. Auto-shutoff is on; still run `stop.sh` when Zach says he's done.
3. Fresh data folder. Automatic. Never point it at the real `data/`.
4. **Rules for the test (tell Zach):** only sample images or Zach's own photos; no photos of other people (especially children) and no class data; never forward the link or passcode to anyone.
5. After the test: `stop.sh` scans logs for signed-link tokens (below).

## Start (about 10 to 60 seconds)
```bash
cd /workspace/photo3d/reports/deploy/iphone-test
./start.sh --haruto-confirmed            # runs the working-tree code
./start.sh --haruto-confirmed --snapshot # or: runs the last COMMITTED code (git archive HEAD) in a private copy
./start.sh --haruto-confirmed --max-minutes 60
```
Before starting: the token file `/workspace/tools/.ngrok-authtoken` must exist (Zach saves it; `start.sh` refuses without it).
It prints only: `started; URL and passcode saved in <run>/url.txt and <run>/passcode.txt (0600). Username: zach. ...`
The URL and passcode are never printed. Before reporting success it checks that the passcode gate answers **401 without** and **200 with** the passcode, locally and at the public address. If any check fails it stops everything and says why.

## Send Zach the URL and passcode (private DM only, never a group chat, never HQ, never a report)
On this computer, read them yourself:
```bash
cat /workspace/zeim-test-run/CURRENT/url.txt; echo
cat /workspace/zeim-test-run/CURRENT/passcode.txt; echo
```
Send them in **Zach's 1:1 chat only**, as two separate lines ("Address:" and "Passcode:", username `zach`). Say that it stops by itself at the time in `/workspace/zeim-test-run/CURRENT/run-info.txt` (`auto_shutoff=`). Do not paste either into HQ, Hq2, a ticket or a file under `reports/`.

## What Zach does on the iPhone
1. Open the address in **Safari** (a normal tab, not an app shortcut on the Home Screen: login prompts are unreliable there).
2. Safari asks for a user name and password: user `zach`, then the passcode (copy it from the DM). Tap Sign In.
3. ZEIM loads. When the camera button appears, allow camera access when Safari asks. Camera needs https, which the tunnel gives.
4. **ngrok free plan shows a warning page the first time** ("You are about to visit ... Visit Site"). That is ngrok, not ZEIM: tap **Visit Site**. It is shown once per browser per address for a while; the passcode prompt follows. (My scripts skip it with the header `ngrok-skip-browser-warning`; a browser cannot.) UNTESTED on a real iPhone.
5. Only use sample images or his own photos.
Notes on login behaviour (all UNTESTED ON REAL iOS): Safari remembers the passcode for that address for the session and sends it automatically with the page's own requests (fetch/XHR, images, model files), so the app should keep working after one login. If something loads but the app shows errors, close the tab and reopen the address. Links that other apps must fetch without a login (for example a slicer app opening a signed `/f/...` link) will **not** work through the passcode gate; that is intended. Download from the browser instead.
Long builds / free-plan limits: ngrok's free plan allows ONE agent session at a time, shows the warning page above, and has bandwidth and request-rate caps and an upload/request body limit (Caddy here also caps bodies at 30 MB). I have not hit or measured any of these yet; see TEST-NOTES for what was actually observed. A very slow request might fail through the tunnel when it works locally.

## Shut down
Automatic at the auto-shutoff time, or any time:
```bash
cd /workspace/photo3d/reports/deploy/iphone-test
./stop.sh                 # stops tunnel, Caddy, app, timer; confirms ports are free; scans logs; shreds passcode, URL and the ngrok token file
./stop.sh --purge-data    # same, and also deletes the test data/outputs (any photos Zach uploaded)
```
Tell Zach when it is off. Then the old address is dead (a free ngrok address is random per start and the token file is gone). Zach should also rotate the authtoken in the ngrok dashboard.

## After the test: log check
`stop.sh` runs `check-logs.sh` and saves `log-check-report.txt` in the run folder. Run it later with `./check-logs.sh /workspace/zeim-test-run/<timestamp>`. It prints counts only (never the values) for: signed-link URLs `/f/<expiry>-<32 hex>/...` (the token is in the URL **path**), token-shaped strings, query strings with `token/sig/code/state/key/password`, Basic-auth headers and the passcode itself, in the app, Caddy and ngrok logs (and the ngrok authtoken text, if the token file still exists). Expected result: all zeros in `app.log`; Caddy's access log shows `/f/REDACTED/` and `?REDACTED` (query strings and path tokens are masked, cookies/Authorization/Referer dropped). The app log has the uvicorn access log switched off so request URLs never reach it. Any non-zero count means: treat the link/passcode as exposed and tell Kenji.
Log retention: logs stay in the run folder (mode 700) until someone deletes them. `rm -rf /workspace/zeim-test-run/<timestamp>` when done.

## If something misbehaves
| Symptom | What to do |
|---|---|
| `start.sh` says `REFUSING TO START` | The gate flag is missing. Only add it after Haruto's confirmation. |
| "ngrok exited (ERR_NGROK_xxx)" / "no ngrok tunnel after 60 s" | `logs/ngrok.log` in the run folder has the reason. `ERR_NGROK_105` = not a valid authtoken; `ERR_NGROK_108` = another ngrok session is already online on this account (close it, free plan allows one); "timed out fetching CRL" = `crl_url` missing from `ngrok.yml`. `start.sh` already stopped everything and kept the token file. |
| Port in use | `ss -ltn` to see what; or set `ZEIM_PROXY_PORT` / `ZEIM_APP_PORT`. |
| Zach is asked for a login again and again | Re-send the passcode (exact, with dashes, no trailing space). Do not lower the protection. |
| Public check says 200 without a passcode | `start.sh` stops everything on its own. Do not retry; tell Ren Okabe. |
| Anything strange (unexpected visitors in `logs/caddy-access.log`, passcode leaked) | `./stop.sh` immediately; a new run gets a new address and passcode. |
| You can't find a stuck process | `./stop.sh` is safe to run twice; `pgrep -fa 'zeim-test-run'`. |

## Known risks (honest list)
- **Anyone who learns the random address can reach the login prompt from the public internet. The passcode is the only gate.** The passcode is 25 random characters (about 120 bits). Caddy has no built-in login-attempt limit, so a long random passcode is the brute-force defence (Caddy's bcrypt hashing at cost 14 also makes each guess slow). Never replace it with a short one.
- A third party (ngrok) sees the traffic, including the photos Zach uploads. Photos are the reason for rule 4.
- The free ngrok tier has no uptime guarantee and can drop; if so, run `stop.sh` and `start.sh` again (new address, new passcode; the token file is shredded by `stop.sh`, so Zach must save it again).
- The address appears in `ngrok.log` (blanked by `stop.sh`) and, as the Host header, may appear in Caddy's access log. It is also in the environment of the ZEIM process (`PHOTO3D_PUBLIC_BASE_URL`), readable only by this Unix user. Keep the run folder private.
- ZEIM itself still has no real login, so inside the passcode wall everything is shared state of one empty test instance. That is acceptable only because the data folder is fresh and the link goes to Zach alone.
- The passcode file is deleted (shredded) by `stop.sh`; it can't be recovered afterwards.
- Untested: real iOS Safari behaviour (login prompt, camera, share sheet), the long builds and uploads through ngrok's free tier. Tested offline: see `TEST-NOTES.md`.

## Files
`start.sh`, `stop.sh`, `check-logs.sh`, `probe-tunnel.sh` (ngrok connectivity check on an empty port; do not run while a test is live), `lib.sh` (ports, paths), `Caddyfile.template`, this runbook, `TEST-NOTES.md`.
Settings (environment variables): `ZEIM_PROXY_PORT` (8480), `ZEIM_APP_PORT` (18765), `ZEIM_MAX_MINUTES` (120), `ZEIM_APP_DIR`, `ZEIM_PYTHON`, `ZEIM_CADDY`, `ZEIM_NGROK`, `ZEIM_NGROK_TOKEN_FILE`, `ZEIM_RUN_ROOT`. ZEIM's own: `HOST`, `PORT`, `PHOTO3D_DATA`, `PHOTO3D_OUT`, `PHOTO3D_MODE`, `PHOTO3D_PUBLIC_BASE_URL`, `FORWARDED_ALLOW_IPS` (`start.sh` sets these; you should not need to).
