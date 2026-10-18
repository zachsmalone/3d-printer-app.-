"""Showcase additions (docs/specs/showcase-gaps.md): licence menu endpoint.

The licence is enforced at the shared publishing boundary (catalog.create_project); this
router only serves the menu the publish form renders. Sort and related items live on the
existing showcase routes in app/api/community.py (they extend existing endpoints).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..community import licensing
from ..community.identity import Actor, get_actor
from . import guards

router = APIRouter(prefix="/api")


@router.get("/showcase/licenses")
def licenses(actor: Actor = Depends(get_actor)):
    """The licence picker for publishing: every option + which one is the default."""
    guards.showcase_gate(actor)
    return {"licenses": licensing.menu(), "default": licensing.DEFAULT}
