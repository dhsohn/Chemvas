from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class Preview3DWindow(QWidget):
    def __init__(self, parent, *, preview_widget) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Molecule Info")
        self.setMinimumSize(420, 360)
        self.resize(560, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(preview_widget)
        self._status_label = QLabel("", self)
        self._status_label.setObjectName("preview_export_status")
        self._status_label.setContentsMargins(12, 4, 12, 6)
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)
        layout.setStretchFactor(preview_widget, 1)
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

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()


@dataclass(frozen=True)
class MainWindowPreviewWindowAssembly:
    preview_window: Preview3DWindow


def build_preview_window(window, *, preview_widget) -> MainWindowPreviewWindowAssembly:
    return MainWindowPreviewWindowAssembly(
        preview_window=Preview3DWindow(window, preview_widget=preview_widget),
    )


__all__ = ["MainWindowPreviewWindowAssembly", "Preview3DWindow", "build_preview_window"]
