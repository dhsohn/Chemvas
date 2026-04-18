from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QGraphicsItemGroup

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class SelectionHighlightStyler:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def set_selection_highlight(self, items: list) -> None:
        self.clear_selection_highlight()
        self.canvas._selected_items = items
        for item in items:
            self.apply_selection_style(item, True)

    def clear_selection_highlight(self) -> None:
        for item in self.canvas._selected_items:
            self.apply_selection_style(item, False)
        self.canvas._selected_items = []

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
            pen.setColor(self.canvas._selection_color)
            pen.setWidthF(pen.widthF() + self.canvas._selection_stroke_delta)
            item.setPen(pen)
            return
        original = item.data(6)
        if isinstance(original, QPen):
            item.setPen(original)


def selection_highlight_styler_for(canvas) -> SelectionHighlightStyler:
    styler = getattr(canvas, "_selection_highlight_styler", None)
    if isinstance(styler, SelectionHighlightStyler) and styler.canvas is canvas:
        return styler
    if styler is not None and all(
        hasattr(styler, name)
        for name in ("set_selection_highlight", "clear_selection_highlight", "apply_selection_style")
    ):
        return styler
    return SelectionHighlightStyler(canvas)


__all__ = ["SelectionHighlightStyler", "selection_highlight_styler_for"]
