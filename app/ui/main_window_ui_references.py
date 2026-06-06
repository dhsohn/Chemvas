from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QDockWidget, QLineEdit, QSplitter, QToolButton

if TYPE_CHECKING:
    from ui.main_window_icon_factory import MainWindowIconFactory
    from ui.main_window_preview_panel import MainWindowPanelAssembly
    from ui.main_window_ui_assembly_service import MainWindowToolbarAssembly


@dataclass(slots=True)
class MainWindowUiReferences:
    icon_factory: MainWindowIconFactory | None = None
    tool_actions: dict[str, QAction] = field(default_factory=dict)
    atom_input: QLineEdit | None = None
    load_action: QAction | None = None
    export_xyz_button: QToolButton | None = None
    preview_panel_button: QToolButton | None = None
    undo_button: QToolButton | None = None
    redo_button: QToolButton | None = None
    panel_splitter: QSplitter | None = None
    panel_dock: QDockWidget | None = None

    def require_icon_factory(self) -> MainWindowIconFactory:
        if self.icon_factory is None:
            raise RuntimeError("Main window icon factory has not been initialized.")
        return self.icon_factory

    def apply_toolbar_assembly(self, assembly: MainWindowToolbarAssembly) -> None:
        self.tool_actions = assembly.tool_actions
        self.atom_input = assembly.atom_input
        self.load_action = assembly.load_action
        self.export_xyz_button = assembly.export_xyz_button
        self.preview_panel_button = assembly.preview_panel_button
        self.undo_button = assembly.undo_button
        self.redo_button = assembly.redo_button

    def tool_action_for_key(self, action_key: str) -> QAction | None:
        return self.tool_actions.get(action_key)

    def apply_panel_assembly(self, assembly: MainWindowPanelAssembly) -> None:
        self.panel_splitter = assembly.splitter
        self.panel_dock = assembly.dock


__all__ = ["MainWindowUiReferences"]
