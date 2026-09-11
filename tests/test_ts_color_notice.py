"""Unsupported per-item TS color gives feedback without changing the drawing."""

import pytest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton

from chemvas.bootstrap.main_window import build_main_window
from chemvas.features.annotations import BRACKET_KIND_VALUES
from chemvas.ui.canvas_callback_state import callback_state_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.main_window_ports import active_canvas_for_window, services_for_window
from chemvas.ui.scene_decoration_access import add_ts_bracket_for
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.mark.parametrize("kind", sorted(BRACKET_KIND_VALUES))
def test_ts_color_reports_document_color_policy_without_mutation(app, kind):
    canvas = build_canvas_view()
    try:
        item = add_ts_bracket_for(canvas, QRectF(0, 0, 70, 90), kind)
        before = snapshot_canvas_state_for(canvas)
        path, brush, pen = item.path(), item.brush(), item.pen()
        history = canvas.services.history_service
        stacks = history.capture_stack_snapshot()
        messages = []
        callback_state_for(canvas).error = messages.append
        canvas.services.scene_operations.canvas_color_mutation_service.apply_color_to_items(
            [item], QColor("#cc3344")
        )
        assert len(messages) == 1
        assert "document bond color" in messages[0]
        assert "per-item color is not supported" in messages[0]
        assert snapshot_canvas_state_for(canvas) == before
        assert (item.path(), item.brush(), item.pen()) == (path, brush, pen)
        history.verify_stack_snapshot(stacks)
    finally:
        canvas.services.document.canvas_scene_reset_service.clear_scene()
        canvas.close()
        app.processEvents()


@pytest.mark.parametrize("kind", ["square_pair", "double_dagger", "dagger"])
def test_color_tool_live_click_shows_ts_notice_in_status_bar(app, kind):
    window = build_main_window()
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    canvas = active_canvas_for_window(window)
    try:
        item = add_ts_bracket_for(canvas, QRectF(-35, -45, 70, 90), kind)
        canvas.services.input.tool_mode_controller.set_tool("color")
        app.processEvents()
        before = snapshot_canvas_state_for(canvas)
        history = canvas.services.history_service
        stacks = history.capture_stack_snapshot()
        ink = item.mapToScene(item.path().pointAtPercent(0.1))
        QTest.mouseClick(
            canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(ink)
        )
        app.processEvents()
        assert "per-item color is not supported" in window.statusBar().currentMessage()
        assert snapshot_canvas_state_for(canvas) == before
        history.verify_stack_snapshot(stacks)
    finally:
        services_for_window(window).canvas_document_service.mark_clean(canvas)
        window.close()
        app.processEvents()


@pytest.mark.parametrize("kind", ["square_pair", "double_dagger", "dagger"])
def test_selected_ts_palette_click_reports_notice_without_mutation(app, kind):
    window = build_main_window()
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    canvas = active_canvas_for_window(window)
    try:
        item = add_ts_bracket_for(canvas, QRectF(-35, -45, 70, 90), kind)
        history = canvas.services.history_service
        add_ts_bracket_for(canvas, QRectF(100, -45, 70, 90), "square_pair")
        history.undo()
        assert history.can_redo()
        item.setSelected(True)
        window.ui_references.tool_actions["color"].trigger()
        app.processEvents()
        button = next(
            widget
            for widget in window.findChildren(QToolButton)
            if widget.toolTip() == "Color: Red"
        )
        before = snapshot_canvas_state_for(canvas)
        selected = set(canvas.scene().selectedItems())
        assert item in selected
        path, brush, pen = item.path(), item.brush(), item.pen()
        stacks = history.capture_stack_snapshot()

        # Exercise the real palette callback and its deferred selection routing.
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert "per-item color is not supported" in window.statusBar().currentMessage()
        assert snapshot_canvas_state_for(canvas) == before
        assert set(canvas.scene().selectedItems()) == selected
        assert (item.path(), item.brush(), item.pen()) == (path, brush, pen)
        history.verify_stack_snapshot(stacks)
    finally:
        services_for_window(window).canvas_document_service.mark_clean(canvas)
        window.close()
        app.processEvents()
