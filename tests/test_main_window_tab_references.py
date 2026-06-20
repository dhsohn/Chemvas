from __future__ import annotations

import os
from unittest import mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QMainWindow
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_view import CanvasView
    from ui.main_window_tab_references import MainWindowTabReferences
    from ui.main_window_tab_setup import build_canvas_tab_assembly


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required for main window tab reference tests")
def test_main_window_tab_references_resolve_active_canvas_tabs_and_names() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = QMainWindow()
    assembly = build_canvas_tab_assembly(
        window,
        on_canvas_tab_moved=mock.Mock(),
        on_canvas_tab_changed=mock.Mock(),
        on_canvas_tab_close_requested=mock.Mock(),
    )
    refs = MainWindowTabReferences.from_assembly(assembly)
    canvas_a = CanvasView()
    canvas_b = CanvasView()

    refs.canvas_tabs.addTab(canvas_a, "Reactant")
    refs.canvas_tabs.addTab(canvas_b, "Product")

    assert refs.canvas_tab_entries() == [(0, canvas_a), (1, canvas_b)]
    assert refs.all_canvases() == [canvas_a, canvas_b]
    assert refs.canvas_count() == 2

    refs.canvas_tabs.setCurrentWidget(canvas_a)
    assert refs.active_canvas_or_none(last_canvas_tab_index=1) is canvas_a
    assert refs.active_canvas_tab_index(canvas_a) == 0
    assert refs.active_canvas_index(canvas_a) == 0
    assert refs.active_canvas_name(canvas_a) == "Reactant"

    refs.canvas_tabs.setCurrentWidget(canvas_b)
    assert refs.active_canvas_or_none(last_canvas_tab_index=1) is canvas_b
    assert refs.active_canvas_tab_index(canvas_b) == 1
    assert refs.active_canvas_index(canvas_b) == 1
    assert refs.active_canvas_name(canvas_b) == "Product"
    assert refs.active_canvas_name(object()) == ""

    window.close()
    app.processEvents()
