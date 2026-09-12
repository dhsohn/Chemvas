"""Edit-menu transforms cancel a pending move before recording their edit."""

import pytest
from PyQt6.QtCore import QPointF

from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.main_window_menu_bar import ALIGN_MENU_SPECS, DISTRIBUTE_MENU_SPECS
from chemvas.ui.main_window_ports import redo_action_for_window, undo_action_for_window
from chemvas.ui.scene_decoration_access import add_arrow_for
from tests.test_active_gesture_document_edits import (
    populate,
    release,
    start_drag,
)
from tests.test_active_gesture_document_edits import (
    qt_errors as qt_errors,
)
from tests.test_note_editing_workflows import app as app
from tests.test_note_editing_workflows import drawing as drawing


@pytest.mark.parametrize(
    "menu_name,action_name",
    [(None, "Flip Horizontal"), (None, "Flip Vertical")]
    + [("Align", text) for text, _mode in ALIGN_MENU_SPECS]
    + [("Distribute", text) for text, _axis in DISTRIBUTE_MENU_SPECS],
)
def test_menu_transform_cancels_move_and_retains_one_exact_undo(
    drawing, qt_errors, menu_name, action_name
):
    window, canvas = drawing
    point, item = populate(canvas, "arrow")
    add_arrow_for(canvas, QPointF(50.1, 80.2), QPointF(97.8, 89.6), "arrow")
    add_arrow_for(canvas, QPointF(-33.8, 130.4), QPointF(120.6, 152.1), "arrow")
    history = canvas.services.history_service
    add_arrow_for(canvas, QPointF(150, -70), QPointF(180, -70), "arrow")
    history.undo()
    assert history.can_redo()
    before = snapshot_canvas_state_for(canvas)
    length = len(history.state.history)
    end = start_drag(canvas, "arrow", point, item)
    assert snapshot_canvas_state_for(canvas) != before

    menu = next(
        action.menu()
        for action in window.menuBar().actions()
        if action.text() == "Edit"
    )
    if menu_name is not None:
        menu = next(
            action.menu() for action in menu.actions() if action.text() == menu_name
        )
    action = next(action for action in menu.actions() if action.text() == action_name)
    assert action.isEnabled()
    action.trigger()
    after = snapshot_canvas_state_for(canvas)
    assert after != before
    assert len(history.state.history) == length + 1
    assert not history.can_redo()
    stacks = history.capture_stack_snapshot()

    release(canvas, end)
    assert not qt_errors
    assert snapshot_canvas_state_for(canvas) == after
    history.verify_stack_snapshot(stacks)
    undo_action_for_window(window).trigger()
    assert snapshot_canvas_state_for(canvas) == before
    redo_action_for_window(window).trigger()
    assert snapshot_canvas_state_for(canvas) == after
