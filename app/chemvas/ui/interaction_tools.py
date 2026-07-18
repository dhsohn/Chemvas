from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QTextCursor

from chemvas.core.tool_overlay_logic import (
    activate_tool_no_drag,
    clear_temporary_tool_overlay,
)
from chemvas.ui.handle_overlay_access import (
    clear_handles_for,
    show_curved_handles_for,
    show_orbital_handles_for,
    show_shape_handles_for,
)
from chemvas.ui.renderer_style_access import bond_length_px_for
from chemvas.ui.scene_decoration_access import add_mark_for, add_mark_for_atom_for
from chemvas.ui.selection_service_access import (
    clear_note_selection_for,
    select_note_for,
    toggle_note_selection_for,
)
from chemvas.ui.tool_base import Tool


class TransformTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("transform", canvas, context=context)
        self._active_handle = None

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def deactivate(self) -> None:
        clear_temporary_tool_overlay(
            self.canvas,
            clear_handles=True,
            clear_handles_callback=lambda: clear_handles_for(self.canvas),
        )
        self._active_handle = None

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.context.item_at_event(event)
        if item is None:
            clear_temporary_tool_overlay(
                self.canvas,
                clear_handles=True,
                clear_handles_callback=lambda: clear_handles_for(self.canvas),
            )
            self._active_handle = None
            return True
        if item.data(0) == "handle":
            self._active_handle = item
            return True
        self._active_handle = None
        kind = item.data(0)
        if kind == "orbital":
            show_orbital_handles_for(self.canvas, item)
        elif kind in {"curved_single", "curved_double"}:
            show_curved_handles_for(self.canvas, item)
        elif kind == "shape":
            show_shape_handles_for(self.canvas, item)
        else:
            clear_temporary_tool_overlay(
                self.canvas,
                clear_handles=True,
                clear_handles_callback=lambda: clear_handles_for(self.canvas),
            )
        return True


class MarkTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("mark", canvas, context=context)

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = self.context.scene_pos_from_event(event)
        atom_id = self.context.find_atom_near(
            pos.x(),
            pos.y(),
            bond_length_px_for(self.canvas) * 0.35,
        )
        if atom_id is not None:
            add_mark_for_atom_for(self.canvas, atom_id, pos)
        else:
            add_mark_for(self.canvas, pos)
        return True


class NoteTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("note", canvas, context=context)
        self._active_handle = None

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.context.item_at_event(event)
        if item is not None and item.data(0) == "note":
            modifiers = event.modifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                toggle_note_selection_for(self.canvas, item)
                return True
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                select_note_for(self.canvas, item, additive=True)
                return True
            if item.hasFocus():
                # Already editing this note: a single click repositions the caret
                # (clearing a double-click word selection) and a double-click selects
                # a word, like any text field.
                self._place_caret_in_note(item, event)
                return True
            select_note_for(self.canvas, item, additive=False)
            self.context.begin_note_edit(item)
            return True
        pos = self.context.scene_pos_from_event(event)
        clear_note_selection_for(self.canvas)
        item = self.context.create_text_note(pos, "")
        self.context.begin_note_edit(item)
        return True

    def _place_caret_in_note(self, item, event) -> None:
        document = item.document()
        cursor = item.textCursor()
        layout = document.documentLayout() if document is not None else None
        if layout is not None:
            local = item.mapFromScene(self.context.scene_pos_from_event(event))
            position = layout.hitTest(local, Qt.HitTestAccuracy.FuzzyHit)
            if position >= 0:
                cursor.setPosition(position)
        if event.type() == QEvent.Type.MouseButtonDblClick:
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        item.setTextCursor(cursor)

    def on_mouse_move(self, event) -> bool:
        return False

    def on_mouse_release(self, event) -> bool:
        self._active_handle = None
        return False


__all__ = ["MarkTool", "NoteTool", "TransformTool"]
