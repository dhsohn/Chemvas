from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QPen
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem

from ui.canvas_scene_items_state import (
    add_selected_note_for,
    clear_selected_notes_for,
    remove_selected_note_for,
    selected_notes_for,
)
from ui.canvas_text_style_state import text_style_state_for
from ui.graphics_items import NoSelectRectItem
from ui.scene_group_operations import (
    deselect_groups_for_note_for,
    expand_note_selection_to_groups_for,
    notes_only_group_member_notes_for,
)
from ui.selection_service_access import refresh_selection_outline_for
from ui.selection_style_access import selection_color_for, selection_stroke_delta_for

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class SelectionNoteService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def select_note(self, item: QGraphicsTextItem, additive: bool = False) -> None:
        if not additive:
            self.clear_note_selection()
        changed = item not in selected_notes_for(self.canvas)
        add_selected_note_for(self.canvas, item)
        self.update_note_selection_box(item)
        if changed:
            expand_note_selection_to_groups_for(self.canvas, item)
            self._refresh_outline_for_note_change()

    def toggle_note_selection(self, item: QGraphicsTextItem) -> None:
        if item in selected_notes_for(self.canvas):
            remove_selected_note_for(self.canvas, item)
            self._deselect_grouped_note_companions(item)
        else:
            add_selected_note_for(self.canvas, item)
            expand_note_selection_to_groups_for(self.canvas, item)
        self.update_note_selection_box(item)
        self._refresh_outline_for_note_change()

    def set_note_selected(self, item: QGraphicsTextItem, selected: bool) -> None:
        is_selected = item in selected_notes_for(self.canvas)
        if selected == is_selected:
            return
        if selected:
            add_selected_note_for(self.canvas, item)
            expand_note_selection_to_groups_for(self.canvas, item)
        else:
            remove_selected_note_for(self.canvas, item)
            self._deselect_grouped_note_companions(item)
        self.update_note_selection_box(item)
        self._refresh_outline_for_note_change()

    def _deselect_grouped_note_companions(self, item: QGraphicsTextItem) -> None:
        # A notes-only group deselects as a unit, mirroring the select-direction
        # expansion; otherwise Ctrl-clicking one member leaves a partial group
        # that delete/copy/drag would silently act on.
        for member in notes_only_group_member_notes_for(self.canvas, item):
            if member is item or member not in selected_notes_for(self.canvas):
                continue
            remove_selected_note_for(self.canvas, member)
            self.update_note_selection_box(member)
        # Mixed groups deselect as a unit too: the group box spans attached
        # members, so leaving the scene members selected would keep a box over
        # a note that a drag no longer moves.
        deselect_groups_for_note_for(self.canvas, item)

    def _refresh_outline_for_note_change(self) -> None:
        # Note selection lives outside QGraphicsScene selection, so it never
        # emits selectionChanged; refresh explicitly or a notes-only group box
        # would linger after the note selection is cleared (e.g. switching to
        # the bond tool).
        refresh_selection_outline_for(self.canvas)

    def apply_group_note_toggle(
        self,
        notes: list[QGraphicsItem],
        selected: bool | None,
    ) -> None:
        """Select or deselect grouped notes as a unit.

        ``selected`` mirrors the group's structure members; pass ``None`` when the
        group has no selectable scene members so the direction is decided from the
        notes' own current state.
        """
        if not notes:
            return
        if selected is None:
            current = selected_notes_for(self.canvas)
            selected = not all(note in current for note in notes)
        for note in notes:
            self.set_note_selected(cast(QGraphicsTextItem, note), selected)

    def clear_note_selection(self) -> None:
        notes = list(selected_notes_for(self.canvas))
        clear_selected_notes_for(self.canvas)
        for note in notes:
            self.update_note_selection_box(note)
        for note in notes:
            # Mixed groups deselect as a unit: without this, clearing the note
            # selection (e.g. NoteTool press on empty canvas) would leave the
            # group's scene members selected and the box spanning notes that a
            # drag no longer moves.
            deselect_groups_for_note_for(self.canvas, note)
        if notes:
            self._refresh_outline_for_note_change()

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
