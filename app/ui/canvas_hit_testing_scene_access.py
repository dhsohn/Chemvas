from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTransform

from ui.scene_item_access import canvas_scene_for


def scene_items_at_pos_for_canvas(canvas, pos):
    return canvas_scene_for(canvas).items(
        pos,
        Qt.ItemSelectionMode.IntersectsItemShape,
        Qt.SortOrder.DescendingOrder,
        QTransform(),
    )


__all__ = ["scene_items_at_pos_for_canvas"]
