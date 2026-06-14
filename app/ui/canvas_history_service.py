from __future__ import annotations

from core.history import HistoryCommand

from ui.canvas_history_state import CanvasHistoryState, history_state_for


class CanvasHistoryService:
    def __init__(
        self,
        canvas,
        state: CanvasHistoryState | None = None,
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
        command = self.state.history[-1]
        command.undo(self.canvas)
        self.state.history.pop()
        self.state.redo_stack.append(command)
        self.notify_change()

    def redo(self) -> None:
        if not self.state.redo_stack:
            return
        command = self.state.redo_stack[-1]
        command.redo(self.canvas)
        self.state.redo_stack.pop()
        self.state.history.append(command)
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


__all__ = ["CanvasHistoryService"]
