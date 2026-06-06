from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QPen
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem

from ui.canvas_scene_items_state import (
    add_selected_note_for,
    clear_selected_notes_for,
    remove_selected_note_for,
    selected_notes_for,
)
from ui.canvas_text_style_state import text_style_state_for
from ui.graphics_items import NoSelectRectItem
from ui.selection_style_access import selection_color_for, selection_stroke_delta_for

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class SelectionNoteService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def select_note(self, item: QGraphicsTextItem, additive: bool = False) -> None:
        if not additive:
            self.clear_note_selection()
        add_selected_note_for(self.canvas, item)
        self.update_note_selection_box(item)

    def toggle_note_selection(self, item: QGraphicsTextItem) -> None:
        if item in selected_notes_for(self.canvas):
            remove_selected_note_for(self.canvas, item)
        else:
            add_selected_note_for(self.canvas, item)
        self.update_note_selection_box(item)

    def clear_note_selection(self) -> None:
        notes = list(selected_notes_for(self.canvas))
        clear_selected_notes_for(self.canvas)
        for note in notes:
            self.update_note_selection_box(note)

    def update_note_selection_box(self, item: QGraphicsTextItem) -> None:
        sel = item.data(21)
        padding = text_style_state_for(self.canvas).note_padding
        rect = item.boundingRect().adjusted(
            -padding,
            -padding,
            padding,
            padding,
        )
        selected = item in selected_notes_for(self.canvas)
        if not selected:
            if isinstance(sel, QGraphicsRectItem):
                sel.setVisible(False)
            return
        if not isinstance(sel, QGraphicsRectItem):
            sel = NoSelectRectItem(item)
            sel.setData(0, "note_select")
            sel.setZValue(1)
            item.setData(21, sel)
        sel.setVisible(True)
        sel.setRect(rect)
        pen = QPen(selection_color_for(self.canvas))
        pen.setWidthF(selection_stroke_delta_for(self.canvas))
        pen.setStyle(Qt.PenStyle.DashLine)
        sel.setPen(pen)
        sel.setBrush(QBrush(Qt.BrushStyle.NoBrush))


__all__ = ["SelectionNoteService"]
