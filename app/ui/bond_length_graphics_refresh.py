from __future__ import annotations

from PyQt6.QtCore import Qt

from ui.atom_label_access import atom_label_service, uses_compact_label_hit_shape_for
from ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from ui.canvas_bond_graphics_state import bond_items_for, bond_items_for_id
from ui.canvas_bond_renderer_state import update_bond_geometry_for
from ui.canvas_model_access import atoms_for, bonds_for
from ui.graphics_items import AtomDotItem, AtomLabelItem
from ui.pick_radius_access import atom_pick_radius_for
from ui.renderer_style_access import (
    atom_font_for,
    bond_length_px_for,
    bond_line_width_for,
    renderer_bond_line_width_for,
)
from ui.selection_service_access import refresh_selection_outline_for


def _refresh_atom_graphics(canvas) -> None:
    labels = atom_items_for(canvas)
    dots = atom_dots_for(canvas)
    if not labels and not dots:
        return
    label_service = atom_label_service(canvas) if labels else None
    font = atom_font_for(canvas)
    label_hit_padding = bond_length_px_for(canvas) * 0.12
    pick_radius = atom_pick_radius_for(canvas)
    dot_radius = max(0.6, bond_line_width_for(canvas) * 0.6)

    for atom_id, atom in atoms_for(canvas).items():
        label = labels.get(atom_id)
        if label is not None:
            if isinstance(label, AtomLabelItem):
                label.set_hit_padding(label_hit_padding)
                label.set_hit_radius(
                    pick_radius if uses_compact_label_hit_shape_for(canvas, atom.element) else None
                )
            label.setFont(font)
            if label_service is not None:
                label_service.position_label(label, atom.x, atom.y)

        dot = dots.get(atom_id)
        if isinstance(dot, AtomDotItem):
            dot.setRect(-dot_radius, -dot_radius, dot_radius * 2.0, dot_radius * 2.0)
            dot.set_hit_padding(max(0.0, pick_radius - dot_radius))
            dot.setPos(atom.x, atom.y)


def _refresh_bond_graphics(canvas) -> None:
    if not bond_items_for(canvas):
        return
    line_width = renderer_bond_line_width_for(canvas)
    for bond_id, bond in enumerate(bonds_for(canvas)):
        if bond is None:
            continue
        items = bond_items_for_id(canvas, bond_id)
        for item in items:
            pen_getter = getattr(item, "pen", None)
            pen_setter = getattr(item, "setPen", None)
            if not callable(pen_getter) or not callable(pen_setter):
                continue
            pen = pen_getter()
            if pen.style() == Qt.PenStyle.NoPen:
                continue
            pen.setWidthF(line_width)
            pen_setter(pen)
        update_bond_geometry_for(canvas, bond_id)


def refresh_bond_length_graphics_for(canvas) -> None:
    """Restyle model graphics after a bond-length change without replacing them."""

    _refresh_atom_graphics(canvas)
    _refresh_bond_graphics(canvas)
    refresh_selection_outline_for(canvas)


__all__ = ["refresh_bond_length_graphics_for"]
