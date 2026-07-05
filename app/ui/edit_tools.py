from __future__ import annotations

from core.tool_overlay_logic import activate_tool_no_drag
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from ui.canvas_smiles_input_state import last_smiles_input_for
from ui.delete_tool_logic import (
    build_delete_tool_history_command,
    erase_delete_tool_item,
)
from ui.renderer_style_access import atom_color_for
from ui.scene_item_access import item_is_in_canvas_scene
from ui.tool_base import Tool


class ColorTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("color", canvas, context=context)
        self._last_color: str | None = None

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def set_color(self, color) -> None:
        qcolor = color if isinstance(color, QColor) else QColor(color)
        self._last_color = qcolor.name() if qcolor.isValid() else str(color)

    def _apply_color_to_item(self, item, color: QColor) -> None:
        self.context.apply_color_to_item(item, color)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.context.item_at_event(event)
        targets = []
        if item is not None:
            targets = [item]
        else:
            targets = [
                sel
                for sel in self.context.selected_scene_items(excluded_kinds=set())
                if sel.data(0) in {"bond", "atom", "ring", "shape"}
            ]
            if not targets:
                return True
        color = QColor(self._last_color or atom_color_for(self.canvas))
        if not color.isValid():
            return True
        for target in targets:
            self._apply_color_to_item(target, color)
        return True


class FlipTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("flip", canvas, context=context)

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.context.item_at_event(event)
        if item is None:
            return True
        bond_id = item.data(1)
        if isinstance(bond_id, int):
            self.context.flip_bond_direction(bond_id)
        return True


class EditBondTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("edit_bond", canvas, context=context)

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.context.item_at_event(event)
        bond_id = None
        if item is not None and item.data(0) == "bond":
            bond_id = item.data(1)
        if not isinstance(bond_id, int):
            bond_id = self.context.bond_id_from_event(event)
        if isinstance(bond_id, int):
            self.context.cycle_bond_style(bond_id)
        return True


class DeleteTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("delete", canvas, context=context)
        self._erasing = False
        self._changed = False
        self._commands: list = []
        self._before_smiles_input: str | None = None

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._erasing = True
        self._commands = []
        self._before_smiles_input = last_smiles_input_for(self.canvas)
        self._erase_at_event(event)
        return True

    def on_mouse_move(self, event) -> bool:
        if not self._erasing:
            return False
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._erase_at_event(event)
            return True
        return False

    def on_mouse_release(self, event) -> bool:
        self._erasing = False
        if self._changed and self._commands:
            command = build_delete_tool_history_command(
                self._commands,
                before_smiles_input=self._before_smiles_input,
                after_smiles_input=last_smiles_input_for(self.canvas),
            )
            if command is not None:
                self.context.push_history(command)
        self._changed = False
        self._commands = []
        self._before_smiles_input = None
        return True

    def _erase_at_event(self, event) -> None:
        item = self.context.item_at_event(event)
        if item is None:
            return
        if not item_is_in_canvas_scene(self.canvas, item):
            return
        changed, command = erase_delete_tool_item(
            self.canvas,
            item,
            scene_ops=self.context.scene_delete_controller,
        )
        if not changed:
            return
        if command is not None:
            self._commands.append(command)
        self._changed = True


__all__ = ["ColorTool", "DeleteTool", "EditBondTool", "FlipTool"]
