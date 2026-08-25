from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MainWindowState:
    context_bar_page_override: str | None = None
    canvas_name_counter: int = 0
    last_canvas_tab_index: int = 0

    def clear_context_bar_page_override(self) -> None:
        self.context_bar_page_override = None

    def set_context_bar_page_override(self, page_key: str | None) -> None:
        self.context_bar_page_override = page_key

    def next_canvas_name(self, prefix: str = "Canvas") -> str:
        self.canvas_name_counter += 1
        return f"{prefix} {self.canvas_name_counter}"


__all__ = ["MainWindowState"]
