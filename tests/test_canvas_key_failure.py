"""Real Qt dispatch must survive a rejected edit, not just a direct Python call."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("kind", ["shape", "ts_bracket"])
def test_failed_key_edit_preserves_document_and_history(kind):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), kind],
        cwd=root,
        env={
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "PYTHONPATH": os.pathsep.join([str(root / "app"), str(root)]),
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "key failure recovered" in result.stdout


def _exercise_key_failure(kind):
    from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    from chemvas.ui.canvas_lifecycle import schedule_canvas_deletion_for
    from chemvas.ui.canvas_scene_items_state import (
        shape_items_for,
        ts_bracket_items_for,
    )
    from chemvas.ui.canvas_window_access import set_error_callback_for
    from tests.canvas_factory import build_canvas_view

    # The red test aborts inside Qt; do not leave a large core dump behind.
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    app = QApplication.instance() or QApplication([])
    canvas = build_canvas_view()
    session = canvas.services.document.canvas_document_session_service
    history = canvas.services.history_service
    limit = 2**53 - 1
    item_state = {
        "kind": kind,
        "left": limit - 10,
        "right": limit - 1,
        "top": 0,
        "bottom": 100,
        **(
            {"shape_kind": "rect", "stroke_style": "solid"}
            if kind == "shape"
            else {"bracket_kind": "square_pair"}
        ),
    }
    key = "shapes" if kind == "shape" else "ts_brackets"
    session.apply_state({**session.snapshot_state(), key: [item_state]})
    extreme = (shape_items_for if kind == "shape" else ts_bracket_items_for)(canvas)[0]
    decoration = canvas.services.scene_decoration.scene_decoration_service
    normal = decoration.add_shape(QRectF(20, 30, 50, 40))
    decoration.add_shape(QRectF(100, 130, 50, 40))
    history.undo()
    normal.setSelected(True)
    extreme.setSelected(True)
    canvas.resize(800, 600)
    canvas.show()
    canvas.centerOn(QPointF(0, 0))
    assert QTest.qWaitForWindowExposed(canvas)
    app.processEvents()
    before = session.snapshot_state()
    stacks = (tuple(history.state.history), tuple(history.state.redo_stack))
    notices = []
    set_error_callback_for(canvas, notices.append)

    QTest.keyPress(
        canvas.viewport(), Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier
    )

    assert notices == ["The current interaction could not be completed. Try again."]
    assert session.snapshot_state() == before
    assert (tuple(history.state.history), tuple(history.state.redo_stack)) == stacks
    assert normal.isSelected() and extreme.isSelected()
    # The next valid key edit still works, and so do its exact undo and redo.
    extreme.setSelected(False)
    QTest.keyPress(
        canvas.viewport(), Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier
    )
    after = session.snapshot_state()
    assert after != before
    history.undo()
    assert session.snapshot_state() == before
    history.redo()
    assert session.snapshot_state() == after
    schedule_canvas_deletion_for(canvas)
    app.sendPostedEvents(canvas, QEvent.Type.DeferredDelete)
    print("key failure recovered")


if __name__ == "__main__":
    _exercise_key_failure(sys.argv[1])
