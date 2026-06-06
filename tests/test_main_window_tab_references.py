from __future__ import annotations

import os
from unittest import mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QApplication, QMainWindow
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_view import CanvasView
    from ui.main_window_tab_references import MainWindowTabReferences
    from ui.main_window_tab_setup import build_canvas_tab_assembly


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required for main window tab reference tests")
def test_main_window_tab_references_wrap_sheet_tab_controls() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = QMainWindow()
    assembly = build_canvas_tab_assembly(
        window,
        show_canvas_tab_context_menu=mock.Mock(),
        on_canvas_tab_moved=mock.Mock(),
        on_canvas_tab_changed=mock.Mock(),
    )
    refs = MainWindowTabReferences.from_assembly(assembly)

    plus_index = refs.canvas_tabs.addTab(refs.sheet_add_tab, "+")

    assert refs.plus_tab_index() == plus_index

    old_add_tab = refs.sheet_add_tab
    new_add_tab = refs.recreate_sheet_add_tab(window)

    assert new_add_tab is refs.sheet_add_tab
    assert refs.sheet_add_tab is not old_add_tab
    assert refs.sheet_add_tab.parent() is window
    assert refs.plus_tab_index() == -1

    refs.set_sheet_add_tab_index(2)
    assert refs.sheet_tab_bar._add_tab_index == 2

    with mock.patch.object(refs.sheet_tab_bar, "moveTab") as move_tab:
        refs.move_sheet_tab(1, 2)
    move_tab.assert_called_once_with(1, 2)

    assert refs.sheet_tab_at(QPoint(-100, -100)) == -1

    window.close()
    app.processEvents()


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required for main window tab reference tests")
def test_main_window_tab_references_resolve_active_canvas_tabs_and_sheet_names() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = QMainWindow()
    assembly = build_canvas_tab_assembly(
        window,
        show_canvas_tab_context_menu=mock.Mock(),
        on_canvas_tab_moved=mock.Mock(),
        on_canvas_tab_changed=mock.Mock(),
    )
    refs = MainWindowTabReferences.from_assembly(assembly)
    canvas_a = CanvasView()
    canvas_b = CanvasView()

    refs.canvas_tabs.addTab(canvas_a, "Reactant")
    refs.canvas_tabs.addTab(refs.sheet_add_tab, "+")
    refs.canvas_tabs.addTab(canvas_b, "Product")

    assert refs.canvas_tab_entries() == [(0, canvas_a), (2, canvas_b)]
    assert refs.all_canvases() == [canvas_a, canvas_b]
    assert refs.canvas_sheet_count() == 2

    refs.canvas_tabs.setCurrentWidget(canvas_a)
    assert refs.active_canvas_or_none(last_canvas_tab_index=2) is canvas_a
    assert refs.active_canvas_tab_index(canvas_a) == 0
    assert refs.active_canvas_sheet_index(canvas_a) == 0
    assert refs.active_canvas_sheet_name(canvas_a) == "Reactant"

    refs.canvas_tabs.setCurrentWidget(refs.sheet_add_tab)
    assert refs.active_canvas_or_none(last_canvas_tab_index=2) is canvas_b
    assert refs.active_canvas_tab_index(canvas_b) == 2
    assert refs.active_canvas_sheet_index(canvas_b) == 1
    assert refs.active_canvas_sheet_name(canvas_b) == "Product"
    assert refs.active_canvas_sheet_name(object()) == ""

    window.close()
    app.processEvents()
