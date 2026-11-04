# Shared email pipeline (RET7, ONB9, expiry warning) — built, switched OFF

Module: `app/services/email.py` · unsubscribe route: `GET /api/email/unsubscribe` · tests: `tests/test_email_module.py`.

## Switch
Sends only when **`ZEIM_EMAIL_ENABLED=1` and `CLOUDFLARE_EMAIL_TOKEN`** are both set. Otherwise every call is a logged no-op
(the would-be payload is logged by kind/user/subject only, never the address). Prod: flag stays 0, no token set, nothing sent.

## Provider
Cloudflare Email Service REST: `POST https://api.cloudflare.com/client/v4/accounts/589efa2a3041d62f3b04dd398bcce6b7/email/sending/send`,
Bearer token, `from: {address: noreply@zeimapp.com, name: ZEIM}`, `html` + `text`, `List-Unsubscribe` header.
Needs Workers Paid (Zach holding) and the sending domain verified in Cloudflare — both are Cloudflare changes, not done.

## Opt-in only
Today the auth store keeps only a keyed hash of each email, so ZEIM *cannot* mail anyone. A person must opt in per kind
(`setup`, `expiry`, `digest`); that stores their address in `DATA/email_optin.json` (chmod 600). Unsubscribing removes the
kind; removing the last kind deletes the address. No opt-in UI is built yet on purpose.

## Before anything is sent (in this order)
1. Change the privacy page: it currently promises email is used for sign-in codes only. Add: optional opt-in emails, what is
   stored (the address, only if you opt in), how to stop. **Not changed in this PR, as asked.**
2. Add the opt-in checkboxes in Account (all unchecked by default).
3. Verify zeimapp.com sending in Cloudflare, set the token in `.env`, flip the flag.
4. Add the senders: expiry warning from the retention sweep (03:00 CT job), ONB9 day 1/3/7 from the off-peak loop.

## Templates (plain, short, account-setup help)
- ONB9 day 1 "Welcome to ZEIM" → first-print lesson; day 3 "Setting up your printer"; day 7 "Keeping your builds" (star tip).
- Expiry: "Some builds will be removed soon" with count and days.
- RET7 digest: "Projects you haven't opened in a while".

## RET7 caveat for Zach
Cloudflare Email Service is transactional-only. A weekly digest is not transactional, so `send(..., "digest")` refuses unless
`ZEIM_EMAIL_DIGEST_ALLOWED=1` (meant for a different provider). Default off. **Not allowed on Cloudflare.**
