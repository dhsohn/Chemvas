"""Behavior tests for the footprint-scoped move savepoint (ADR 0003).

A selection move captures a savepoint restricted to the gesture's mutation
footprint. These tests pin the user-observable contract: a move gesture that
fails mid-frame or at commit restores the document — including parts outside
the dragged selection — exactly, and the scoped capture really skips the
rest of the document.
"""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from chemvas.ui.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas_model_access import atoms_for
from chemvas.ui.move_tool import MoveTool
from chemvas.ui.select_all_access import select_all_scene_items_for
from chemvas.ui.selection_collection_access import selection_snapshot_for
from chemvas.ui.transactions.document import DocumentSavepoint, MoveGestureScope
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app() -> QApplication:
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app: QApplication):
    view = build_canvas_view()
    yield view
    view.services.document.canvas_scene_reset_service.clear_scene()
    view.close()


def _document_state(canvas) -> dict:
    return canvas.services.document.canvas_document_session_service.snapshot_state()


def _draw_two_molecules(canvas) -> tuple[set[int], set[int]]:
    """Two disconnected two-atom molecules; returns their atom-id sets."""

    from chemvas.ui.structure_mutation_access import add_atom_for, add_bond_for

    a1 = add_atom_for(canvas, "C", 100.0, 100.0)
    a2 = add_atom_for(canvas, "N", 140.0, 100.0)
    add_bond_for(canvas, a1, a2)
    b1 = add_atom_for(canvas, "O", 300.0, 300.0)
    b2 = add_atom_for(canvas, "S", 340.0, 300.0)
    add_bond_for(canvas, b1, b2)
    return {a1, a2}, {b1, b2}


def _label_positions(canvas) -> dict[int, tuple[float, float]]:
    positions = {}
    for atom_id, item in atom_items_for(canvas).items():
        if item is None:
            continue
        pos = item.pos()
        positions[atom_id] = (pos.x(), pos.y())
    return positions


def test_mid_move_failure_restores_whole_document(canvas) -> None:
    molecule_a, _molecule_b = _draw_two_molecules(canvas)
    drawn = _document_state(canvas)
    drawn_labels = _label_positions(canvas)
    drawn_items = {id(item) for item in canvas.scene().items()}

    tool = MoveTool(canvas, context=canvas.services.tool_controller.context)
    assert tool._begin_selection_drag(set(molecule_a), [], QPointF())
    tool._apply_drag_delta(QPointF(15.0, -7.0))

    boom = RuntimeError("mid-frame failure")
    with mock.patch(
        "chemvas.ui.selection_drag_tool.shift_selection_outlines_for",
        side_effect=boom,
    ):
        with pytest.raises(RuntimeError) as excinfo:
            tool._apply_drag_delta(QPointF(3.0, 3.0))
    assert excinfo.value is boom

    assert _document_state(canvas) == drawn
    assert _label_positions(canvas) == drawn_labels
    assert {id(item) for item in canvas.scene().items()} == drawn_items


def test_commit_push_failure_restores_document_and_scene(canvas) -> None:
    _draw_two_molecules(canvas)
    assert select_all_scene_items_for(canvas)
    snapshot = selection_snapshot_for(canvas)
    assert snapshot is not None

    drawn = _document_state(canvas)
    drawn_labels = _label_positions(canvas)
    drawn_items = {id(item) for item in canvas.scene().items()}

    tool = MoveTool(canvas, context=canvas.services.tool_controller.context)
    assert tool._begin_selection_drag(
        set(snapshot.selected_atom_ids),
        list(snapshot.selection_items),
        QPointF(),
    )
    tool._apply_drag_delta(QPointF(15.0, -7.0))

    with mock.patch.object(
        canvas.services.history_service,
        "push",
        return_value=False,
    ):
        with pytest.raises(RuntimeError):
            tool._commit_selection_drag()

    assert _document_state(canvas) == drawn
    assert _label_positions(canvas) == drawn_labels
    # A failed commit may have rebuilt selection outlines after the capture;
    # the restore must remove those and re-attach the captured items.
    assert {id(item) for item in canvas.scene().items()} == drawn_items


def test_moved_drag_still_pushes_one_command_and_round_trips(canvas) -> None:
    molecule_a, _molecule_b = _draw_two_molecules(canvas)
    drawn = _document_state(canvas)
    history = canvas.services.history_service
    history_length = len(history.state.history)

    tool = MoveTool(canvas, context=canvas.services.tool_controller.context)
    assert tool._begin_selection_drag(set(molecule_a), [], QPointF())
    tool._apply_drag_delta(QPointF(15.0, -7.0))
    tool._commit_selection_drag()

    assert len(history.state.history) == history_length + 1
    moved = _document_state(canvas)
    assert moved != drawn

    history.undo()
    assert _document_state(canvas) == drawn
    history.redo()
    assert _document_state(canvas) == moved


def test_scoped_capture_skips_atoms_outside_the_footprint(canvas) -> None:
    molecule_a, molecule_b = _draw_two_molecules(canvas)
    scope = MoveGestureScope(
        atom_ids=frozenset(molecule_a),
        bond_ids=frozenset({0}),
        scene_items=tuple(
            item
            for atom_id in molecule_a
            if (item := atom_items_for(canvas).get(atom_id)) is not None
        ),
    )
    savepoint = DocumentSavepoint.capture(canvas, move_scope=scope)
    captured_atoms = {
        id(atom)
        for snapshot in savepoint.objects
        for atom in [snapshot.target]
        if atom in atoms_for(canvas).values()
    }
    scoped_atoms = {id(atoms_for(canvas)[atom_id]) for atom_id in molecule_a}
    unscoped_atoms = {id(atoms_for(canvas)[atom_id]) for atom_id in molecule_b}
    assert scoped_atoms <= captured_atoms
    assert not (unscoped_atoms & captured_atoms)
    savepoint.release()
