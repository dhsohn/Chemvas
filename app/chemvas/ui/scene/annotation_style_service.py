from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsEllipseItem

from chemvas.ui.annotations.state import arrow_state_dict_for
from chemvas.ui.canvas.canvas_scene_items_state import (
    arrow_items_for,
    orbital_items_for,
)
from chemvas.ui.canvas.canvas_tool_settings_state import set_tool_setting_for


def apply_annotation_style_for(canvas, values: dict[str, float | bool]) -> None:
    """Apply document-wide annotation settings without replacing scene identities."""
    for name, value in values.items():
        set_tool_setting_for(canvas, name, value)
    if {"arrow_line_width", "arrow_head_scale"} & values.keys():
        for item in arrow_items_for(canvas):
            # Curved state application refreshes its path in place, retaining
            # the pen. Update the common width while keeping dash/color flags.
            pen = item.pen()
            pen.setWidthF(canvas.runtime_state.tool_settings_state.arrow_line_width)
            item.setPen(pen)
            canvas.services.scene_item_controller.apply_scene_item_state(
                item, arrow_state_dict_for(canvas, item)
            )
    if "orbital_phase_enabled" in values:
        for item in orbital_items_for(canvas):
            rebuilt = (
                canvas.services.scene_decoration_build_service.build_orbital_items(
                    QPointF(), item.data(2)["kind"]
                )
            )
            existing_lobes = [
                child
                for child in item.childItems()
                if isinstance(child, QGraphicsEllipseItem)
            ]
            rebuilt_lobes = [
                child for child in rebuilt if isinstance(child, QGraphicsEllipseItem)
            ]
            for child, template in zip(existing_lobes, rebuilt_lobes, strict=True):
                child.setBrush(template.brush())
    canvas.services.selection.update_selection_outline()
    callback = canvas.runtime_state.callback_state.tool_change
    if callback is not None:
        callback()


__all__ = ["apply_annotation_style_for"]
