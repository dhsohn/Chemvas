from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QGraphicsItemGroup

from chemvas.ui.canvas_service_ports import selection_highlight_styler_for_access
from chemvas.ui.selection_style_access import (
    selected_highlight_items_for,
    selection_color_for,
    selection_stroke_delta_for,
    set_selected_highlight_items_for,
)

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


class SelectionHighlightStyler:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def set_selection_highlight(self, items: list) -> None:
        self.clear_selection_highlight()
        set_selected_highlight_items_for(self.canvas, items)
        for item in items:
            self.apply_selection_style(item, True)

    def clear_selection_highlight(self) -> None:
        for item in selected_highlight_items_for(self.canvas):
            self.apply_selection_style(item, False)
        set_selected_highlight_items_for(self.canvas, [])

    def apply_selection_style(self, item, selected: bool) -> None:
        if isinstance(item, QGraphicsItemGroup):
            for child in item.childItems():
                self.apply_selection_style(child, selected)
            return
        if not hasattr(item, "pen"):
            return
        pen = item.pen()
        if selected:
            item.setData(6, pen)
            pen.setColor(selection_color_for(self.canvas))
            pen.setWidthF(pen.widthF() + selection_stroke_delta_for(self.canvas))
            item.setPen(pen)
            return
        original = item.data(6)
        if isinstance(original, QPen):
            item.setPen(original)


def selection_highlight_styler_for(canvas) -> SelectionHighlightStyler:
    return selection_highlight_styler_for_access(canvas)


__all__ = ["SelectionHighlightStyler", "selection_highlight_styler_for"]
