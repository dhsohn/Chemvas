from __future__ import annotations

from PyQt6.QtCore import QRectF

from ui.canvas_atom_graphics_state import (
    atom_dots_for,
    atom_items_for,
    visible_atom_item_for,
)
from ui.canvas_bond_graphics_state import bond_items_for
from ui.canvas_model_access import atom_for_id
from ui.pick_radius_access import atom_pick_radius_for
from ui.renderer_style_access import bond_spacing_px_for
from ui.selection_scene_access import clear_scene_selection_for
from ui.selection_service_access import selection_service_from_canvas
from ui.selection_style_state import selection_style_state_for


def selected_highlight_items_for(canvas) -> list:
    return selection_style_state_for(canvas).selected_items


def set_selected_highlight_items_for(canvas, items: list) -> None:
    selection_style_state_for(canvas).selected_items = items


def selection_color_for(canvas):
    return selection_style_state_for(canvas).color


def selection_stroke_delta_for(canvas) -> float:
    return float(selection_style_state_for(canvas).stroke_delta)


def suspend_selection_outline_for(canvas) -> bool:
    return bool(selection_style_state_for(canvas).suspend_outline)


def emit_selection_info_for(canvas) -> None:
    from ui.selection_info_access import emit_selection_info_for as emit_selection_info

    emit_selection_info(canvas)


def restore_selection_from_ids_for(canvas, atom_ids: set[int], bond_ids: set[int]) -> None:
    if not clear_scene_selection_for(canvas):
        return
    atom_items = atom_items_for(canvas)
    atom_dots = atom_dots_for(canvas)
    for atom_id in atom_ids:
        item = atom_items.get(atom_id) or atom_dots.get(atom_id)
        if item is not None:
            item.setSelected(True)
    for bond_id in bond_ids:
        for item in bond_items_for(canvas).get(bond_id, []):
            item.setSelected(True)
    try:
        controller = selection_service_from_canvas(canvas)
    except AttributeError:
        controller = None
    update_selection_outline = getattr(controller, "update_selection_outline", None)
    if callable(update_selection_outline):
        update_selection_outline()


def selection_bond_overlay_width_for(canvas, base_pen) -> float:
    return max(
        base_pen.widthF() + bond_spacing_px_for(canvas) * 1.05,
        atom_pick_radius_for(canvas) * 0.75,
    )


def selection_indicator_rect_for_atom_for(canvas, atom_id: int):
    atom = atom_for_id(canvas, atom_id)
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
    "emit_selection_info_for",
    "restore_selection_from_ids_for",
    "selected_highlight_items_for",
    "selection_bond_overlay_width_for",
    "selection_color_for",
    "selection_indicator_rect_for_atom_for",
    "selection_stroke_delta_for",
    "set_selected_highlight_items_for",
    "suspend_selection_outline_for",
]
