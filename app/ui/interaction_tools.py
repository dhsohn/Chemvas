from __future__ import annotations

from core.tool_overlay_logic import activate_tool_no_drag, clear_temporary_tool_overlay
from PyQt6.QtCore import Qt

from ui.handle_overlay_access import (
    clear_handles_for,
    show_curved_handles_for,
    show_orbital_handles_for,
)
from ui.renderer_style_access import bond_length_px_for
from ui.scene_decoration_access import add_mark_for, add_mark_for_atom_for
from ui.selection_service_access import (
    clear_note_selection_for,
    select_note_for,
    toggle_note_selection_for,
)
from ui.tool_base import Tool


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
            select_note_for(self.canvas, item, additive=False)
            self.context.begin_note_edit(item)
            return True
        pos = self.context.scene_pos_from_event(event)
        clear_note_selection_for(self.canvas)
        item = self.context.create_text_note(pos, "")
        self.context.begin_note_edit(item)
        return True

    def on_mouse_move(self, event) -> bool:
        return False

    def on_mouse_release(self, event) -> bool:
        self._active_handle = None
        return False


__all__ = ["MarkTool", "NoteTool", "TransformTool"]
