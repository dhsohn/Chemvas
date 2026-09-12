"""Committed desktop edits keep off-sheet content reachable without moving Fit."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QGraphicsRectItem

from chemvas.bootstrap.main_window import build_main_window
from chemvas.features.export import (
    collect_export_items,
    content_bounds,
    export_item_closure,
)
from chemvas.ui import sheet_setup_access
from chemvas.ui.canvas_window_access import (
    set_error_callback_for,
    snapshot_canvas_state_for,
)
from chemvas.ui.input_view_access import (
    fit_canvas_to_view_for,
    set_zoom_for,
    zoom_factor_for,
)
from chemvas.ui.main_window_ports import active_canvas_for_window, services_for_window
from chemvas.ui.select_all_access import select_all_scene_items_for
from chemvas.ui.structure_mutation_access import add_bond_between_points_for


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def drawing(app):
    window = build_main_window()
    window.resize(1400, 900)
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    canvas = active_canvas_for_window(window)
    add_bond_between_points_for(canvas, QPointF(200, 0), QPointF(220, 0))
    canvas.services.input.tool_mode_controller.set_tool("select")
    select_all_scene_items_for(canvas)
    canvas.services.history_service.clear()
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    set_zoom_for(canvas, 0.2)
    canvas.centerOn(0, 0)
    app.processEvents()
    yield window, canvas
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    window.close()
    app.processEvents()


def _bounds(canvas):
    return content_bounds(export_item_closure(collect_export_items(canvas.scene())))


def _reachable(canvas):
    """Union every scrollbar extreme, preserving the current view position."""
    horizontal, vertical = canvas.horizontalScrollBar(), canvas.verticalScrollBar()
    original = horizontal.value(), vertical.value()
    result = QRectF()
    try:
        for x in (horizontal.minimum(), horizontal.maximum()):
            for y in (vertical.minimum(), vertical.maximum()):
                horizontal.setValue(x)
                vertical.setValue(y)
                result = result.united(
                    canvas.mapToScene(canvas.viewport().rect()).boundingRect()
                )
    finally:
        horizontal.setValue(original[0])
        vertical.setValue(original[1])
    return result


def _drag(canvas, app, *, release=True):
    start = canvas.mapFromScene(QPointF(210, 0))
    end = start + QPoint(480, 0)
    assert canvas.viewport().rect().contains(start)
    assert canvas.viewport().rect().contains(end)

    def move(position, buttons):
        # Deliver actual viewport events; Wayland does not permit cursor warps.
        QApplication.sendEvent(
            canvas.viewport(),
            QMouseEvent(
                QEvent.Type.MouseMove,
                QPointF(position),
                QPointF(canvas.viewport().mapToGlobal(position)),
                Qt.MouseButton.NoButton,
                buttons,
                Qt.KeyboardModifier.NoModifier,
            ),
        )

    move(start - QPoint(10, 0), Qt.MouseButton.NoButton)
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    move(start + QPoint(20, 0), Qt.MouseButton.LeftButton)
    QTest.qWait(20)  # The Select tool intentionally throttles preview frames.
    move(end, Qt.MouseButton.LeftButton)
    QTest.qWait(20)
    app.processEvents()
    if release:
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    return end


def test_real_drag_refreshes_only_after_release_and_history_restores_bounds(
    drawing, app, monkeypatch
):
    window, canvas = drawing
    document = services_for_window(window).canvas_document_service
    history = canvas.services.history_service
    before = snapshot_canvas_state_for(canvas)
    sheet_range = QRectF(canvas.sceneRect())
    updates = []
    original = sheet_setup_access.apply_sheet_scene_rect_for

    def observe(target):
        updates.append(snapshot_canvas_state_for(target))
        original(target)

    monkeypatch.setattr(sheet_setup_access, "apply_sheet_scene_rect_for", observe)
    end = _drag(canvas, app, release=False)
    assert not updates
    assert canvas.sceneRect() == sheet_range
    assert canvas.scene().sceneRect() == sheet_range
    # Off-sheet movement previews continuously, without changing the scroll
    # range or publishing the gesture before release.
    assert _bounds(canvas).left() > 2500
    preview = snapshot_canvas_state_for(canvas)
    assert not history.can_undo()
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert _bounds(canvas).left() > 2500
    after = snapshot_canvas_state_for(canvas)
    assert after == preview
    assert len(updates) == 1
    assert updates[0] == after
    assert document.is_dirty(canvas)
    expanded = QRectF(canvas.sceneRect())
    assert expanded.contains(_bounds(canvas))
    assert expanded == canvas.scene().sceneRect()
    set_zoom_for(canvas, 1.0)
    assert _reachable(canvas).contains(_bounds(canvas))
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    assert canvas.sceneRect() == sheet_range
    assert not document.is_dirty(canvas)
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after
    assert canvas.sceneRect() == expanded
    assert len(updates) == 3


def test_real_nudge_delete_and_undo_shrink_and_restore_scroll_range(drawing, app):
    _window, canvas = drawing
    sheet_range = QRectF(canvas.sceneRect())
    _drag(canvas, app)
    # Also exercises the pre-existing load/setup refresh, so deletion's RED is
    # independent of whether the preceding live-drag hook already works.
    sheet_setup_access.apply_sheet_scene_rect_for(canvas)
    before_nudge = QRectF(canvas.sceneRect())
    QTest.keyClick(
        canvas.viewport(), Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier
    )
    assert canvas.sceneRect().right() == pytest.approx(before_nudge.right() + 10)
    expanded = QRectF(canvas.sceneRect())
    before_delete = snapshot_canvas_state_for(canvas)
    QTest.keyClick(canvas.viewport(), Qt.Key.Key_Delete)
    assert not canvas.model.atoms
    assert _bounds(canvas) is None
    assert canvas.sceneRect() == sheet_range
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before_delete
    assert canvas.sceneRect() == expanded
    canvas.services.history_service.redo()
    assert not canvas.model.atoms
    assert canvas.sceneRect() == sheet_range


def test_fit_repairs_stale_bounds_but_still_fits_only_the_physical_sheet(drawing):
    _window, canvas = drawing
    # An inactive canvas has no history observer. Fit must also recover such a
    # stale range using canonical document-content bounds, not all scene items.
    history = canvas.services.history_service
    callback = history.state.change_callback
    history.set_change_callback(None)
    try:
        add_bond_between_points_for(canvas, QPointF(2600, 0), QPointF(2620, 0))
    finally:
        history.set_change_callback(callback)
    before = snapshot_canvas_state_for(canvas)
    stacks = history.capture_stack_snapshot()
    assert not canvas.sceneRect().contains(_bounds(canvas))
    QTest.keyClick(canvas.viewport(), Qt.Key.Key_F6)
    assert canvas.sceneRect().contains(_bounds(canvas))
    sheet = sheet_setup_access.sheet_rect_for(canvas)
    viewport = canvas.viewport().rect()
    expected_zoom = (
        min(viewport.width() / sheet.width(), viewport.height() / sheet.height()) * 0.92
    )
    assert zoom_factor_for(canvas) == pytest.approx(expected_zoom)
    assert canvas.mapToScene(viewport).boundingRect().contains(sheet)
    assert not canvas.mapToScene(viewport).boundingRect().contains(_bounds(canvas))
    assert snapshot_canvas_state_for(canvas) == before
    assert history.capture_stack_snapshot() == stacks


def test_cancelled_drag_does_not_expand_scroll_range_or_publish_history(drawing, app):
    window, canvas = drawing
    before = snapshot_canvas_state_for(canvas)
    rect = QRectF(canvas.sceneRect())
    stacks = canvas.services.history_service.capture_stack_snapshot()
    end = _drag(canvas, app, release=False)
    assert _bounds(canvas).left() > 2500
    assert snapshot_canvas_state_for(canvas) != before
    QTest.keyClick(canvas.viewport(), Qt.Key.Key_Escape)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert snapshot_canvas_state_for(canvas) == before
    assert canvas.sceneRect() == rect
    assert canvas.services.history_service.capture_stack_snapshot() == stacks
    assert not services_for_window(window).canvas_document_service.is_dirty(canvas)


def test_refresh_failure_preserves_committed_edit_and_fit_retries(
    drawing, app, monkeypatch
):
    window, canvas = drawing
    original = sheet_setup_access.content_bounds
    rect = QRectF(canvas.sceneRect())

    def fail(_items):
        raise RuntimeError("synthetic bounds failure")

    monkeypatch.setattr(sheet_setup_access, "content_bounds", fail)
    _drag(canvas, app)
    after = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    assert history.can_undo()
    assert _bounds(canvas).left() > 2500
    assert canvas.sceneRect() == rect
    assert canvas.scene().sceneRect() == rect
    assert window.isWindowModified()
    assert "scroll range" in window.statusBar().currentMessage().lower()
    zoom = zoom_factor_for(canvas)
    assert fit_canvas_to_view_for(canvas) == zoom
    assert canvas.sceneRect() == rect
    monkeypatch.setattr(sheet_setup_access, "content_bounds", original)
    QTest.keyClick(canvas.viewport(), Qt.Key.Key_F6)
    assert canvas.sceneRect().contains(_bounds(canvas))
    assert snapshot_canvas_state_for(canvas) == after
    assert history.capture_stack_snapshot() == stacks


def test_no_bounds_change_preserves_scrollbar_values_and_document(drawing, app):
    _window, canvas = drawing
    _drag(canvas, app)
    sheet_setup_access.apply_sheet_scene_rect_for(canvas)
    set_zoom_for(canvas, 1.0)
    canvas.centerOn(1700, 0)
    before = snapshot_canvas_state_for(canvas)
    scroll = canvas.horizontalScrollBar().value(), canvas.verticalScrollBar().value()
    rect = QRectF(canvas.sceneRect())
    canvas.services.history_service.notify_change()
    assert canvas.sceneRect() == rect
    assert (
        canvas.horizontalScrollBar().value(),
        canvas.verticalScrollBar().value(),
    ) == scroll
    assert snapshot_canvas_state_for(canvas) == before


@pytest.mark.parametrize("role", [None, "selection_outline"])
def test_transient_graphics_do_not_expand_live_scroll_range(drawing, role):
    _window, canvas = drawing
    before = snapshot_canvas_state_for(canvas)
    rect = QRectF(canvas.sceneRect())
    transient = QGraphicsRectItem(9000, 9000, 500, 500)
    transient.setData(0, role)
    canvas.scene().addItem(transient)
    try:
        canvas.services.history_service.notify_change()
        assert canvas.sceneRect() == rect
        assert snapshot_canvas_state_for(canvas) == before
    finally:
        canvas.scene().removeItem(transient)


def test_failed_drag_publication_restores_document_and_old_range(
    drawing, app, monkeypatch
):
    window, canvas = drawing
    before = snapshot_canvas_state_for(canvas)
    rect = QRectF(canvas.sceneRect())
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    monkeypatch.setattr(history, "push", lambda _command: False)
    _drag(canvas, app)
    assert snapshot_canvas_state_for(canvas) == before
    assert history.capture_stack_snapshot() == stacks
    assert canvas.sceneRect() == rect
    assert canvas.scene().sceneRect() == rect
    assert not services_for_window(window).canvas_document_service.is_dirty(canvas)


def test_refresh_without_error_observer_does_not_silently_swallow_failure(
    drawing, monkeypatch
):
    _window, canvas = drawing
    set_error_callback_for(canvas, None)

    def fail(_items):
        raise RuntimeError("synthetic bounds failure")

    monkeypatch.setattr(sheet_setup_access, "content_bounds", fail)
    with pytest.raises(RuntimeError, match="synthetic bounds failure"):
        sheet_setup_access.refresh_canvas_scroll_range_for(canvas)
