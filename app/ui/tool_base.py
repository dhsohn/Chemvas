from __future__ import annotations

from ui.tool_context import ToolContext


class Tool:
    def __init__(self, name: str, canvas=None, *, context: ToolContext | None = None) -> None:
        self.name = name
        self.canvas = canvas if canvas is not None else (context.canvas if context is not None else None)
        self._context = context

    @property
    def context(self) -> ToolContext:
        if self._context is None:
            raise RuntimeError(f"Tool {self.name!r} has no active ToolContext.")
        return self._context

    @context.setter
    def context(self, value: ToolContext | None) -> None:
        self._context = value

    def activate(self) -> None:
        pass

    def deactivate(self) -> None:
        pass

    def on_mouse_press(self, event) -> bool:
        return False

    def on_mouse_move(self, event) -> bool:
        return False

    def on_mouse_release(self, event) -> bool:
        return False


__all__ = ["Tool"]
