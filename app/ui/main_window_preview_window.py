from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QVBoxLayout, QWidget


class Preview3DWindow(QWidget):
    def __init__(self, parent, *, preview_widget) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("3D Preview")
        self.setMinimumSize(420, 360)
        self.resize(560, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(preview_widget)

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
