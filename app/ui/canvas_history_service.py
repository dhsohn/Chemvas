from __future__ import annotations

from typing import Any

from core.history import HistoryCommand
from ui.canvas_history_state import CanvasHistoryState, CanvasHistoryStateAdapter, history_state_for


class CanvasHistoryService:
    def __init__(
        self,
        canvas: Any,
        state: CanvasHistoryState | CanvasHistoryStateAdapter | None = None,
    ) -> None:
        self.canvas = canvas
        self.state = state if state is not None else history_state_for(canvas)

    def push(self, command: HistoryCommand) -> None:
        if not self.state.enabled:
            return
        self.state.history.append(command)
        if len(self.state.history) > self.state.limit:
            self.state.history.pop(0)
        self.state.redo_stack.clear()
        self.notify_change()

    def undo(self) -> None:
        if not self.state.history:
            return
        command = self.state.history.pop()
        self.state.redo_stack.append(command)
        command.undo(self.canvas)
        self.notify_change()

    def redo(self) -> None:
        if not self.state.redo_stack:
            return
        command = self.state.redo_stack.pop()
        self.state.history.append(command)
        command.redo(self.canvas)
        self.notify_change()

    def set_change_callback(self, callback) -> None:
        self.state.change_callback = callback

    def set_enabled(self, enabled: bool) -> None:
        self.state.enabled = bool(enabled)

    def clear(self) -> None:
        self.state.history = []
        self.state.redo_stack = []
        self.notify_change()

    def notify_change(self) -> None:
        if self.state.change_callback is not None:
            self.state.change_callback()

    def is_enabled(self) -> bool:
        return bool(self.state.enabled)

    def can_undo(self) -> bool:
        return bool(self.state.history)

    def can_redo(self) -> bool:
        return bool(self.state.redo_stack)


class CanvasHistoryCommandSink:
    def __init__(self, canvas: Any) -> None:
        self.canvas = canvas

    @property
    def state(self):
        return history_state_for(self.canvas)

    def push(self, command: HistoryCommand) -> None:
        push_command = getattr(self.canvas, "_push_command", None)
        if callable(push_command):
            push_command(command)

    def undo(self) -> None:
        CanvasHistoryService(self.canvas, self.state).undo()

    def redo(self) -> None:
        CanvasHistoryService(self.canvas, self.state).redo()

    def set_change_callback(self, callback) -> None:
        self.state.change_callback = callback

    def set_enabled(self, enabled: bool) -> None:
        self.state.enabled = bool(enabled)

    def clear(self) -> None:
        self.state.history = []
        self.state.redo_stack = []
        self.notify_change()

    def notify_change(self) -> None:
        callback = self.state.change_callback
        if callback is not None:
            callback()

    def is_enabled(self) -> bool:
        try:
            return bool(self.state.enabled)
        except Exception:
            return True

    def can_undo(self) -> bool:
        return bool(self.state.history)

    def can_redo(self) -> bool:
        return bool(self.state.redo_stack)


def history_service_for(canvas: Any) -> CanvasHistoryService | CanvasHistoryCommandSink:
    service = getattr(canvas, "_history_service", None)
    if service is not None:
        return service
    push_command = getattr(canvas, "_push_command", None)
    if callable(push_command):
        return CanvasHistoryCommandSink(canvas)
    return CanvasHistoryService(canvas)


__all__ = ["CanvasHistoryService", "CanvasHistoryCommandSink", "history_service_for"]
