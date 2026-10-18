"""Licence picker for showcase projects (docs/specs/showcase-gaps.md, item 1).

A fixed menu modelled on the standard creator-site convention (Cults' licence page):
CC BY / BY-SA / BY-NC / BY-NC-SA / BY-NC-ND / CC0, plus "Private use" as the default
for NEW projects. Every new project gets one of these (default `private-use`); legacy
projects with no `license_id` stay unspecified until their maker edits the project —
no default is applied retroactively.

Permissions are explicit, never inferred:
- ND licences (BY-ND, BY-NC-ND) forbid publishing adaptations — `may_remix` is False.
- "Private use" grants nothing beyond personal printing/gifting — `may_remix` is False.
- Unset (legacy) grants nothing either — remixing it is refused, not silently allowed.

This module holds the data + rules; enforcement lives at the shared publishing boundary
(`catalog.create_project`) so every route that publishes goes through it.
"""
from __future__ import annotations

LICENSES: dict[str, dict] = {
    "cc0-1.0": dict(name="CC0 1.0", url="https://creativecommons.org/publicdomain/zero/1.0/",
                    derivatives=True, commercial=True,
                    blurb="Public-domain dedication: anyone may share, remix and sell it, no credit needed."),
    "cc-by-4.0": dict(name="CC BY 4.0", url="https://creativecommons.org/licenses/by/4.0/",
                      derivatives=True, commercial=True,
                      blurb="Anyone may share, remix and sell it, with credit to you."),
    "cc-by-sa-4.0": dict(name="CC BY-SA 4.0", url="https://creativecommons.org/licenses/by-sa/4.0/",
                         derivatives=True, commercial=True,
                         blurb="Like CC BY, but remixes must carry the same licence."),
    "cc-by-nd-4.0": dict(name="CC BY-ND 4.0", url="https://creativecommons.org/licenses/by-nd/4.0/",
                         derivatives=False, commercial=True,
                         blurb="Share it with credit, but no remixes or edits of it."),
    "cc-by-nc-4.0": dict(name="CC BY-NC 4.0", url="https://creativecommons.org/licenses/by-nc/4.0/",
                         derivatives=True, commercial=False,
                         blurb="Anyone may remix with credit, for non-commercial use only."),
    "cc-by-nc-sa-4.0": dict(name="CC BY-NC-SA 4.0", url="https://creativecommons.org/licenses/by-nc-sa/4.0/",
                            derivatives=True, commercial=False,
                            blurb="Non-commercial remixes with credit, same licence for them."),
    "cc-by-nc-nd-4.0": dict(name="CC BY-NC-ND 4.0", url="https://creativecommons.org/licenses/by-nc-nd/4.0/",
                            derivatives=False, commercial=False,
                            blurb="Non-commercial sharing with credit, no remixes."),
    "private-use": dict(name="Private use", url="",
                       derivatives=False, commercial=False,
                       blurb="Keep it personal: print it, gift it, keep it to yourself and this site."),
}
DEFAULT = "private-use"          # applied to NEW projects only; legacy unset stays unset


def menu() -> list[dict]:
    """The picker the publish form shows: every entry + the default flag (order = display order)."""
    return [dict(id=k, default=(k == DEFAULT), **v) for k, v in LICENSES.items()]


def check(license_id) -> str:
    """Validated licence id. None/'' -> DEFAULT (new projects); unknown ids raise ValueError."""
    if license_id in (None, ""):
        return DEFAULT
    if not isinstance(license_id, str) or license_id not in LICENSES:
        raise ValueError("unknown licence: pick one from the licence list")
    return license_id


def describe(license_id) -> dict | None:
    """Public licence info for an item payload: None when the project predates the picker."""
    lid = license_id if isinstance(license_id, str) else ""
    if lid not in LICENSES:
        return None
    return dict(id=lid, **LICENSES[lid])


def may_remix(license_id) -> bool:
    """True only when the SOURCE licence explicitly allows publishing adaptations.

    ND, Private use, unset (legacy) and unknown licences all return False: permission to
    redistribute an adaptation is never inferred from absence of a licence.
    """
    return isinstance(license_id, str) and LICENSES.get(license_id, {}).get("derivatives") is True
