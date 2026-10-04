# Runbook: temporary passcode-protected HTTPS address so Zach can test ZEIM on his iPhone

For Mr. Yami Kato (operator). Written by Ren Okabe (DevOps). **PROPOSAL. Prepared, NOT switched on.**
**Everything here is UNTESTED ON REAL iOS** and the tunnel itself is UNTESTED from this computer (see "Blocker" below).

## What this sets up

```
iPhone Safari --https--> Cloudflare quick tunnel --> Caddy 127.0.0.1:8480 (passcode check) --> ZEIM 127.0.0.1:18765
```
- The tunnel points only at Caddy. ZEIM listens on `127.0.0.1` only. Nothing else on this computer is exposed.
- The passcode (HTTP basic auth, user `zach`) is checked by Caddy **in front of** the app. Every path needs it, including `/healthz` and static files.
- ZEIM starts from a **brand-new empty data folder** `/workspace/zeim-test-run/<timestamp>/{data,outputs}`. It never reads or writes `/workspace/photo3d/data` or `outputs`.
- `PHOTO3D_MODE=shared` is set on purpose: Settings, printers and linked accounts stay locked (no admin token is set), so Zach cannot change server settings from the phone.
- The tunnel address is random and only known after the tunnel starts, so `start.sh` starts the tunnel first and then starts ZEIM with `PHOTO3D_PUBLIC_BASE_URL=<that address>`. The setting is locked in the UI, and join QR codes and signed links use the tunnel address.
- Auto-shutoff after 120 minutes (change with `--max-minutes N`, 5 to 480). `stop.sh` stops it sooner.
- Cloudflare **quick tunnels need no account and no money**. Tools live in `/workspace/tools` (not in git): `cloudflared` 2026.9.3 (SHA-256 checked against the official GitHub release: OK) and `caddy` 2.11.6.

## Blocker to read first: this computer cannot open a working tunnel (tested 2026-10-04)

**Result: the tunnel does not connect from this computer.** The probe was run with Zach's and Mr. Yami Kato's OK (empty port, about 25 s, shut down, nothing served). Details:
- `cloudflared` gets an address (that part uses port 443) but never logs `Registered tunnel connection`. Its own pre-check fails for QUIC/UDP and for HTTP/2 over TCP 7844. Tried `--protocol auto`, `http2` and `quic`: all fail. (`http2` also uses 7844, not 443, so there is no 443-only mode.)
- **Why:** this computer's outbound network only passes TLS (HTTPS) traffic on port 443. Raw TCP on 443 (for example ssh), every other port (22, 80, 7844, 8083) and UDP time out. Hostnames resolve to a placeholder address handled by the egress proxy.
- Other options checked: `localtunnel` (needs raw TCP to a high port: blocked), `pinggy`/`serveo`/`localhost.run` (need ssh; ssh-on-443 gets no reply because it is not TLS), `bore.pub` (port 7835: blocked), `Tunnelmole` (npm, no account; its client connects to `service.tunnelmole.com:8083`: blocked, so it never produced an address). `ngrok` and `tailscale funnel` need accounts, so they were not tried. A DIY WebSocket tunnel needs a public relay server, which we do not have.
- Earlier versions of `probe-tunnel.sh` and `start.sh` treated "got an address" as success, which **gave a false yes**. Both now require `Registered tunnel connection`; `start.sh` fails safe and stops everything if it is missing.

So `start.sh` will stop with "could not connect to Cloudflare" on this computer. Options, in order:
1. Run the test from Zach's own computer (or any computer with open outbound internet): copy this folder and `/workspace/tools/{caddy,cloudflared}` equivalents, or use `reports/deploy/local-https/` (home Wi-Fi only; trust a certificate on the phone).
2. Ask whoever controls this computer's network egress to allow outbound TCP 7844 (and ideally UDP 7844) to `*.argotunnel.com`, then re-run `./probe-tunnel.sh --yes-open-a-probe-tunnel`.
3. On a computer with ssh: `ssh -p 443 -R0:localhost:8480 free.pinggy.io` (free, time-limited, run by Pinggy; not tried). Any third-party tunnel sees all traffic including uploaded photos; use sample images only.

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
4. Only use sample images or his own photos.
Notes on login behaviour (all UNTESTED ON REAL iOS): Safari remembers the passcode for that address for the session and sends it automatically with the page's own requests (fetch/XHR, images, model files), so the app should keep working after one login. If something loads but the app shows errors, close the tab and reopen the address. Links that other apps must fetch without a login (for example a slicer app opening a signed `/f/...` link) will **not** work through the passcode gate; that is intended. Download from the browser instead.
Long builds: Cloudflare gives up on a request after about 100 seconds (error 524). A slow build might fail through the tunnel when it works locally.

## Shut down
Automatic at the auto-shutoff time, or any time:
```bash
cd /workspace/photo3d/reports/deploy/iphone-test
./stop.sh                 # stops tunnel, Caddy, app, timer; confirms ports are free; scans logs; deletes passcode + URL files
./stop.sh --purge-data    # same, and also deletes the test data/outputs (any photos Zach uploaded)
```
Tell Zach when it is off. Then the old address is dead (a quick tunnel address cannot be reused).

## After the test: log check
`stop.sh` runs `check-logs.sh` and saves `log-check-report.txt` in the run folder. Run it later with `./check-logs.sh /workspace/zeim-test-run/<timestamp>`. It prints counts only (never the values) for: signed-link URLs `/f/<expiry>-<32 hex>/...` (the token is in the URL **path**), token-shaped strings, query strings with `token/sig/code/state/key/password`, Basic-auth headers and the passcode itself, in the app, Caddy and cloudflared logs. Expected result: all zeros in `app.log`; Caddy's access log shows `/f/REDACTED/` and `?REDACTED` (query strings and path tokens are masked, cookies/Authorization/Referer dropped). The app log has the uvicorn access log switched off so request URLs never reach it. Any non-zero count means: treat the link/passcode as exposed and tell Kenji.
Log retention: logs stay in the run folder (mode 700) until someone deletes them. `rm -rf /workspace/zeim-test-run/<timestamp>` when done.

## If something misbehaves
| Symptom | What to do |
|---|---|
| `start.sh` says `REFUSING TO START` | The gate flag is missing. Only add it after Haruto's confirmation. |
| "no tunnel address after 60 s" / cloudflared exited | See the blocker above; `logs/cloudflared.log` in the run folder (it has the reason). `start.sh` already stopped everything. |
| Port in use | `ss -ltn` to see what; or set `ZEIM_PROXY_PORT` / `ZEIM_APP_PORT`. |
| Zach is asked for a login again and again | Re-send the passcode (exact, with dashes, no trailing space). Do not lower the protection. |
| Public check says 200 without a passcode | `start.sh` stops everything on its own. Do not retry; tell Ren Okabe. |
| Anything strange (unexpected visitors in `logs/caddy-access.log`, passcode leaked) | `./stop.sh` immediately; a new run gets a new address and passcode. |
| You can't find a stuck process | `./stop.sh` is safe to run twice; `pgrep -fa 'zeim-test-run'`. |

## Known risks (honest list)
- **Anyone who learns the random address can reach the login prompt from the public internet. The passcode is the only gate.** The passcode is 25 random characters (about 120 bits). Caddy has no built-in login-attempt limit, so a long random passcode is the brute-force defence (Caddy's bcrypt hashing at cost 14 also makes each guess slow). Never replace it with a short one.
- A third party (Cloudflare) sees the traffic, including the photos Zach uploads. Photos are the reason for rule 4.
- Quick tunnels have no uptime guarantee or support and can drop; if so, just run `stop.sh` and `start.sh` again (new address, new passcode).
- The address appears in `cloudflared.log` and (as the Host header) in Caddy's access log. Keep the run folder private.
- ZEIM itself still has no real login, so inside the passcode wall everything is shared state of one empty test instance. That is acceptable only because the data folder is fresh and the link goes to Zach alone.
- The passcode file is deleted (shredded) by `stop.sh`; it can't be recovered afterwards.
- Untested: real iOS Safari behaviour (login prompt, camera, share sheet), the real tunnel from this computer, long builds through Cloudflare's timeout. Tested offline: see `TEST-NOTES.md`.

## Files
`start.sh`, `stop.sh`, `check-logs.sh`, `probe-tunnel.sh`, `lib.sh` (ports, paths), `Caddyfile.template`, this runbook, `TEST-NOTES.md`.
Settings (environment variables): `ZEIM_PROXY_PORT` (8480), `ZEIM_APP_PORT` (18765), `ZEIM_MAX_MINUTES` (120), `ZEIM_APP_DIR`, `ZEIM_PYTHON`, `ZEIM_CADDY`, `ZEIM_CLOUDFLARED`, `ZEIM_RUN_ROOT`. ZEIM's own: `HOST`, `PORT`, `PHOTO3D_DATA`, `PHOTO3D_OUT`, `PHOTO3D_MODE`, `PHOTO3D_PUBLIC_BASE_URL`, `FORWARDED_ALLOW_IPS` (`start.sh` sets these; you should not need to).
