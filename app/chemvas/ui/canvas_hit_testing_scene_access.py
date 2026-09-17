from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTransform

from chemvas.ui.scene_item_access import canvas_scene_for


def scene_items_at_pos_for_canvas(canvas, pos):
    # Handles keep their size on screen (ItemIgnoresTransformations), so the
    # scene needs the view's transform to place their shapes for picking.
    return canvas_scene_for(canvas).items(
        pos,
        Qt.ItemSelectionMode.IntersectsItemShape,
        Qt.SortOrder.DescendingOrder,
        canvas.viewportTransform(),
    )


def scene_items_in_rect_for_canvas(canvas, rect):
    return canvas_scene_for(canvas).items(
        rect,
        Qt.ItemSelectionMode.IntersectsItemBoundingRect,
        Qt.SortOrder.DescendingOrder,
        QTransform(),
    )


__all__ = ["scene_items_at_pos_for_canvas", "scene_items_in_rect_for_canvas"]
