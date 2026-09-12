"""Real ring-button and hover-hotkey fusion, history and document round trips."""

import math

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton

from chemvas.core.document_io import read_document, write_document
from chemvas.features.graph import find_rings
from chemvas.ui.canvas_window_access import (
    restore_canvas_state_for,
    snapshot_canvas_state_for,
)
from chemvas.ui.scene_decoration_access import add_arrow_for
from tests.test_active_gesture_document_edits import qt_errors as qt_errors
from tests.test_chair_fusion_geometry import proper_crossings
from tests.test_note_editing_workflows import _click, _tool
from tests.test_note_editing_workflows import app as app
from tests.test_note_editing_workflows import drawing as drawing


def _ring_button(window, label):
    _tool(window, "benzene")
    button = next(
        button
        for button in window.findChildren(QToolButton)
        if button.toolTip() == label
    )
    assert button.isVisible() and button.isEnabled()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()


@pytest.mark.parametrize(
    "existing", ["Cyclohexane (Chair)", "Cyclohexane (Chair, flipped)"]
)
@pytest.mark.parametrize("route", ["button", "hotkey"])
@pytest.mark.parametrize(
    "label,key",
    [
        ("Benzene", Qt.Key.Key_A),
        ("Cyclohexane (Chair)", Qt.Key.Key_9),
        ("Cyclohexane (Chair, flipped)", Qt.Key.Key_0),
    ],
)
def test_chair_fusion_button_and_hotkey_roundtrip(
    drawing, qt_errors, tmp_path, monkeypatch, existing, route, label, key
):
    window, canvas = drawing
    _ring_button(window, existing)
    _click(canvas, QPointF(0, 0))
    _tool(window, "select")
    assert len(canvas.model.atoms) == 6
    before = snapshot_canvas_state_for(canvas)
    original_atoms = {key: (atom.x, atom.y) for key, atom in canvas.model.atoms.items()}
    old_cycle = find_rings(canvas.model.bonds)[0]
    old_points = [original_atoms[atom_id] for atom_id in old_cycle]
    anchor = canvas.model.bonds[1]
    first, second = canvas.model.atoms[anchor.a], canvas.model.atoms[anchor.b]
    midpoint = QPointF((first.x + second.x) / 2, (first.y + second.y) / 2)
    history = canvas.services.history_service
    count = len(history.state.history)

    if route == "button":
        _ring_button(window, label)
        _click(canvas, midpoint)
    else:
        canvas.setFocus()
        QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(midpoint))
        QApplication.processEvents()
        # Wayland cannot warp the system cursor for QTest. Feed the same native
        # viewport position to the hotkey's cursor query; hit testing stays real.
        global_pos = canvas.viewport().mapToGlobal(canvas.mapFromScene(midpoint))
        with monkeypatch.context() as cursor:
            cursor.setattr("chemvas.ui.hover.QCursor.pos", lambda: global_pos)
            QTest.keyClick(canvas, key)
        QApplication.processEvents()
    _tool(window, "select")
    assert not qt_errors
    assert len(canvas.model.atoms) == 10
    assert len([bond for bond in canvas.model.bonds if bond is not None]) == 11
    assert {
        key: (canvas.model.atoms[key].x, canvas.model.atoms[key].y)
        for key in original_atoms
    } == original_atoms
    assert all(
        math.hypot(
            canvas.model.atoms[bond.a].x - canvas.model.atoms[bond.b].x,
            canvas.model.atoms[bond.a].y - canvas.model.atoms[bond.b].y,
        )
        == pytest.approx(20)
        for bond in canvas.model.bonds
        if bond is not None
    )
    added_cycles = [
        cycle
        for cycle in find_rings(canvas.model.bonds)
        if set(cycle) - original_atoms.keys()
    ]
    assert len(added_cycles) == 1
    added_points = [
        (canvas.model.atoms[atom_id].x, canvas.model.atoms[atom_id].y)
        for atom_id in added_cycles[0]
    ]
    assert proper_crossings(old_points, added_points) == 0
    after = snapshot_canvas_state_for(canvas)
    assert after != before
    assert len(history.state.history) == count + 1
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after

    stacks = history.capture_stack_snapshot()
    _ring_button(window, "Benzene")
    _click(canvas, midpoint)
    _tool(window, "select")
    assert snapshot_canvas_state_for(canvas) == after
    history.verify_stack_snapshot(stacks)

    path = tmp_path / "fused-chair.chemvas"
    write_document(path, after, canvas.FILE_FORMAT_VERSION)
    restore_canvas_state_for(canvas, read_document(path).state)
    assert snapshot_canvas_state_for(canvas) == after


def test_chair_fusion_recording_failure_preserves_drawing_and_redo(
    drawing, monkeypatch
):
    window, canvas = drawing
    _ring_button(window, "Cyclohexane (Chair)")
    _click(canvas, QPointF(0, 0))
    _tool(window, "select")
    history = canvas.services.history_service
    add_arrow_for(canvas, QPointF(100, 100), QPointF(140, 100), "arrow")
    history.undo()
    before = snapshot_canvas_state_for(canvas)
    stacks = history.capture_stack_snapshot()
    assert history.can_redo()
    bond = canvas.model.bonds[1]
    first, second = canvas.model.atoms[bond.a], canvas.model.atoms[bond.b]
    midpoint = QPointF((first.x + second.x) / 2, (first.y + second.y) / 2)
    _ring_button(window, "Benzene")
    failure = RuntimeError("recording failed")

    def fail(_command):
        raise failure

    with monkeypatch.context() as patch:
        patch.setattr(history, "push", fail)
        with pytest.raises(RuntimeError) as error:
            canvas.services.structure.insert_controller.commit_template_insert(midpoint)
    assert error.value is failure
    assert snapshot_canvas_state_for(canvas) == before
    history.verify_stack_snapshot(stacks)

    canvas.services.structure.insert_controller.commit_template_insert(midpoint)
    assert len(canvas.model.atoms) == 10
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
