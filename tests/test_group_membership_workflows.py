"""Group edits remain repairable through the actual window's keyboard and mouse."""

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from chemvas.core.document_io import read_document
from chemvas.ui.canvas_group_state import group_state_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.select_all_access import select_all_scene_items_for
from chemvas.ui.structure_mutation_access import add_atom_for, add_bond_for
from tests.test_active_gesture_document_edits import qt_errors as qt_errors
from tests.test_group_membership_additions import _group
from tests.test_keyboard_focus_workflows import fresh_window as fresh_window
from tests.test_note_editing_workflows import _click, _tool
from tests.test_note_editing_workflows import app as app


def test_bond_drag_extends_group_then_keyboard_move_undo_reopen(
    fresh_window, app, tmp_path
):
    window, canvas = fresh_window
    _a, _b, group_id = _group(canvas)
    before = snapshot_canvas_state_for(canvas)
    _tool(window, "bond")
    start, end = (
        canvas.mapFromScene(QPointF(30, 0)),
        canvas.mapFromScene(QPointF(60, 0)),
    )
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    app.processEvents()
    assert len(canvas.model.atoms) == 3
    assert group_state_for(canvas).groups[group_id].atom_ids == set(canvas.model.atoms)
    drawn = snapshot_canvas_state_for(canvas)
    drawn_positions = {
        atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()
    }
    _tool(window, "select")
    newest = canvas.model.atoms[max(canvas.model.atoms)]
    _click(canvas, QPointF(newest.x, newest.y))
    QTest.keyClick(canvas, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    moved = snapshot_canvas_state_for(canvas)
    deltas = {
        (atom.x - drawn_positions[atom_id][0], atom.y - drawn_positions[atom_id][1])
        for atom_id, atom in canvas.model.atoms.items()
    }
    assert len(deltas) == 1 and deltas != {(0, 0)}
    assert moved["groups"] == drawn["groups"]
    QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert snapshot_canvas_state_for(canvas) == drawn
    QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert snapshot_canvas_state_for(canvas) == before
    for _ in range(2):
        QTest.keyClick(
            canvas,
            Qt.Key.Key_Z,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
    assert snapshot_canvas_state_for(canvas) == moved
    path = tmp_path / "grouped-sprout.chemvas"
    documents = canvas.services.document.canvas_document_session_service
    assert documents.save_to_file(str(path)) == []
    documents.apply_state(read_document(path).state)
    assert next(iter(group_state_for(canvas).groups.values())).atom_ids == set(
        canvas.model.atoms
    )


def test_single_molecule_group_shortcut_shows_status_guidance(fresh_window, app):
    window, canvas = fresh_window
    a = add_atom_for(canvas, "C", 0, 0)
    b = add_atom_for(canvas, "C", 30, 0)
    add_bond_for(canvas, a, b)
    canvas.services.structure.structure_build_service.render_model()
    _tool(window, "select")
    select_all_scene_items_for(canvas)
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service.capture_stack_snapshot()
    QTest.keyClick(canvas, Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert "Group needs at least two objects" in window.statusBar().currentMessage()
    assert "caption" in window.statusBar().currentMessage()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.verify_stack_snapshot(history)
