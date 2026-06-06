from __future__ import annotations

from ui.tool_context import ToolContext


class Tool:
    def __init__(self, name: str, canvas=None, *, context: ToolContext | None = None) -> None:
        self.name = name
        self.canvas = canvas if canvas is not None else (context.canvas if context is not None else None)
        self.context = context

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
