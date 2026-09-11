from __future__ import annotations

from typing import override

from PyQt6.QtCore import Qt

from chemvas.core.tool_overlay_logic import activate_tool_no_drag
from chemvas.ui.mark_item_access import find_atom_for_mark_for
from chemvas.ui.scene_decoration_access import add_mark_for, add_mark_for_atom_for
from chemvas.ui.selection_service_access import (
    clear_note_selection_for,
    select_note_for,
    toggle_note_selection_for,
)
from chemvas.ui.tool_base import Tool


class MarkTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("mark", canvas, context=context)

    @override
    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    @override
    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = self.context.scene_pos_from_event(event)
        atom_id = find_atom_for_mark_for(self.canvas, pos)
        if atom_id is not None:
            add_mark_for_atom_for(self.canvas, atom_id, pos)
        else:
            add_mark_for(self.canvas, pos)
        return True


class NoteTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("note", canvas, context=context)
        self._active_handle = None

    @override
    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    @override
    def deactivate(self) -> None:
        self.context.finish_note_edit()

    @override
    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.context.item_at_event(event)
        if item is not None and item.data(0) == "note":
            if item.hasFocus():
                # Let Qt receive the whole gesture, including the press that
                # starts a drag selection, shift-click or double-click.
                return False
            modifiers = event.modifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                toggle_note_selection_for(self.canvas, item)
                return True
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                select_note_for(self.canvas, item, additive=True)
                return True
            select_note_for(self.canvas, item, additive=False)
            self.context.begin_note_edit(item)
            return True
        pos = self.context.scene_pos_from_event(event)
        clear_note_selection_for(self.canvas)
        item = self.context.create_text_note(pos, "")
        self.context.begin_note_edit(item)
        return True

    @override
    def on_mouse_move(self, event) -> bool:
        return False

    @override
    def on_mouse_release(self, event) -> bool:
        self._active_handle = None
        return False


__all__ = ["MarkTool", "NoteTool"]
