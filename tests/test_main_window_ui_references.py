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
def test_main_window_ui_references_apply_toolbar_and_menu_bar_assemblies() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    owner = QToolButton()
    action = QAction("Select", owner)
    atom_input = QLineEdit()
    undo_action = QAction("Undo", owner)
    redo_action = QAction("Redo", owner)
    refs = MainWindowUiReferences()

    refs.apply_toolbar_assembly(SimpleNamespace(tool_actions={"select": action}))

    assert refs.tool_action_for_key("select") is action
    assert refs.tool_action_for_key("missing") is None
    assert refs.atom_input is None
    assert refs.undo_action is None
    assert refs.redo_action is None

    refs.apply_menu_bar_assembly(
        SimpleNamespace(undo_action=undo_action, redo_action=redo_action)
    )

    assert refs.undo_action is undo_action
    assert refs.redo_action is redo_action
    refs.set_atom_input(atom_input)
    assert refs.atom_input is atom_input
    preview_window = object()
    refs.apply_preview_window_assembly(SimpleNamespace(preview_window=preview_window))
    assert refs.preview_window is preview_window

    owner.close()
    app.processEvents()
