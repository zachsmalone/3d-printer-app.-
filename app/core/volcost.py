"""Material and cost estimate from mesh volume (Edit upgrade 6).

Uses the same density table as print_setup. Price is optional user input
(currency-agnostic); we report grams and cost = grams * price_per_kg / 1000.
"""
from __future__ import annotations

from ..services.print_setup import DENSITY_G_CM3, DEFAULT_DENSITY, density_of


# Default retail-ish price hints (USD/kg). Estimates only — brands vary a lot.
DEFAULT_PRICE_PER_KG = {
    "PLA": 20.0, "PETG": 25.0, "TPU": 35.0, "ABS": 22.0, "ASA": 28.0, "PC": 40.0,
    "PVA": 45.0, "HIPS": 25.0,
}


def estimate(mesh, material: str = "PLA", price_per_kg: float | None = None,
             infill_pct: float = 20.0, wall_factor: float = 1.15) -> dict:
    """Approximate filament grams and cost from solid volume.

    Solid volume is scaled by (infill/100) * wall_factor to account for shells.
    wall_factor ~1.15 is a rough extra for perimeters on typical FDM parts.
    """
    mat = (material or "PLA").upper().split()[0]
    # Map library ids like pla_plus -> PLA
    for key in DENSITY_G_CM3:
        if mat.startswith(key) or key.startswith(mat[:3]):
            mat = key
            break
    dens = density_of(mat)
    vol_mm3 = float(getattr(mesh, "volume", 0) or 0)
    if vol_mm3 <= 0:
        return {"ok": False, "error": "Mesh has no positive volume (not watertight?)."}
    vol_cm3 = vol_mm3 / 1000.0
    fill = max(0.0, min(100.0, float(infill_pct))) / 100.0
    wf = max(0.5, min(2.0, float(wall_factor)))
    used_cm3 = vol_cm3 * fill * wf
    # Cap at solid: can't use more filament than the solid volume
    used_cm3 = min(used_cm3, vol_cm3)
    grams = used_cm3 * dens
    price = float(price_per_kg) if price_per_kg is not None else DEFAULT_PRICE_PER_KG.get(mat, 25.0)
    cost = grams * price / 1000.0
    return {
        "ok": True,
        "material": mat,
        "density_g_cm3": dens,
        "volume_mm3": round(vol_mm3, 2),
        "volume_cm3": round(vol_cm3, 3),
        "infill_pct": round(fill * 100, 1),
        "wall_factor": wf,
        "used_cm3": round(used_cm3, 3),
        "grams": round(grams, 2),
        "price_per_kg": price,
        "cost": round(cost, 2),
        "note": (
            f"About {grams:.1f} g of {mat} (~{cost:.2f} at ${price:g}/kg). "
            f"Uses solid volume × {fill*100:.0f}% infill × {wf:g} wall factor. "
            "Real use varies with walls, supports, and brand density."
        ),
    }
