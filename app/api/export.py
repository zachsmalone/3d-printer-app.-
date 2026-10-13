"""Universal export API endpoints: 'Export for my printer'."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.builds import meta_for
from app.community.identity import Actor, get_actor
from app.services import print_setup as ps
from app.services import universal_export as ue

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/hints")
def get_slicer_hints(printer_id: str = Query("", description="Optional printer ID for official slicer matching")):
    hints = ue.get_open_in_hints(printer_id or None)
    return {"hints": hints, "count": len(hints)}


@router.get("/{bid}")
def get_export_info(
    bid: str,
    printer_id: str = Query("", description="Optional printer ID (defaults to account setting)"),
    actor: Actor = Depends(get_actor),
):
    """Metadata and URLs for 'Export for my printer'."""
    meta = meta_for(bid, actor, owner_only=True)
    pref_pid = printer_id
    if not pref_pid:
        if actor.user and actor.user.get("printer", {}).get("printer_id"):
            pref_pid = actor.user["printer"]["printer_id"]
        else:
            pref_pid = ps.DEFAULT_PRINTER

    try:
        p = ps.printer_public(pref_pid)
    except Exception:
        pref_pid = ps.DEFAULT_PRINTER
        p = ps.printer_public(pref_pid)

    fn_3mf = ue.format_export_filename(bid, meta.get("title"), pref_pid, "3mf")
    fn_stl = ue.format_export_filename(bid, meta.get("title"), pref_pid, "stl")

    return {
        "build_id": bid,
        "title": meta.get("title", ""),
        "printer": {
            "id": pref_pid,
            "name": p["name"],
            "bed_mm": p["bed_mm"],
            "official_slicer": p.get("official_slicer"),
            "official_slicer_url": p.get("official_slicer_url"),
        },
        "filename": fn_3mf,
        "filename_fallback": fn_stl,
        "downloads": {
            "3mf": f"/api/export/{bid}/download?format=3mf&printer_id={pref_pid}",
            "stl": f"/api/export/{bid}/download?format=stl&printer_id={pref_pid}",
        },
        "open_in_hints": ue.get_open_in_hints(pref_pid),
    }


@router.get("/{bid}/download")
def download_export(
    bid: str,
    format: str = Query("3mf", regex="^(3mf|stl)$"),
    printer_id: str = Query("", description="Optional printer ID (defaults to account setting)"),
    actor: Actor = Depends(get_actor),
):
    """Download universal export sized and named for the printer (3MF with STL fallback)."""
    pref_pid = printer_id
    if not pref_pid:
        if actor.user and actor.user.get("printer", {}).get("printer_id"):
            pref_pid = actor.user["printer"]["printer_id"]
        else:
            pref_pid = ps.DEFAULT_PRINTER

    try:
        data, filename, ext, mime, info = ue.export_build_for_printer(
            bid, actor, printer_id=pref_pid, force_format=format
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Could not export model: {e}")

    return Response(
        content=data,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Export-Printer": info["printer_id"],
            "X-Export-Format": ext,
        },
    )
