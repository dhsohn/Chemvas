from __future__ import annotations

from chemvas.ui.renderer_style_access import bond_length_px_for, bond_line_width_for


def atom_pick_radius_for(canvas) -> float:
    try:
        base_radius = max(0.6, bond_line_width_for(canvas) * 0.6)
        return max(base_radius, bond_length_px_for(canvas) * 0.32)
    except AttributeError:
        pass
    return 0.0


def bond_pick_radius_for(canvas) -> float:
    try:
        return bond_length_px_for(canvas) * 0.528
    except AttributeError:
        pass
    return 0.0


__all__ = ["atom_pick_radius_for", "bond_pick_radius_for"]
