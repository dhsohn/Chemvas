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
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.ui.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas_model_access import atoms_for
from chemvas.ui.move_tool import MoveTool
from chemvas.ui.select_all_access import select_all_scene_items_for
from chemvas.ui.selection_collection_access import selection_snapshot_for
from chemvas.ui.transactions.document import DocumentSavepoint, MoveGestureScope
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


def _add_bond_with_graphics(canvas, a: int, b: int) -> int:
    from chemvas.ui.bond_graphics_access import add_bond_graphics_for
    from chemvas.ui.structure_mutation_access import add_bond_for

    bond_id = add_bond_for(canvas, a, b)
    add_bond_graphics_for(canvas, bond_id)
    return bond_id


def _draw_two_molecules(canvas) -> tuple[set[int], set[int]]:
    """Two disconnected two-atom molecules; returns their atom-id sets."""

    from chemvas.ui.structure_mutation_access import add_atom_for

    a1 = add_atom_for(canvas, "C", 100.0, 100.0)
    a2 = add_atom_for(canvas, "N", 140.0, 100.0)
    _add_bond_with_graphics(canvas, a1, a2)
    b1 = add_atom_for(canvas, "O", 300.0, 300.0)
    b2 = add_atom_for(canvas, "S", 340.0, 300.0)
    _add_bond_with_graphics(canvas, b1, b2)
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


def test_failed_boundary_drag_restores_stationary_endpoint_label_exactly(
    canvas,
) -> None:
    from chemvas.ui.structure_mutation_access import add_atom_for

    moving_id = add_atom_for(canvas, "C", 0.0, 0.0)
    stationary_id = add_atom_for(canvas, "CF3", 20.0, 0.0)
    outer_id = add_atom_for(canvas, "C", 40.0, 0.0)
    _add_bond_with_graphics(canvas, moving_id, stationary_id)
    outer_bond_id = _add_bond_with_graphics(canvas, stationary_id, outer_id)
    label = atom_items_for(canvas)[stationary_id]
    before_outer_bond = _bond_item_states(canvas, outer_bond_id)
    before = (
        label.toPlainText(),
        label._raw_text,
        label._anchor_element,
        label._anchor_at_end,
        label._stack,
        label.pos(),
        label.anchor_scene_rect(),
    )
    tool = MoveTool(canvas, context=canvas.services.tool_controller.context)
    assert tool._begin_selection_drag({moving_id}, [], QPointF())

    tool._apply_drag_delta(QPointF(50.0, 0.0))

    assert label.toPlainText() == "F3C"
    assert label._anchor_at_end is True
    assert _bond_item_states(canvas, outer_bond_id) != before_outer_bond
    with (
        mock.patch.object(
            canvas.services.history_service,
            "push",
            return_value=False,
        ),
        mock.patch.object(
            canvas.bond_renderer,
            "update_bond_geometry",
            side_effect=RuntimeError("injected rollback redraw failure"),
        ),
        pytest.raises(RuntimeError),
    ):
        tool._commit_selection_drag()

    assert (
        label.toPlainText(),
        label._raw_text,
        label._anchor_element,
        label._anchor_at_end,
        label._stack,
        label.pos(),
        label.anchor_scene_rect(),
    ) == before
    assert _bond_item_states(canvas, outer_bond_id) == before_outer_bond


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


def _bond_item_states(canvas, bond_id: int) -> list[tuple]:
    from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id

    states = []
    for item in bond_items_for_id(canvas, bond_id):
        pos = item.pos()
        line = item.line() if hasattr(item, "line") else None
        line_state = (
            (line.x1(), line.y1(), line.x2(), line.y2()) if line is not None else None
        )
        states.append(((pos.x(), pos.y()), line_state))
    return states


def test_failed_drag_does_not_rewrite_unscoped_bond_graphics(canvas) -> None:
    """A prior successful drag leaves interior bond items translated via
    ``moveBy`` (``pos != 0`` with stale local coordinates). The restore of a
    later, unrelated failed drag must not canonicalize those untouched items.
    """

    from chemvas.ui.structure_mutation_access import add_atom_for

    a1 = add_atom_for(canvas, "C", 100.0, 100.0)
    a2 = add_atom_for(canvas, "C", 140.0, 100.0)
    a3 = add_atom_for(canvas, "C", 180.0, 100.0)
    interior_bond_id = _add_bond_with_graphics(canvas, a1, a2)
    _add_bond_with_graphics(canvas, a2, a3)
    b1 = add_atom_for(canvas, "O", 300.0, 300.0)
    b2 = add_atom_for(canvas, "S", 340.0, 300.0)
    _add_bond_with_graphics(canvas, b1, b2)

    tool = MoveTool(canvas, context=canvas.services.tool_controller.context)
    # Drag 1 (succeeds): bond a1-a2 is interior, bond a2-a3 is a boundary
    # bond. The interior bond's items now carry a nonzero pos.
    assert tool._begin_selection_drag({a1, a2}, [], QPointF())
    tool._apply_drag_delta(QPointF(11.0, 9.0))
    tool._commit_selection_drag()

    interior_states = _bond_item_states(canvas, interior_bond_id)
    assert any(pos != (0.0, 0.0) for pos, _line in interior_states)
    after_first_drag = _document_state(canvas)
    ordered_items = [id(item) for item in canvas.scene().items()]

    # Drag 2 (fails at commit): moves the unrelated O-S fragment only.
    assert tool._begin_selection_drag({b1, b2}, [], QPointF())
    tool._apply_drag_delta(QPointF(5.0, 5.0))
    with mock.patch.object(
        canvas.services.history_service,
        "push",
        return_value=False,
    ):
        with pytest.raises(RuntimeError):
            tool._commit_selection_drag()

    assert _document_state(canvas) == after_first_drag
    assert _bond_item_states(canvas, interior_bond_id) == interior_states
    assert [id(item) for item in canvas.scene().items()] == ordered_items


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
