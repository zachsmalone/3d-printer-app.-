"""ZEIM account security: passkeys (WebAuthn), passwords, email one-time codes, server-side sessions.

Passwords are stored as Argon2id hashes only. Emails are never stored in plain text
(only a keyed hash + a masked hint).
"""
