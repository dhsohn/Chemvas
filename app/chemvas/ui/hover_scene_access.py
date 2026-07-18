from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtWidgets import QGraphicsItem

from chemvas.ui.hover_scene_renderer import (
    add_hover_preview_items as add_hover_preview_items_helper,
)
from chemvas.ui.hover_scene_renderer import (
    clear_hover_items as clear_hover_items_helper,
)
from chemvas.ui.scene_item_access import add_item_to_canvas_scene, canvas_scene_for


def clear_hover_items_for(
    canvas, items: Sequence[QGraphicsItem]
) -> list[QGraphicsItem]:
    return clear_hover_items_helper(canvas_scene_for(canvas), items)


def add_hover_preview_items_to_scene_for(
    canvas, items: Sequence[QGraphicsItem]
) -> list[QGraphicsItem]:
    return add_hover_preview_items_helper(canvas_scene_for(canvas), items)


def add_hover_scene_item_for(canvas, item: QGraphicsItem):
    return add_item_to_canvas_scene(canvas, item)


__all__ = [
    "add_hover_preview_items_to_scene_for",
    "add_hover_scene_item_for",
    "clear_hover_items_for",
]
