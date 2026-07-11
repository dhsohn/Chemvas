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

    def _apply_color_to_items(self, items, color: QColor) -> None:
        self.context.apply_color_to_items(items, color)

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
        self._apply_color_to_items(targets, color)
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
        self._delete_session = None

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def deactivate(self) -> None:
        if self._delete_session is not None and self._changed:
            self._rollback_active_session()
            return
        self._finish_active_session()

    def _clear_session_state(self) -> None:
        self._erasing = False
        self._changed = False
        self._commands = []
        self._before_smiles_input = None
        self._delete_session = None

    @staticmethod
    def _add_rollback_error_notes(
        primary_error: BaseException,
        rollback_errors: list[BaseException],
    ) -> None:
        for rollback_error in rollback_errors:
            try:
                primary_error.add_note(
                    "Delete tool rollback also encountered "
                    f"{type(rollback_error).__name__}: {rollback_error}"
                )
            except BaseException:
                # A third-party control-flow exception can expose a broken
                # diagnostic hook. Reporting must not replace the primary.
                continue

    def _rollback_active_session(self, original_error: BaseException | None = None) -> None:
        rollback_errors: list[BaseException] = []
        session = self._delete_session
        rollback_completed = session is None
        try:
            if session is not None:
                try:
                    rollback_result = self.context.rollback_delete_tool_session(session)
                    rollback_errors = list(rollback_result)
                    rollback_completed = bool(
                        getattr(rollback_result, "completed", True)
                    )
                except BaseException as rollback_error:
                    rollback_errors = [rollback_error]
        finally:
            if rollback_completed:
                self._clear_session_state()
            else:
                # Stop consuming pointer events, but retain the live session
                # and its command metadata so deactivate/new press can retry.
                self._erasing = False
        if original_error is not None:
            self._add_rollback_error_notes(original_error, rollback_errors)
            return
        if rollback_errors:
            primary_error = rollback_errors[0]
            self._add_rollback_error_notes(primary_error, rollback_errors[1:])
            raise primary_error

    def _finish_active_session(self, command=None) -> None:
        session = self._delete_session
        try:
            if session is not None:
                self.context.commit_delete_tool_session(session, command)
        except BaseException as original_error:
            self._rollback_active_session(original_error)
            raise
        self._clear_session_state()

    def _erase_or_rollback(self, event) -> None:
        try:
            self._erase_at_event(event)
        except BaseException as original_error:
            self._rollback_active_session(original_error)
            raise

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if self._delete_session is not None:
            if self._changed:
                self._rollback_active_session()
            else:
                self._finish_active_session()
        try:
            self._delete_session = self.context.begin_delete_tool_session()
            self._before_smiles_input = last_smiles_input_for(self.canvas)
            self._erasing = True
            self._erase_or_rollback(event)
        except BaseException as original_error:
            if self._erasing or self._delete_session is not None:
                self._rollback_active_session(original_error)
            raise
        return True

    def on_mouse_move(self, event) -> bool:
        if not self._erasing:
            return False
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._erase_or_rollback(event)
            return True
        return False

    def on_mouse_release(self, event) -> bool:
        self._erasing = False
        if not self._changed:
            self._finish_active_session()
            return True
        if not self._commands:
            self._rollback_active_session()
            return True
        try:
            command = build_delete_tool_history_command(
                self._commands,
                before_smiles_input=self._before_smiles_input,
                after_smiles_input=last_smiles_input_for(self.canvas),
            )
            if command is None:
                self._rollback_active_session()
                return True
            self._finish_active_session(command)
        except BaseException as original_error:
            self._rollback_active_session(original_error)
            raise
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
            delete_session=self._delete_session,
        )
        if not changed:
            return
        if command is not None:
            self._commands.append(command)
        self._changed = True


__all__ = ["ColorTool", "DeleteTool", "EditBondTool", "FlipTool"]
