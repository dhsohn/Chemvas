import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QTransform
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.domain.document import VALID_ARROW_KINDS
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.graphics_items import NoSelectPathItem
from chemvas.ui.handle_state import active_handles_for
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    history_service_for_window,
    services_for_window,
    set_zoom_percent_for_window,
    tool_action_for_window,
)
from chemvas.ui.scene_decoration_access import add_arrow_for, add_shape_for
from chemvas.ui.scene_group_operations import group_selection_for
from chemvas.ui.scene_item_state_serialization import arrow_state_dict


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def drawing(app):
    window = build_main_window()
    window.resize(1120, 700)
    window.show()
    canvas = active_canvas_for_window(window)
    set_zoom_percent_for_window(window, 100)
    tool_action_for_window(window, "select").trigger()
    canvas.setFocus()
    app.processEvents()
    QTest.qWait(20)
    yield window, canvas
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    window.close()
    app.processEvents()


def _add(canvas, kind="line", y=0.0):
    return add_arrow_for(canvas, QPointF(-70, y), QPointF(70, y), kind)


def _click(canvas, pos, modifiers=Qt.KeyboardModifier.NoModifier):
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, modifiers, pos)
    QApplication.processEvents()


def _drag(canvas, start, end, *, moves=True):
    QTest.mousePress(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        start,
    )
    if moves:
        QTest.mouseMove(canvas.viewport(), end, 20)
    QTest.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        end,
    )
    QApplication.processEvents()


@pytest.mark.parametrize("zoom", [50, 100, 200, 400])
@pytest.mark.parametrize("kind", ["line", "arrow", "line_dashed"])
def test_unselected_stroke_has_screen_space_click_tolerance(drawing, zoom, kind):
    window, canvas = drawing
    item = _add(canvas, kind)
    set_zoom_percent_for_window(window, zoom)
    origin = canvas.mapFromScene(QPointF(0, 0))
    _click(canvas, origin + QPoint(0, 5))
    assert item.isSelected()
    assert not active_handles_for(canvas)
    _click(canvas, origin + QPoint(0, 10))
    assert not item.isSelected()


@pytest.mark.parametrize("zoom", [100, 200])
@pytest.mark.parametrize("kind", ["line", "arrow"])
@pytest.mark.parametrize("moves", [True, False])
def test_first_press_drags_and_round_trips_history(drawing, zoom, kind, moves):
    window, canvas = drawing
    item = _add(canvas, kind)
    set_zoom_percent_for_window(window, zoom)
    history = history_service_for_window(window)
    before = arrow_state_dict(item)
    count = len(history.state.history)
    origin = canvas.mapFromScene(QPointF(0, 0))
    delta = QPoint(24, 14)
    _drag(canvas, origin, origin + delta, moves=moves)
    assert item.isSelected()
    assert item.pos() == QPointF(24 * 100 / zoom, 14 * 100 / zoom)
    assert len(history.state.history) == count + 1
    after = arrow_state_dict(item)
    history.undo()
    assert arrow_state_dict(item) == before
    history.redo()
    assert arrow_state_dict(item) == after


@pytest.mark.parametrize("zoom", [50, 100, 200, 400])
@pytest.mark.parametrize("kind", ["line", "arrow"])
def test_click_jitter_preserves_geometry_redo_and_handle_toggle(drawing, zoom, kind):
    window, canvas = drawing
    item = _add(canvas, kind)
    set_zoom_percent_for_window(window, zoom)
    history = history_service_for_window(window)
    item.setSelected(True)
    origin = canvas.mapFromScene(QPointF(0, 0))
    _drag(canvas, origin, origin + QPoint(24, 14))
    history.undo()
    item.setSelected(True)
    before = arrow_state_dict(item)
    undo = list(history.state.history)
    redo = list(history.state.redo_stack)
    assert redo
    origin = canvas.mapFromScene(QPointF(0, 0))
    _drag(canvas, origin, origin + QPoint(1, 0))
    assert arrow_state_dict(item) == before
    assert history.state.history == undo
    assert history.state.redo_stack == redo
    assert len(active_handles_for(canvas)) == 2
    _drag(canvas, origin, origin + QPoint(1, 0))
    assert not active_handles_for(canvas)
    assert arrow_state_dict(item) == before
    assert history.state.redo_stack == redo


@pytest.mark.parametrize("selected", [False, True])
def test_curved_arrow_does_not_select_its_empty_interior(drawing, selected):
    _, canvas = drawing
    item = _add(canvas, "curved_single")
    item.setSelected(selected)
    # The quadratic's midpoint is (0,21), ten pixels below this empty point.
    interior = QPointF(0, 11)
    assert not item.shape().contains(item.mapFromScene(interior))
    _click(canvas, canvas.mapFromScene(interior))
    assert not item.isSelected()
    assert not active_handles_for(canvas)


def test_near_strokes_pick_the_nearest_and_shift_toggles(drawing):
    _, canvas = drawing
    nearest = _add(canvas)
    upper = _add(canvas, y=8)
    # The newer item's stacking order must not beat the closer stroke.
    point = canvas.mapFromScene(QPointF(0, 3))
    _click(canvas, point)
    assert nearest.isSelected()
    assert not upper.isSelected()
    _click(canvas, point, Qt.KeyboardModifier.ShiftModifier)
    assert not nearest.isSelected()
    _click(canvas, point, Qt.KeyboardModifier.ShiftModifier)
    assert nearest.isSelected()


def test_first_press_on_group_member_drags_the_group(drawing):
    window, canvas = drawing
    first = _add(canvas)
    second = _add(canvas, y=40)
    first.setSelected(True)
    second.setSelected(True)
    assert group_selection_for(canvas)
    canvas.scene().clearSelection()
    history = history_service_for_window(window)
    count = len(history.state.history)
    origin = canvas.mapFromScene(QPointF(0, 0))
    _drag(canvas, origin, origin + QPoint(24, 14))
    assert first.pos() == second.pos() == QPointF(24, 14)
    assert len(history.state.history) == count + 1


def test_release_only_movement_of_selected_arrow_is_a_drag_not_a_click(drawing):
    _, canvas = drawing
    item = _add(canvas)
    item.setSelected(True)
    origin = canvas.mapFromScene(QPointF(0, 0))
    _drag(canvas, origin, origin + QPoint(24, 14), moves=False)
    assert item.pos() == QPointF(24, 14)
    assert not active_handles_for(canvas)


@pytest.mark.parametrize("zoom", [50, 100, 200, 400])
def test_slow_drag_accumulates_and_keeps_subthreshold_frames_after_start(drawing, zoom):
    window, canvas = drawing
    item = _add(canvas)
    item.setSelected(True)
    set_zoom_percent_for_window(window, zoom)
    history = history_service_for_window(window)
    count = len(history.state.history)
    origin = canvas.mapFromScene(QPointF(0, 0))
    threshold = QApplication.startDragDistance()
    assert threshold > 1
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=origin)
    for distance in range(1, threshold + 2):
        # Pace widget events explicitly beyond the canvas drag throttle.
        QTest.qWait(20)
        QTest.mouseMove(canvas.viewport(), origin + QPoint(distance, 0), 20)
        QApplication.processEvents()
        if distance < threshold:
            assert item.pos() == QPointF()
        else:
            assert item.pos() == QPointF(distance * 100 / zoom, 0)
    QTest.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=origin + QPoint(threshold + 1, 0),
    )
    assert len(history.state.history) == count + 1


@pytest.mark.parametrize("distance", [1, 24])
def test_tool_switch_cancels_pending_or_active_arrow_drag(drawing, distance):
    window, canvas = drawing
    item = _add(canvas)
    history = history_service_for_window(window)
    before = arrow_state_dict(item)
    undo = list(history.state.history)
    origin = canvas.mapFromScene(QPointF(0, 0))
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=origin)
    QTest.qWait(20)
    QTest.mouseMove(canvas.viewport(), origin + QPoint(distance, 0), 20)
    QApplication.processEvents()
    assert item.pos() == QPointF(distance if distance > 1 else 0, 0)
    tool_action_for_window(window, "line").trigger()
    assert arrow_state_dict(item) == before
    assert history.state.history == undo
    # End the synthetic pointer sequence without drawing with the new tool.
    tool_action_for_window(window, "select").trigger()
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=origin)
    _drag(canvas, origin, origin + QPoint(24, 14))
    assert item.pos() == QPointF(24, 14)


def test_near_picking_ignores_hidden_items_and_respects_actual_item_hits(drawing):
    _, canvas = drawing
    item = _add(canvas)
    hit = canvas_services_for(canvas).selection.hit_testing_service
    assert hit.item_at_scene_pos(QPointF(0, 4)) is item
    item.hide()
    assert hit.item_at_scene_pos(QPointF(0, 4)) is None
    item.show()
    # An exact stroke hit wins over the wider corridor of a later item.
    _add(canvas, y=4)
    assert hit.item_at_scene_pos(QPointF(0, 0)) is item


def test_near_picking_maps_rotated_items_and_anisotropic_views(drawing):
    _, canvas = drawing
    item = _add(canvas)
    item.setRotation(90)
    item.setPos(10, 15)
    canvas.setTransform(QTransform().scale(2, 0.5))
    hit = canvas_services_for(canvas).selection.hit_testing_service
    center = canvas.viewportTransform().map(item.mapToScene(QPointF(0, 0)))
    inverse, ok = canvas.viewportTransform().inverted()
    assert ok
    assert hit.item_at_scene_pos(inverse.map(center + QPointF(5, 0))) is item
    assert hit.item_at_scene_pos(inverse.map(center + QPointF(10, 0))) is None


@pytest.mark.parametrize("kind", sorted(VALID_ARROW_KINDS))
def test_stroke_only_hit_shape_preserves_original_figure_bounds(drawing, kind):
    _, canvas = drawing
    for length in [20, 60, 80, 140]:
        for direction in [QPointF(1, 0), QPointF(0, 1), QPointF(0.6, 0.8)]:
            end = direction * length
            item = add_arrow_for(canvas, QPointF(), end, kind)
            original = NoSelectPathItem(item.path())
            original.setPen(item.pen())
            original.setBrush(item.brush())
            expected = original.boundingRect()
            actual = item.boundingRect()
            assert (
                actual.x(),
                actual.y(),
                actual.width(),
                actual.height(),
            ) == pytest.approx(
                (expected.x(), expected.y(), expected.width(), expected.height()),
                rel=0,
                abs=1e-9,
            ), (kind, length, direction)


@pytest.mark.parametrize("panel_z", [-10, 10])
def test_foreground_stroke_can_be_picked_nearby_over_a_background_panel(
    drawing, panel_z
):
    _, canvas = drawing
    panel = add_shape_for(canvas, QRectF(-90, -30, 180, 60), shape_kind="rectangle")
    panel.setZValue(panel_z)
    line = _add(canvas)
    _click(canvas, canvas.mapFromScene(QPointF(0, 3)))
    assert line.isSelected() is (panel_z < line.zValue())
    assert panel.isSelected() is (panel_z > line.zValue())


@pytest.mark.parametrize("kind", ["line", "arrow"])
@pytest.mark.parametrize("offset", [0, 4])
def test_ctrl_click_adds_an_arrow_without_replacing_the_selection(
    drawing, kind, offset
):
    window, canvas = drawing
    first = _add(canvas, kind)
    second = _add(canvas, kind, y=40)
    history = history_service_for_window(window)
    before = [arrow_state_dict(item) for item in (first, second)]
    count = len(history.state.history)
    _click(canvas, canvas.mapFromScene(QPointF(0, 0)))
    point = canvas.mapFromScene(QPointF(0, 40)) + QPoint(0, offset)
    _click(canvas, point, Qt.KeyboardModifier.ControlModifier)
    assert first.isSelected() and second.isSelected()
    assert not active_handles_for(canvas)
    # Ctrl on an already selected arrow retains the established handle click.
    _click(canvas, point, Qt.KeyboardModifier.ControlModifier)
    assert first.isSelected() and second.isSelected()
    assert len(active_handles_for(canvas)) == 2
    assert [arrow_state_dict(item) for item in (first, second)] == before
    assert len(history.state.history) == count
