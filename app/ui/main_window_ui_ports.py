from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.main_window_ui_references import MainWindowUiReferences


def ui_references_for_window(window) -> MainWindowUiReferences:
    return window.ui_references


def icon_factory_for_window(window):
    return ui_references_for_window(window).require_icon_factory()


def atom_input_for_window(window):
    return ui_references_for_window(window).atom_input


def set_atom_input_for_window(window, atom_input) -> None:
    ui_references_for_window(window).set_atom_input(atom_input)


def tool_actions_for_window(window):
    return ui_references_for_window(window).tool_actions


def tool_action_for_window(window, action_key: str):
    return ui_references_for_window(window).tool_action_for_key(action_key)


def preview_panel_button_for_window(window):
    return ui_references_for_window(window).preview_panel_button


def panel_splitter_for_window(window):
    return ui_references_for_window(window).panel_splitter


def panel_dock_for_window(window):
    return ui_references_for_window(window).panel_dock


def apply_panel_assembly_for_window(window, assembly) -> None:
    ui_references_for_window(window).apply_panel_assembly(assembly)


def undo_button_for_window(window):
    return ui_references_for_window(window).undo_button


def redo_button_for_window(window):
    return ui_references_for_window(window).redo_button


def export_xyz_button_for_window(window):
    return ui_references_for_window(window).export_xyz_button


__all__ = [
    "atom_input_for_window",
    "apply_panel_assembly_for_window",
    "export_xyz_button_for_window",
    "icon_factory_for_window",
    "panel_dock_for_window",
    "panel_splitter_for_window",
    "preview_panel_button_for_window",
    "redo_button_for_window",
    "set_atom_input_for_window",
    "tool_action_for_window",
    "tool_actions_for_window",
    "ui_references_for_window",
    "undo_button_for_window",
]
