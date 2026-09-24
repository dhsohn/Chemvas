"""Read-only ownership feedback; moving a glyph never changes its atom."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from chemvas.ui.canvas.canvas_model_access import atom_for_id

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem

    from chemvas.ui.canvas.canvas_view import CanvasView


def mark_is_distant_for(canvas: CanvasView, item: QGraphicsItem) -> bool:
    data = item.data(1) or {}
    atom_id = data.get("atom_id")
    if not isinstance(atom_id, int):
        return False
    atom = atom_for_id(canvas, atom_id)
    if atom is None:
        return False
    center = canvas.services.scene_decoration_build_service.mark_center(item)
    dx, dy = center.x() - atom.x, center.y() - atom.y
    distance = math.hypot(dx, dy)
    if distance == 0:
        return False
    length = canvas.renderer.style.bond_length_px
    # A long alias has a legitimate label-aware offset. This is a visual
    # warning threshold, not a binding radius or a chemical validation rule.
    label_offset = canvas.render_context.geometry.mark_target_distance_for_atom(
        atom_id, dx / distance, dy / distance, data.get("kind", "plus")
    )
    return distance > max(length, label_offset + length * 0.5)


def mark_owner_text_for(canvas: CanvasView, item: QGraphicsItem) -> str:
    atom_id = (item.data(1) or {}).get("atom_id")
    atom = atom_for_id(canvas, atom_id)
    if atom is None:
        return "Free mark (no chemical owner)"
    warning = " — far from owner" if mark_is_distant_for(canvas, item) else ""
    return f"Owner: {atom.element} #{atom_id}{warning}"
