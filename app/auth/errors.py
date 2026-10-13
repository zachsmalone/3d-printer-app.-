from __future__ import annotations


class AuthError(Exception):
    """Friendly, machine-coded error. `message` is safe to show to the user."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class RateLimited(AuthError):
    def __init__(self, retry_after: int, message: str = "Too many attempts. Please wait a bit and try again."):
        super().__init__("rate_limited", message, 429)
        self.retry_after = max(1, int(retry_after))
