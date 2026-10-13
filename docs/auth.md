# ZEIM sign-in (passkeys + email codes) — not wired in yet

The code lives in `app/auth/` (rules) and `app/api/auth.py` (HTTP routes under `/api/auth`).
It is **not mounted** in `app/main.py` yet; the existing login is unchanged.

## How it works, in plain words
- **No passwords.** People sign up with a *passkey* (Face ID, fingerprint, phone or security key).
- **Email codes** are a backup: add an email, then sign in with a 6-digit code that works once, for 10 minutes.
- **Sessions** live on the server. The browser only holds a random cookie (`__Host-zeim_session`:
  HttpOnly, Secure, SameSite=Lax, Path=/). Idle sessions end after 14 days, every session after 30.
- **Sign out everywhere** and per-device sign-out are built in.
- **Sensitive changes** (adding a passkey or an email) need a sign-in from the last 15 minutes.
- **18+ only.** Sign-up asks for a birth date and refuses anyone under 18.
- Emails are never stored in plain text (only a keyed hash and a masked hint like `s***@e***.com`).
- Requests that change things must send `X-Requested-With: zeim` and come from an allowed origin.
- Rate limits (per IP and per email) stop code guessing and email spamming.

## Settings (environment variables)
| Variable | Required | Meaning |
|---|---|---|
| `ZEIM_RP_ID` | yes | The site's domain, e.g. `zeim.example` (passkeys are tied to it). |
| `ZEIM_ORIGINS` | yes | Comma-separated allowed origins, e.g. `https://zeim.example`. Must be https. |
| `ZEIM_AUTH_PEPPER` | yes | A secret of **at least 32 characters**. Keep it out of git; changing it invalidates stored email hashes. |
| `ZEIM_AUTH_DB` | no | SQLite path (default `data/auth.sqlite3`). |
| `ZEIM_SMTP_HOST/PORT/FROM/USER/PASSWORD` | no | Mail server for codes. Without it, email codes are switched off. |
| `ZEIM_TRUST_PROXY` | no | `1` only behind a proxy you control (uses the last X-Forwarded-For hop). |
| `ZEIM_ENV=dev` | no | Local dev defaults (localhost, dev pepper). Never in production. |

The server refuses to start the auth module if the three required values are missing or weak.

## Still to do before switching it on
1. Mount it in `app/main.py` with `init_auth(app, legacy_resolver=...)`. The resolver maps today's
   cookie account to `(legacy_id, display_name)` so existing users keep their data (`owner_id` stays the legacy id).
2. Retire the old recovery codes once accounts have a passkey or email.
3. Decide what happens when someone loses their only passkey and has no email.
4. Set `ZEIM_RP_ID`, `ZEIM_ORIGINS` and `ZEIM_AUTH_PEPPER` on the live server (and SMTP if email codes are wanted).
