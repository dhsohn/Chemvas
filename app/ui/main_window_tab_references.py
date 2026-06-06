from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import QTabWidget, QWidget

from ui.canvas_view import CanvasView
from ui.main_window_canvas_logic import (
    active_canvas_sheet_index as active_canvas_sheet_index_for,
)
from ui.main_window_canvas_logic import (
    active_canvas_tab_index as active_canvas_tab_index_for,
)
from ui.main_window_canvas_logic import resolve_active_canvas
from ui.main_window_tab_setup import MainWindowTabAssembly, SheetTabBar


@dataclass(slots=True)
class MainWindowTabReferences:
    canvas_tabs: QTabWidget
    sheet_add_tab: QWidget
    sheet_tab_bar: SheetTabBar

    @classmethod
    def from_assembly(cls, assembly: MainWindowTabAssembly) -> MainWindowTabReferences:
        return cls(
            canvas_tabs=assembly.canvas_tabs,
            sheet_add_tab=assembly.sheet_add_tab,
            sheet_tab_bar=assembly.sheet_tab_bar,
        )

    def plus_tab_index(self) -> int:
        return self.canvas_tabs.indexOf(self.sheet_add_tab)

    def recreate_sheet_add_tab(self, parent=None) -> QWidget:
        self.sheet_add_tab = QWidget(parent)
        return self.sheet_add_tab

    def set_sheet_add_tab_index(self, index: int) -> None:
        self.sheet_tab_bar.set_add_tab_index(index)

    def move_sheet_tab(self, from_index: int, to_index: int) -> None:
        self.sheet_tab_bar.moveTab(from_index, to_index)

    def sheet_tab_at(self, pos) -> int:
        return self.sheet_tab_bar.tabAt(pos)

    def sheet_tab_global_pos(self, pos):
        return self.sheet_tab_bar.mapToGlobal(pos)

    def canvas_tab_entries(self) -> list[tuple[int, CanvasView]]:
        entries: list[tuple[int, CanvasView]] = []
        for index in range(self.canvas_tabs.count()):
            widget = self.canvas_tabs.widget(index)
            if isinstance(widget, CanvasView):
                entries.append((index, widget))
        return entries

    def all_canvases(self) -> list[CanvasView]:
        return [canvas for _, canvas in self.canvas_tab_entries()]

    def active_canvas_or_none(self, last_canvas_tab_index: int) -> CanvasView | None:
        return resolve_active_canvas(
            self.canvas_tabs.currentWidget(),
            last_canvas_tab_index,
            self.canvas_tab_entries(),
        )

    def active_canvas_tab_index(self, active_canvas) -> int:
        return active_canvas_tab_index_for(self.canvas_tab_entries(), active_canvas)

    def active_canvas_sheet_index(self, active_canvas) -> int:
        return active_canvas_sheet_index_for(self.canvas_tab_entries(), active_canvas)

    def canvas_sheet_count(self) -> int:
        return len(self.all_canvases())

    def active_canvas_sheet_name(self, active_canvas) -> str:
        index = self.active_canvas_tab_index(active_canvas)
        return self.tab_text(index)

    def tab_text(self, index: int) -> str:
        if index < 0:
            return ""
        return self.canvas_tabs.tabText(index)


__all__ = ["MainWindowTabReferences"]
