from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDockWidget, QSplitter, QWidget


@dataclass(frozen=True)
class MainWindowPanelAssembly:
    splitter: QSplitter
    dock: QDockWidget


def build_preview_panel_dock(window, *, preview_widget) -> MainWindowPanelAssembly:
    dock = QDockWidget("Panels", window)
    dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
    dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
    dock.setMinimumWidth(320)
    dock.setMaximumWidth(420)
    title_bar = QWidget(dock)
    title_bar.setFixedHeight(0)
    dock.setTitleBarWidget(title_bar)

    splitter = QSplitter(Qt.Orientation.Vertical)
    splitter.addWidget(preview_widget)
    splitter.setChildrenCollapsible(False)
    splitter.setStretchFactor(0, 1)
    splitter.setSizes([1])

    dock.setWidget(splitter)
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    return MainWindowPanelAssembly(splitter=splitter, dock=dock)


__all__ = ["MainWindowPanelAssembly", "build_preview_panel_dock"]
