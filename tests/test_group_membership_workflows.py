"""Group edits remain repairable through the actual window's keyboard and mouse."""

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from chemvas.core.document_io import read_document
from chemvas.ui.molecule.structure_mutation_access import add_bond_for
from chemvas.ui.selection.select_all_access import select_all_scene_items_for
from tests.gui_workflow_support import _click, _tool
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import fresh_window as fresh_window
from tests.gui_workflow_support import qt_errors as qt_errors
from tests.test_group_membership_additions import _group


def test_bond_drag_extends_group_then_keyboard_move_undo_reopen(
    fresh_window, app, tmp_path
):
    window, canvas = fresh_window
    _a, _b, group_id = _group(canvas)
    before = canvas.services.canvas_document_session_service.snapshot_state()
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
    assert canvas.runtime_state.group_state.groups[group_id].atom_ids == set(
        canvas.model.atoms
    )
    drawn = canvas.services.canvas_document_session_service.snapshot_state()
    drawn_positions = {
        atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()
    }
    _tool(window, "select")
    newest = canvas.model.atoms[max(canvas.model.atoms)]
    _click(canvas, QPointF(newest.x, newest.y))
    QTest.keyClick(canvas, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    moved = canvas.services.canvas_document_session_service.snapshot_state()
    deltas = {
        (atom.x - drawn_positions[atom_id][0], atom.y - drawn_positions[atom_id][1])
        for atom_id, atom in canvas.model.atoms.items()
    }
    assert len(deltas) == 1 and deltas != {(0, 0)}
    assert moved["groups"] == drawn["groups"]
    QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert canvas.services.canvas_document_session_service.snapshot_state() == drawn
    QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    for _ in range(2):
        QTest.keyClick(
            canvas,
            Qt.Key.Key_Z,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
    assert canvas.services.canvas_document_session_service.snapshot_state() == moved
    path = tmp_path / "grouped-sprout.chemvas"
    documents = canvas.services.canvas_document_session_service
    assert documents.save_to_file(str(path)) == []
    documents.apply_state(read_document(path).state)
    assert next(iter(canvas.runtime_state.group_state.groups.values())).atom_ids == set(
        canvas.model.atoms
    )


def test_single_molecule_group_shortcut_shows_status_guidance(fresh_window, app):
    window, canvas = fresh_window
    a = canvas.services.canvas_atom_mutation_service.add_atom("C", 0, 0)
    b = canvas.services.canvas_atom_mutation_service.add_atom("C", 30, 0)
    add_bond_for(canvas, a, b)
    canvas.services.structure_build_service.render_model()
    _tool(window, "select")
    select_all_scene_items_for(canvas)
    before = canvas.services.canvas_document_session_service.snapshot_state()
    history = canvas.services.history_service.capture_stack_snapshot()
    QTest.keyClick(canvas, Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert "Group needs at least two objects" in window.statusBar().currentMessage()
    assert "caption" in window.statusBar().currentMessage()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    canvas.services.history_service.verify_stack_snapshot(history)
