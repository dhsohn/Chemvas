from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF

from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas.pick_radius_access import atom_pick_radius_for
from chemvas.ui.selection.selection_queries import clear_scene_selection_for


def restore_selection_from_ids_for(
    canvas, atom_ids: set[int], bond_ids: set[int]
) -> None:
    if not clear_scene_selection_for(canvas):
        return
    atom_items = canvas.runtime_state.atom_graphics_state.atom_items
    atom_dots = canvas.runtime_state.atom_graphics_state.atom_dots
    for atom_id in atom_ids:
        item = atom_items.get(atom_id) or atom_dots.get(atom_id)
        if item is not None:
            item.setSelected(True)
    for bond_id in bond_ids:
        for item in canvas.runtime_state.bond_graphics_state.bond_items.get(
            bond_id, []
        ):
            item.setSelected(True)
    try:
        controller = canvas.services.selection
    except AttributeError:
        controller = None
    update_selection_outline = getattr(controller, "update_selection_outline", None)
    if callable(update_selection_outline):
        update_selection_outline()


def selection_bond_overlay_width_for(canvas, base_pen) -> float:
    return max(
        base_pen.widthF() + canvas.renderer.style.bond_spacing_px * 1.05,
        atom_pick_radius_for(canvas) * 0.75,
    )


def atom_center_point_for(canvas, atom_id: int):
    atom = canvas.model.atom_for_id(atom_id)
    if atom is None:
        return None
    return QPointF(atom.x, atom.y)


def selection_indicator_rect_for_atom_for(canvas, atom_id: int):
    atom = canvas.model.atom_for_id(atom_id)
    if atom is None:
        return None
    radius = atom_pick_radius_for(canvas)
    rect = QRectF(
        atom.x - radius,
        atom.y - radius,
        radius * 2.0,
        radius * 2.0,
    )
    item = visible_atom_item_for(canvas, atom_id)
    if item is not None:
        try:
            label_rect = item.sceneBoundingRect()
        except (RuntimeError, AttributeError):
            label_rect = None
        # Short element labels keep their circular indicator; only long free text
        # (multi-character labels that clearly overflow the circle) widen it so the
        # highlight covers the whole string.
        if (
            label_rect is not None
            and not label_rect.isEmpty()
            and label_rect.width() > rect.width() * 3.0
        ):
            rect = rect.united(label_rect)
    return rect


__all__ = [
    "atom_center_point_for",
    "restore_selection_from_ids_for",
    "selection_bond_overlay_width_for",
    "selection_indicator_rect_for_atom_for",
]
