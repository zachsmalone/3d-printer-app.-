"""Image moderation hook for user photos (e.g. "I printed this").

Pluggable on purpose: swap `review_upload` for a real checker later (hash lists,
local model, etc.). Default always returns needs_human_review and NEVER
auto-approves. No paid APIs.
"""
from __future__ import annotations

from typing import Callable

# Outcomes a hook may return. "approve" is reserved for a future real checker;
# the default hook never returns it, and callers must not treat it as a shortcut
# past the moderator queue today.
NEEDS_HUMAN_REVIEW = "needs_human_review"
REJECT = "reject"
APPROVE = "approve"          # not used by the default; kept so a future plug-in can signal

ReviewFn = Callable[[bytes, dict], str]

_hook: ReviewFn | None = None


def default_review(data: bytes, meta: dict | None = None) -> str:
    """Safe default: every upload needs a human. Never auto-approves."""
    return NEEDS_HUMAN_REVIEW


def set_review_hook(fn: ReviewFn | None) -> None:
    """Tests / future integrations: replace the hook. Pass None to restore the default."""
    global _hook
    _hook = fn


def review_upload(data: bytes, meta: dict | None = None) -> str:
    """Run the current hook on uploaded image bytes. Meta may hold item_id, owner, etc."""
    fn = _hook or default_review
    result = fn(data, meta or {})
    if result not in (NEEDS_HUMAN_REVIEW, REJECT, APPROVE):
        return NEEDS_HUMAN_REVIEW
    return result
