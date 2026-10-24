# ZEIM sign-in (passkeys + email codes)

The code lives in `app/auth/` (rules) and `app/api/auth.py` (HTTP routes under `/api/auth`).
It is **mounted** from `app/main.py` via `try_mount_auth(app)` (which calls `init_auth` with a
legacy resolver). The old cookie login (`p3d_sid`) still works alongside it.

## How it works, in plain words
- **No passwords.** People sign up with a *passkey* (Face ID, fingerprint, phone or security key).
- **Email codes** are a backup: add an email, then sign in with a 6-digit code that works once, for 10 minutes.
- **Sessions** live on the server. The browser only holds a random cookie (`__Host-zeim_session`:
  HttpOnly, Secure, SameSite=Lax, Path=/). Idle sessions end after 14 days, every session after 30.
  On plain http localhost the cookie name is `zeim_session` (no `__Host-`, so it works without https).
- **Sign out everywhere** and per-device sign-out are built in.
- **Sensitive changes** (adding a passkey or an email) need a sign-in from the last 15 minutes.
- **18+ only.** Sign-up asks for a birth date and refuses anyone under 18.
- Emails are never stored in plain text (only a keyed hash and a masked hint like `s***@e***.com`).
- Requests that change things must send `X-Requested-With: zeim` and come from an allowed origin.
- Rate limits (per IP and per email) stop code guessing and email spamming.

## When it turns on
| Situation | What happens |
|---|---|
| `ZEIM_ENV=dev`, or listening on localhost / 127.0.0.1 / ::1 | Comes up with safe local defaults (localhost RP id, http origins for this port, a fixed dev pepper). Plain-http cookies allowed. |
| Production (non-loopback host, `ZEIM_ENV` not `dev`) with strong `ZEIM_RP_ID` + `ZEIM_ORIGINS` (https) + `ZEIM_AUTH_PEPPER` (32+ chars) | Mounts normally. |
| Production **without** those secrets | App **keeps running** with the old cookie login. A clear warning is logged. It does **not** crash, and it does **not** weaken the required-secret checks. |
| No SMTP (`ZEIM_SMTP_*`) | Email codes stay off (passkeys still work). Set `ZEIM_DEV_MAIL=console` in dev to print codes to the log. |

Existing cookie accounts can add a passkey: the legacy resolver maps today's `p3d_sid` account to
`(account id, display name)` so `owner_id` stays that account id and their Showcase / follows keep working.

## Who owns what (session -> account)
- Every ZEIM route asks `identity.get_actor`. If a live `zeim_session` cookie is present, the account is the one whose
  `id` equals the session's auth `owner_id` (the legacy id for upgraded cookie accounts, otherwise the auth account id).
  Builds, Edit projects, Showcase items, follows and favourites then belong to that account on **every device** it signs in on.
- A passkey sign-up makes the ZEIM account record right away (same birth-date record as cookie accounts, display name
  through ZEIM's name filter, auto username). That record sits under an internal key that is never a browser cookie,
  so signing out of the passkey session really signs that browser out.
- Right after a passkey / email-code sign-in, builds this browser made while **signed out** move to the account.
  A browser that has its own cookie account is never merged into another account.
- Without a live session (signed out, expired, revoked, account disabled) the old `p3d_sid` cookie login works as before.
- "Sign out" in the app (`/api/me/signout`) also ends the passkey session on this browser.

## Settings (environment variables)
| Variable | Required | Meaning |
|---|---|---|
| `ZEIM_RP_ID` | yes (outside local/dev) | The site's domain, e.g. `zeim.example` (passkeys are tied to it). |
| `ZEIM_ORIGINS` | yes (outside local/dev) | Comma-separated allowed origins, e.g. `https://zeim.example`. Must be https outside dev. For a phone tunnel, add the tunnel origin here. |
| `ZEIM_AUTH_PEPPER` | yes (outside local/dev) | A secret of **at least 32 characters**. Keep it out of git; changing it invalidates stored email hashes. |
| `ZEIM_AUTH_DB` | no | SQLite path (default `data/auth.sqlite3` under the data folder). |
| `ZEIM_SMTP_HOST/PORT/FROM/USER/PASSWORD` | no | Mail server for codes. Without it, email codes are switched off. |
| `ZEIM_TRUST_PROXY` | no | `1` only behind a proxy you control (uses the last X-Forwarded-For hop). |
| `ZEIM_ENV=dev` | no | Local / pilot defaults (localhost, dev pepper). Never in production. |
| `ZEIM_INSECURE_COOKIES=1` | no | Dev only: drop the `__Host-` / Secure cookie requirement so plain http works. |

The auth module still **refuses to start** if the three required values are missing or weak when it is asked to load outside the local/dev case. That refuse is caught at mount time so the rest of ZEIM keeps serving.

## Billing is not a login reset

Optional Semi Pro / Pro use Stripe. ZEIM still has **no passwords**. Getting back into an account is a passkey or an email sign-in code (this document). Older cookie accounts may still have a one-time recovery code. Canceling a plan or changing the card is the Stripe Customer Portal, not a password reset. The Stripe Customer id stays on the same ZEIM account, so signing back in keeps the plan. Details: [`docs/ops/stripe-plans.md`](ops/stripe-plans.md).

## Still open (not blocking local/pilot)
1. Retire the old recovery codes once accounts have a passkey or email.
2. Decide what happens when someone loses their only passkey and has no email.
3. Set `ZEIM_RP_ID`, `ZEIM_ORIGINS` and `ZEIM_AUTH_PEPPER` on the live server (and SMTP if email codes are wanted).
4. ~~Wire the new session into the rest of the app~~ **Done (2026-10-13).** See "Who owns what" below.
