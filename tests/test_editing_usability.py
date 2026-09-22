import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QToolButton

from chemvas.ui.canvas_service_ports import note_controller_for_access
from chemvas.ui.handle_state import active_handles_for
from chemvas.ui.main_window_ports import history_service_for_window
from chemvas.ui.scene_decoration_access import add_shape_for
from chemvas.ui.shape_record_access import require_shape_record_for
from tests.gui_workflow_support import _click, _tool
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing


@pytest.mark.parametrize("kind", ["rect", "rounded_rect", "ellipse", "circle"])
def test_first_shape_selection_exposes_resize_and_supports_undo(drawing, kind):
    window, canvas = drawing
    _tool(window, "select")
    shape = add_shape_for(canvas, QRectF(-60, -40, 100, 80), shape_kind=kind)
    before = require_shape_record_for(canvas, shape)
    assert before.shape_kind == kind
    _click(canvas, shape.sceneBoundingRect().center())
    handles = active_handles_for(canvas)
    assert len(handles) == 8
    handle = next(h for h in handles if h.data(1) == "shape_se")
    start = canvas.mapFromScene(handle.sceneBoundingRect().center())
    end = start + canvas.mapFromScene(QPointF(30, 20)) - canvas.mapFromScene(QPointF())
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end, 30)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    after = require_shape_record_for(canvas, shape)
    assert after.right > before.right + 20
    assert after.bottom > before.bottom + 10
    assert (after.left, after.top) == (before.left, before.top)
    history = history_service_for_window(window)
    history.undo()
    assert require_shape_record_for(canvas, shape) == before
    history.redo()
    assert require_shape_record_for(canvas, shape) == after


@pytest.mark.parametrize(
    "tooltip", ["Bold the selected text", "Italicize the selected text", "Align center"]
)
def test_pointer_travel_to_text_toolbar_preserves_partial_selection(drawing, tooltip):
    window, canvas = drawing
    _tool(window, "note")
    controller = note_controller_for_access(canvas)
    note = controller.create_text_note(QPointF(-80, 35), "alpha beta gamma")
    controller.begin_note_edit(note)
    cursor = note.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
    note.setTextCursor(cursor)
    original = note.toHtml()
    QTest.mouseMove(
        canvas.viewport(),
        canvas.mapFromScene(note.sceneBoundingRect().bottomRight() + QPointF(80, 40)),
    )
    button = next(b for b in window.findChildren(QToolButton) if b.toolTip() == tooltip)
    QTest.mouseMove(button, button.rect().center())
    for _ in range(30):
        QTest.qWait(10)
        assert note.hasFocus()
        assert note.textCursor().selectedText() == "alpha"
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert note.textCursor().selectedText() == "alpha"
    assert note.toHtml() != original
    note.document().undo()
    assert note.toHtml() == original
