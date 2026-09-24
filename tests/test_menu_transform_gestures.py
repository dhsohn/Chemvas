"""Edit-menu transforms cancel a pending move before recording their edit."""

import pytest
from PyQt6.QtCore import QPointF

from chemvas.ui.window.main_window_menu_bar import (
    ALIGN_MENU_SPECS,
    DISTRIBUTE_MENU_SPECS,
)
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing
from tests.gui_workflow_support import (
    populate,
    release,
    start_drag,
)
from tests.gui_workflow_support import (
    qt_errors as qt_errors,
)


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
    canvas.services.scene_decoration_service.add_arrow(
        QPointF(50.1, 80.2), QPointF(97.8, 89.6), "arrow"
    )
    canvas.services.scene_decoration_service.add_arrow(
        QPointF(-33.8, 130.4), QPointF(120.6, 152.1), "arrow"
    )
    history = canvas.services.history_service
    canvas.services.scene_decoration_service.add_arrow(
        QPointF(150, -70), QPointF(180, -70), "arrow"
    )
    history.undo()
    assert history.can_redo()
    before = canvas.services.canvas_document_session_service.snapshot_state()
    length = len(history.state.history)
    end = start_drag(canvas, "arrow", point, item)
    assert canvas.services.canvas_document_session_service.snapshot_state() != before

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
    after = canvas.services.canvas_document_session_service.snapshot_state()
    assert after != before
    assert len(history.state.history) == length + 1
    assert not history.can_redo()
    stacks = history.capture_stack_snapshot()

    release(canvas, end)
    assert not qt_errors
    assert canvas.services.canvas_document_session_service.snapshot_state() == after
    history.verify_stack_snapshot(stacks)
    window.ui_references.undo_action.trigger()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    window.ui_references.redo_action.trigger()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after
