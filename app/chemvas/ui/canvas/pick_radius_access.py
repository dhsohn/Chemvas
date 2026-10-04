from __future__ import annotations

STRUCTURE_BOND_PICK_RADIUS_RATIO = 0.528


def atom_pick_radius(renderer) -> float:
    base_radius = max(0.6, renderer.style.bond_line_width * 0.6)
    return max(base_radius, renderer.style.bond_length_px * 0.32)


def atom_pick_radius_for(canvas) -> float:
    return atom_pick_radius(canvas.renderer)


__all__ = ["atom_pick_radius_for"]
