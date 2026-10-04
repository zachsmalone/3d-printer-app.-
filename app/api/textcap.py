"""Length caps for every text input, applied BEFORE any regex/word-list work (Safety S-02 / bug B-02)."""
from __future__ import annotations

from fastapi import Request

# Hard ceilings (characters). Individual fields use smaller caps via text_in().
MAX_JSON_BODY = 256 * 1024


def text_in(value, max_len: int, label: str = "Text") -> str:
    """Return `value` as a stripped string, or raise ValueError('<label> is too long (max N characters).').
    Never scans or slices a longer string first: the length check is O(1)."""
    if value is None:
        return ""
    if not isinstance(value, str):
        if isinstance(value, (int, float)):
            value = str(value)
        else:
            raise ValueError(f"{label} must be text.")
    if len(value) > max_len:
        raise ValueError(f"{label} is too long (max {max_len} characters).")
    return value.strip()


def ip(request: Request) -> str:
    """Client address as the server sees it (behind a proxy run uvicorn with --proxy-headers)."""
    return request.client.host if request.client else "unknown"
