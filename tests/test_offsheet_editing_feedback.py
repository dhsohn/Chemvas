"""Sheet restrictions explain refusals without turning idle hover into alerts."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QCursor, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.canvas_hover_state import hover_state_for
from chemvas.ui.canvas_insert_state import insert_state_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.input_view_access import set_zoom_for
from chemvas.ui.main_window_ports import active_canvas_for_window, services_for_window
from chemvas.ui.select_all_access import select_all_scene_items_for
from chemvas.ui.selection_scene_access import clear_scene_selection_for
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
    for x in (0, 2600):
        add_bond_between_points_for(canvas, QPointF(x, 0), QPointF(x + 80, 0))
    canvas.services.input.tool_mode_controller.set_tool("select")
    canvas.services.history_service.clear()
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    set_zoom_for(canvas, 0.2)
    canvas.centerOn(0, 0)
    app.processEvents()
    yield window, canvas
    insert_state_for(canvas).template_active = False
    insert_state_for(canvas).smiles_active = False
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    window.close()
    app.processEvents()


def _move(canvas, position, buttons=Qt.MouseButton.NoButton):
    point = canvas.mapFromScene(position)
    assert canvas.viewport().rect().contains(point)
    QApplication.sendEvent(
        canvas.viewport(),
        QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(point),
            QPointF(canvas.viewport().mapToGlobal(point)),
            Qt.MouseButton.NoButton,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        ),
    )


def _assert_guidance(window):
    message = window.statusBar().currentMessage().lower()
    assert "sheet" in message
    assert "inside" in message
    assert "select" in message


@pytest.mark.parametrize("mode", ["bond", "note", "template", "smiles"])
def test_blocked_left_click_shows_real_status_without_mutating(drawing, mode):
    window, canvas = drawing
    if mode in {"template", "smiles"}:
        setattr(insert_state_for(canvas), f"{mode}_active", True)
    else:
        canvas.services.input.tool_mode_controller.set_tool(mode)
    before = snapshot_canvas_state_for(canvas)
    stacks = canvas.services.history_service.capture_stack_snapshot()
    window.statusBar().clearMessage()
    QTest.mouseClick(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=canvas.mapFromScene(QPointF(2500, 200)),
    )
    _assert_guidance(window)
    assert snapshot_canvas_state_for(canvas) == before
    assert canvas.services.history_service.capture_stack_snapshot() == stacks
    assert not services_for_window(window).canvas_document_service.is_dirty(canvas)


def test_drawing_drag_cancel_reports_once_even_when_release_returns_inside(drawing):
    window, canvas = drawing
    canvas.services.input.tool_mode_controller.set_tool("bond")
    before = snapshot_canvas_state_for(canvas)
    messages = []
    window.statusBar().messageChanged.connect(messages.append)
    window.statusBar().clearMessage()
    QTest.mousePress(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=canvas.mapFromScene(QPointF(0, 200)),
    )
    _move(canvas, QPointF(80, 200), Qt.MouseButton.LeftButton)
    for x in (2400, 2500, 2600):
        _move(canvas, QPointF(x, 200), Qt.MouseButton.LeftButton)
    _assert_guidance(window)
    assert len([message for message in messages if "inside" in message.lower()]) == 1
    _move(canvas, QPointF(80, 200), Qt.MouseButton.LeftButton)
    QTest.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=canvas.mapFromScene(QPointF(80, 200)),
    )
    assert snapshot_canvas_state_for(canvas) == before
    assert not canvas.services.history_service.can_undo()

    # The canceled gesture must not disable the next in-sheet drawing.
    QTest.mouseClick(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=canvas.mapFromScene(QPointF(0, 200)),
    )
    assert snapshot_canvas_state_for(canvas) != before
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    window.statusBar().clearMessage()
    QTest.mouseClick(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=canvas.mapFromScene(QPointF(2500, 200)),
    )
    _assert_guidance(window)
    assert len([message for message in messages if "inside" in message.lower()]) == 2


def test_drawing_release_outside_without_move_is_explained_and_canceled(drawing):
    window, canvas = drawing
    canvas.services.input.tool_mode_controller.set_tool("bond")
    before = snapshot_canvas_state_for(canvas)
    window.statusBar().clearMessage()
    QTest.mousePress(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=canvas.mapFromScene(QPointF(0, 200)),
    )
    QTest.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=canvas.mapFromScene(QPointF(2500, 200)),
    )
    _assert_guidance(window)
    assert snapshot_canvas_state_for(canvas) == before
    assert not canvas.services.history_service.can_undo()


@pytest.mark.parametrize(
    "target,key",
    [(2600, Qt.Key.Key_N), (2640, Qt.Key.Key_2), (2600, Qt.Key.Key_Delete)],
)
def test_offsheet_structure_shortcut_reports_without_creating_hover(
    drawing, monkeypatch, target, key
):
    window, canvas = drawing
    point = canvas.mapFromScene(QPointF(target, 0))
    # Bind the cursor read used by real hover/key routing. Wayland cannot warp
    # hardware pointers; monkeypatch restores this class method after each test.
    monkeypatch.setattr(QCursor, "pos", lambda: canvas.viewport().mapToGlobal(point))
    before = snapshot_canvas_state_for(canvas)
    window.statusBar().clearMessage()
    for _ in range(3):
        _move(canvas, QPointF(target, 0))
        canvas.services.hover.refresh()
    assert "inside" not in window.statusBar().currentMessage().lower()
    QTest.keyClick(canvas.viewport(), key)
    _assert_guidance(window)
    assert snapshot_canvas_state_for(canvas) == before
    assert not canvas.services.history_service.can_undo()
    assert hover_state_for(canvas).atom_id is None
    assert hover_state_for(canvas).bond_id is None
    assert not hover_state_for(canvas).items


@pytest.mark.parametrize(
    "button", [Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton]
)
def test_unrelated_buttons_do_not_show_boundary_warning(drawing, button):
    window, canvas = drawing
    canvas.services.input.tool_mode_controller.set_tool("bond")
    window.statusBar().clearMessage()
    QTest.mouseClick(
        canvas.viewport(), button, pos=canvas.mapFromScene(QPointF(2500, 200))
    )
    assert "inside" not in window.statusBar().currentMessage().lower()


def test_blank_hover_and_tool_view_keys_do_not_show_boundary_warning(
    drawing, monkeypatch
):
    window, canvas = drawing
    point = canvas.mapFromScene(QPointF(2500, 200))
    monkeypatch.setattr(QCursor, "pos", lambda: canvas.viewport().mapToGlobal(point))
    for key in (Qt.Key.Key_N, Qt.Key.Key_Space, Qt.Key.Key_F7):
        window.statusBar().clearMessage()
        QTest.keyClick(canvas.viewport(), key)
        assert "inside" not in window.statusBar().currentMessage().lower()


def test_existing_selection_delete_and_nudge_remain_allowed_offsheet(
    drawing, monkeypatch
):
    window, canvas = drawing
    point = canvas.mapFromScene(QPointF(2600, 0))
    monkeypatch.setattr(QCursor, "pos", lambda: canvas.viewport().mapToGlobal(point))
    select_all_scene_items_for(canvas)
    before = snapshot_canvas_state_for(canvas)
    window.statusBar().clearMessage()
    QTest.keyClick(
        canvas.viewport(), Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier
    )
    assert snapshot_canvas_state_for(canvas) != before
    assert "inside" not in window.statusBar().currentMessage().lower()
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    QTest.keyClick(canvas.viewport(), Qt.Key.Key_Delete)
    assert not canvas.model.atoms
    assert "inside" not in window.statusBar().currentMessage().lower()
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before


def test_in_sheet_hover_edit_and_exact_undo_remain_available(drawing, monkeypatch):
    window, canvas = drawing
    clear_scene_selection_for(canvas)
    point = canvas.mapFromScene(QPointF(0, 0))
    monkeypatch.setattr(QCursor, "pos", lambda: canvas.viewport().mapToGlobal(point))
    before = snapshot_canvas_state_for(canvas)
    window.statusBar().clearMessage()
    QTest.keyClick(canvas.viewport(), Qt.Key.Key_N)
    assert canvas.model.atoms[0].element == "N"
    assert "inside" not in window.statusBar().currentMessage().lower()
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before


@pytest.mark.parametrize("key", [Qt.Key.Key_Shift, Qt.Key.Key_Space, Qt.Key.Key_F7])
def test_offsheet_structure_tool_and_view_keys_are_not_refused(
    drawing, monkeypatch, key
):
    window, canvas = drawing
    point = canvas.mapFromScene(QPointF(2600, 0))
    monkeypatch.setattr(QCursor, "pos", lambda: canvas.viewport().mapToGlobal(point))
    before = snapshot_canvas_state_for(canvas)
    window.statusBar().clearMessage()
    QTest.keyClick(canvas.viewport(), key)
    assert "inside" not in window.statusBar().currentMessage().lower()
    assert snapshot_canvas_state_for(canvas) == before
    assert not canvas.services.history_service.can_undo()


@pytest.mark.parametrize("cancel", [False, True])
def test_eraser_held_move_reaches_offsheet_structure_with_exact_history(
    drawing, cancel
):
    window, canvas = drawing
    canvas.services.input.tool_mode_controller.set_tool("delete")
    before = snapshot_canvas_state_for(canvas)
    window.statusBar().clearMessage()
    QTest.mousePress(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=canvas.mapFromScene(QPointF(0, 200)),
    )
    _move(canvas, QPointF(2640, 0), Qt.MouseButton.LeftButton)
    assert snapshot_canvas_state_for(canvas) != before
    assert not canvas.services.history_service.can_undo()
    assert "inside" not in window.statusBar().currentMessage().lower()
    if cancel:
        QTest.keyClick(canvas.viewport(), Qt.Key.Key_Escape)
    QTest.mouseRelease(
        canvas.viewport(),
        Qt.MouseButton.LeftButton,
        pos=canvas.mapFromScene(QPointF(2640, 0)),
    )
    if cancel:
        assert not canvas.services.history_service.can_undo()
    else:
        assert canvas.services.history_service.can_undo()
        canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    assert not services_for_window(window).canvas_document_service.is_dirty(canvas)
