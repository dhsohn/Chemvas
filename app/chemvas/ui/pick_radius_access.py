from __future__ import annotations

from chemvas.ui.renderer_style_access import bond_length_px_for, renderer_for


def atom_pick_radius(renderer) -> float:
    base_radius = max(0.6, renderer.style.bond_line_width * 0.6)
    return max(base_radius, renderer.style.bond_length_px * 0.32)


def atom_pick_radius_for(canvas) -> float:
    return atom_pick_radius(renderer_for(canvas))


def bond_pick_radius_for(canvas) -> float:
    return bond_length_px_for(canvas) * 0.528


__all__ = ["atom_pick_radius_for", "bond_pick_radius_for"]
