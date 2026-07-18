from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QAction
    from PyQt6.QtWidgets import QApplication, QLineEdit, QToolButton
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.ui.main_window_ui_references import MainWindowUiReferences


@pytest.mark.skipif(
    QApplication is None, reason="PyQt6 is required for main window UI reference tests"
)
def test_main_window_ui_references_require_initialized_icon_factory() -> None:
    refs = MainWindowUiReferences()

    with pytest.raises(RuntimeError, match="icon factory"):
        refs.require_icon_factory()

    icon_factory = object()
    refs.icon_factory = icon_factory

    assert refs.require_icon_factory() is icon_factory


@pytest.mark.skipif(
    QApplication is None, reason="PyQt6 is required for main window UI reference tests"
)
def test_main_window_ui_references_apply_toolbar_assembly() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    owner = QToolButton()
    action = QAction("Select", owner)
    atom_input = QLineEdit()
    export_button = QToolButton()
    preview_button = QToolButton()
    undo_button = QToolButton()
    redo_button = QToolButton()
    assembly = SimpleNamespace(
        tool_actions={"select": action},
        load_action=QAction("Load", owner),
        export_xyz_button=export_button,
        preview_panel_button=preview_button,
        undo_button=undo_button,
        redo_button=redo_button,
    )
    refs = MainWindowUiReferences()

    refs.apply_toolbar_assembly(assembly)

    assert refs.tool_action_for_key("select") is action
    assert refs.tool_action_for_key("missing") is None
    assert refs.atom_input is None
    assert refs.export_xyz_button is export_button
    assert refs.preview_panel_button is preview_button
    assert refs.undo_button is undo_button
    assert refs.redo_button is redo_button
    refs.set_atom_input(atom_input)
    assert refs.atom_input is atom_input
    preview_window = object()
    refs.apply_preview_window_assembly(SimpleNamespace(preview_window=preview_window))
    assert refs.preview_window is preview_window

    owner.close()
    app.processEvents()
