from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtWidgets import QTabWidget


@dataclass(frozen=True, slots=True)
class MainWindowTabAssembly:
    canvas_tabs: QTabWidget


def build_canvas_tab_assembly(
    parent,
    *,
    on_canvas_tab_moved: Callable,
    on_canvas_tab_changed: Callable,
    on_canvas_tab_close_requested: Callable,
) -> MainWindowTabAssembly:
    canvas_tabs = QTabWidget()
    canvas_tabs.setObjectName("canvasTabs")
    canvas_tabs.setTabPosition(QTabWidget.TabPosition.South)
    canvas_tabs.setDocumentMode(False)
    canvas_tabs.setMovable(True)
    canvas_tabs.setTabsClosable(True)
    tab_bar = canvas_tabs.tabBar()
    assert tab_bar is not None
    tab_bar.setExpanding(False)
    tab_bar.setDrawBase(False)
    tab_bar.tabMoved.connect(on_canvas_tab_moved)
    canvas_tabs.currentChanged.connect(on_canvas_tab_changed)
    canvas_tabs.tabCloseRequested.connect(on_canvas_tab_close_requested)
    canvas_tabs.setParent(parent)
    return MainWindowTabAssembly(
        canvas_tabs=canvas_tabs,
    )


__all__ = ["MainWindowTabAssembly", "build_canvas_tab_assembly"]
