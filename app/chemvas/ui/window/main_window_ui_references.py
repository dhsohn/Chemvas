from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt6.QtGui import QAction
    from PyQt6.QtWidgets import QLineEdit

    from chemvas.shell.icon_factory import MainWindowIconFactory
    from chemvas.ui.dialogs.calculation_panel import CalculationPanel
    from chemvas.ui.window.main_window_menu_bar import MainWindowMenuBarAssembly
    from chemvas.ui.window.main_window_panel_toolbar import (
        MainWindowPanelToolbarAssembly,
    )
    from chemvas.ui.window.main_window_preview_window import (
        MainWindowPreviewWindowAssembly,
        MoleculeInspectorDock,
    )


@dataclass(slots=True, kw_only=True)
class MainWindowUiReferences:
    icon_factory: MainWindowIconFactory | None = None
    tool_actions: dict[str, QAction] = field(default_factory=dict)
    atom_input: QLineEdit | None = None
    undo_action: QAction | None = None
    redo_action: QAction | None = None
    grid_snap_action: QAction | None = None
    preview_window: MoleculeInspectorDock | None = None
    calculation_panel: CalculationPanel | None = None

    def require_icon_factory(self) -> MainWindowIconFactory:
        if self.icon_factory is None:
            raise RuntimeError("Main window icon factory has not been initialized.")
        return self.icon_factory

    def apply_toolbar_assembly(self, assembly: MainWindowPanelToolbarAssembly) -> None:
        self.tool_actions = assembly.tool_actions

    def apply_menu_bar_assembly(self, assembly: MainWindowMenuBarAssembly) -> None:
        self.undo_action = assembly.undo_action
        self.redo_action = assembly.redo_action
        self.grid_snap_action = assembly.grid_snap_action

    def set_atom_input(self, atom_input: QLineEdit | None) -> None:
        self.atom_input = atom_input

    def tool_action_for_key(self, action_key: str) -> QAction | None:
        return self.tool_actions.get(action_key)

    def apply_preview_window_assembly(
        self, assembly: MainWindowPreviewWindowAssembly
    ) -> None:
        self.preview_window = assembly.preview_window


__all__ = ["MainWindowUiReferences"]
