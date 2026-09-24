from __future__ import annotations

from dataclasses import dataclass
from typing import override

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtWidgets import (
    QDockWidget,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from chemvas.shell.icon_factory import MainWindowIconFactory
from chemvas.shell.theme import TOOLBAR_BUTTON_SIZE, TOOLBAR_ICON_SIZE


class MoleculeInspectorDock(QDockWidget):
    def __init__(self, parent, *, preview_widget) -> None:
        super().__init__("Molecule Info", parent)
        self.setObjectName("inspectorDock")
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(preview_widget)
        self._preview_widget = preview_widget
        self._status_label = QLabel("", self)
        self._status_label.setObjectName("preview_export_status")
        self._status_label.setWordWrap(True)
        self._status_label.setContentsMargins(12, 4, 12, 6)
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)
        layout.setStretchFactor(preview_widget, 1)
        self.setWidget(content)
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(4000)
        self._status_timer.timeout.connect(self._clear_export_status)

    def show_export_status(self, message: str) -> None:
        self._status_label.setText(message)
        self._status_label.setVisible(bool(message))
        if message:
            self._status_timer.start()

    def _clear_export_status(self) -> None:
        self._status_label.clear()
        self._status_label.setVisible(False)

    @override
    def hideEvent(self, event) -> None:
        self._preview_widget.pause_updates()
        super().hideEvent(event)


@dataclass(frozen=True)
class MainWindowPreviewWindowAssembly:
    preview_window: MoleculeInspectorDock


def build_preview_window(
    window, *, preview_widget, panel_bar
) -> MainWindowPreviewWindowAssembly:
    dock = MoleculeInspectorDock(window, preview_widget=preview_widget)
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    window.resizeDocks([dock], [280], Qt.Orientation.Horizontal)
    dock.hide()
    action = dock.toggleViewAction()
    assert action is not None
    action.setIcon(MainWindowIconFactory(window).make_design_icon("cube"))
    action.setToolTip("Show or hide the molecule inspector")
    button = QToolButton()
    button.setObjectName("inspectorToggleButton")
    button.setDefaultAction(action)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    button.setIconSize(QSize(TOOLBAR_ICON_SIZE, TOOLBAR_ICON_SIZE))
    button.setFixedSize(TOOLBAR_BUTTON_SIZE, TOOLBAR_BUTTON_SIZE)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setProperty("iconOnly", True)
    panel_bar.addWidget(button)
    return MainWindowPreviewWindowAssembly(preview_window=dock)


__all__ = [
    "MainWindowPreviewWindowAssembly",
    "MoleculeInspectorDock",
    "build_preview_window",
]
