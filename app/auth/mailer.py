"""Outgoing email for one-time codes. The address is only ever held in memory while sending."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Optional, Protocol

from app.auth.errors import AuthError
from app.auth.security import mask_email

log = logging.getLogger("zeim.auth.mail")


class Mailer(Protocol):
    def send(self, to: str, subject: str, text: str) -> None: ...


def code_email(code: str, minutes: int) -> tuple:
    subject = "Your ZEIM sign-in code"
    text = (f"Your ZEIM code is {code}\n\n"
            f"It works for {minutes} minutes and can be used once.\n"
            "If you didn't ask for this, you can ignore this email. Nobody can sign in without the code.\n"
            "ZEIM will never ask you for this code by phone or chat.\n")
    return subject, text


def password_reset_email(code: str, minutes: int) -> tuple:
    subject = "Your ZEIM password code"
    text = (f"Your ZEIM code is {code}\n\n"
            f"Use it to set a password on your account. It works for {minutes} minutes and can be used once.\n"
            "If you didn't ask for this, you can ignore this email. Your passkey still works.\n"
            "ZEIM will never ask you for this code by phone or chat.\n")
    return subject, text


class SmtpMailer:
    def __init__(self, host: str, port: int, sender: str, user: Optional[str] = None,
                 password: Optional[str] = None, starttls: bool = True, timeout: int = 15):
        self.host, self.port, self.sender = host, port, sender
        self.user, self.password, self.starttls, self.timeout = user, password, starttls, timeout

    def send(self, to: str, subject: str, text: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(text)
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as s:
            if self.starttls:
                s.starttls()
            if self.user:
                s.login(self.user, self.password or "")
            s.send_message(msg)


class ConsoleMailer:
    """DEV ONLY: prints the code (never the full address) so you can test without an SMTP server."""

    def send(self, to: str, subject: str, text: str) -> None:
        log.warning("[dev mail] to=%s | %s", mask_email(to), text.splitlines()[0])


class NullMailer:
    def send(self, to: str, subject: str, text: str) -> None:
        raise AuthError("email_unavailable", "Email sign-in isn't available right now. Please use your passkey.", 503)


def mailer_from_env(env) -> Mailer:
    if env.get("ZEIM_SMTP_HOST"):
        return SmtpMailer(env["ZEIM_SMTP_HOST"], int(env.get("ZEIM_SMTP_PORT", "587")),
                          env.get("ZEIM_SMTP_FROM", "ZEIM <no-reply@localhost>"), env.get("ZEIM_SMTP_USER"),
                          env.get("ZEIM_SMTP_PASSWORD"), env.get("ZEIM_SMTP_STARTTLS", "1") == "1")
    if env.get("ZEIM_ENV", "").lower() == "dev" and env.get("ZEIM_DEV_MAIL") == "console":
        return ConsoleMailer()
    return NullMailer()
