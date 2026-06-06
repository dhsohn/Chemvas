from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QTabBar, QTabWidget, QWidget


class SheetTabBar(QTabBar):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setExpanding(False)
        self.setDrawBase(False)
        self._add_tab_index = -1

    def set_add_tab_index(self, index: int) -> None:
        self._add_tab_index = index
        self.updateGeometry()
        self.update()

    def tabSizeHint(self, index: int) -> QSize:
        hint = super().tabSizeHint(index)
        if index == self._add_tab_index:
            return QSize(28, hint.height())
        return hint


@dataclass(frozen=True, slots=True)
class MainWindowTabAssembly:
    sheet_add_tab: QWidget
    canvas_tabs: QTabWidget
    sheet_tab_bar: SheetTabBar


def build_canvas_tab_assembly(
    parent,
    *,
    show_canvas_tab_context_menu: Callable,
    on_canvas_tab_moved: Callable,
    on_canvas_tab_changed: Callable,
) -> MainWindowTabAssembly:
    canvas_tabs = QTabWidget()
    canvas_tabs.setObjectName("canvasTabs")
    sheet_tab_bar = SheetTabBar(canvas_tabs)
    canvas_tabs.setTabBar(sheet_tab_bar)
    canvas_tabs.setTabPosition(QTabWidget.TabPosition.South)
    canvas_tabs.setDocumentMode(False)
    canvas_tabs.setMovable(True)
    canvas_tabs.setTabsClosable(False)
    sheet_tab_bar.setExpanding(False)
    sheet_tab_bar.setDrawBase(False)
    sheet_tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    sheet_tab_bar.customContextMenuRequested.connect(show_canvas_tab_context_menu)
    sheet_tab_bar.tabMoved.connect(on_canvas_tab_moved)
    canvas_tabs.currentChanged.connect(on_canvas_tab_changed)
    canvas_tabs.setParent(parent)
    return MainWindowTabAssembly(
        sheet_add_tab=QWidget(parent),
        canvas_tabs=canvas_tabs,
        sheet_tab_bar=sheet_tab_bar,
    )


__all__ = ["MainWindowTabAssembly", "SheetTabBar", "build_canvas_tab_assembly"]
