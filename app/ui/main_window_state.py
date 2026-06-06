from __future__ import annotations

from dataclasses import dataclass

from ui.main_window_canvas_logic import canvas_sheet_name_counter


@dataclass
class MainWindowState:
    current_file_path: str | None = None
    context_bar_page_override: str | None = None
    canvas_name_counter: int = 0
    result_sheet_counter: int = 0
    last_canvas_tab_index: int = 0
    tab_reactions_suspended: bool = False
    repositioning_add_tab: bool = False

    def clear_context_bar_page_override(self) -> None:
        self.context_bar_page_override = None

    def set_context_bar_page_override(self, page_key: str | None) -> None:
        self.context_bar_page_override = page_key

    def next_canvas_sheet_name(self, prefix: str = "Sheet") -> str:
        self.canvas_name_counter += 1
        return f"{prefix} {self.canvas_name_counter}"

    def next_result_canvas_name(self, prefix: str) -> str:
        self.result_sheet_counter += 1
        return f"{prefix} {self.result_sheet_counter}"

    def reset_canvas_name_counter(self, sheet_names) -> None:
        self.canvas_name_counter = canvas_sheet_name_counter(sheet_names)


__all__ = ["MainWindowState"]
