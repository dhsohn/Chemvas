"""Label/mark compound history shares the canonical exact rollback owner."""

import os
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.core.history import CompositeCommand
from chemvas.ui.atom_label_access import atom_label_service
from chemvas.ui.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas_document_metadata_state import (
    document_is_dirty_for,
    mark_document_clean_for,
)
from chemvas.ui.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas_scene_items_state import mark_items_for
from chemvas.ui.canvas_smiles_input_state import (
    last_smiles_input_for,
    set_last_smiles_input_for,
)
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.history_commands import ChangeAtomLabelCommand, DeleteSceneItemsCommand
from chemvas.ui.scene_decoration_access import add_mark_for_atom_for
from chemvas.ui.scene_item_state import mark_state_dict_for
from chemvas.ui.structure_mutation_access import add_bond_for
from chemvas.ui.transactions.document import DocumentSavepoint
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def canvas():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    view = build_canvas_view()
    yield view
    sip.delete(view)


def _command(canvas, atom_id, *, element="C", explicit=True):
    atom = canvas.model.atoms[atom_id]
    return ChangeAtomLabelCommand(
        atom_id=atom_id,
        before_element=atom.element,
        after_element=element,
        before_explicit_label=atom.explicit_label,
        after_explicit_label=explicit,
        before_smiles_input=last_smiles_input_for(canvas),
        after_smiles_input="after-label",
    )


def _edit(canvas, compound):
    atom_id = canvas.services.structure.canvas_atom_mutation_service.add_atom(
        "C", 0.1, -0.3
    )
    mark = (
        add_mark_for_atom_for(canvas, atom_id, QPointF(10, -10), kind="plus")
        if compound
        else None
    )
    set_last_smiles_input_for(canvas, "before-label")
    visible_atom_item_for(canvas, atom_id).setSelected(True)
    label = _command(canvas, atom_id)
    command = (
        CompositeCommand(
            [
                DeleteSceneItemsCommand.capture(
                    canvas, [mark_state_dict_for(canvas, mark)], [mark]
                ),
                label,
            ]
        )
        if mark is not None
        else label
    )
    history = canvas.services.history_service
    history.clear()
    before = snapshot_canvas_state_for(canvas)
    mark_document_clean_for(canvas, before)
    command.redo(canvas)
    assert history.push(command)
    return atom_id, mark, command, before, snapshot_canvas_state_for(canvas)


def _exact_state(canvas):
    return (
        snapshot_canvas_state_for(canvas),
        tuple(canvas.scene().items()),
        tuple(canvas.scene().selectedItems()),
        tuple(mark_items_for(canvas)),
        {key: tuple(items) for key, items in mark_registry_for(canvas).by_atom.items()},
        canvas.sceneRect(),
        canvas.scene().sceneRect(),
    )


@pytest.mark.parametrize("direction", ["undo", "redo"])
@pytest.mark.parametrize("compound", [False, True])
def test_failed_label_replay_restores_exact_scene_and_history_then_retries(
    canvas, monkeypatch, direction, compound
):
    atom_id, _mark, _command_value, before, after = _edit(canvas, compound)
    history = canvas.services.history_service
    if direction == "redo":
        history.undo()
    expected = _exact_state(canvas)
    stacks = history.capture_stack_snapshot()
    label_service = atom_label_service(canvas)
    original = label_service.restore_atom_item_interaction
    failures = []

    def fail_after_label_layout(*args, **kwargs):
        # This callback is reached after the real model and Qt label/dot change,
        # before the command has updated its SMILES-input metadata.
        failures.append(canvas.model.atoms[atom_id].explicit_label)
        if len(failures) == 1:
            raise RuntimeError("synthetic post-layout interaction failure")
        return original(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(
            label_service, "restore_atom_item_interaction", fail_after_label_layout
        )
        with pytest.raises(RuntimeError, match="post-layout interaction failure"):
            getattr(history, direction)()
    assert failures[0] is (direction == "redo")
    assert _exact_state(canvas) == expected
    history.verify_stack_snapshot(stacks)
    getattr(history, direction)()
    assert snapshot_canvas_state_for(canvas) == (
        before if direction == "undo" else after
    )
    assert document_is_dirty_for(canvas, snapshot_canvas_state_for(canvas)) is (
        direction == "redo"
    )
    assert visible_atom_item_for(canvas, atom_id).isSelected()


@pytest.mark.parametrize("direction", ["undo", "redo"])
def test_failed_compound_mark_replay_restores_label_and_mark_identity(
    canvas, monkeypatch, direction
):
    _atom_id, mark, _command_value, before, after = _edit(canvas, True)
    history = canvas.services.history_service
    if direction == "redo":
        history.undo()
    expected = _exact_state(canvas)
    stacks = history.capture_stack_snapshot()
    marks = canvas.services.scene_decoration.canvas_mark_scene_service
    original = marks.sync_marks_for_atom
    calls = 0

    def fail_after_registry_mutation(atom_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            assert (mark.scene() is canvas.scene()) is (direction == "undo")
            raise RuntimeError("synthetic mark reconciliation failure")
        return original(atom_id)

    with monkeypatch.context() as patch:
        patch.setattr(marks, "sync_marks_for_atom", fail_after_registry_mutation)
        with pytest.raises(RuntimeError, match="mark reconciliation failure"):
            getattr(history, direction)()
    assert calls
    assert _exact_state(canvas) == expected
    history.verify_stack_snapshot(stacks)
    getattr(history, direction)()
    assert snapshot_canvas_state_for(canvas) == (
        before if direction == "undo" else after
    )


@pytest.mark.parametrize("direction", ["undo", "redo"])
def test_standalone_label_failure_restores_original_graphics_without_inverse_rebuild(
    canvas, monkeypatch, direction
):
    atom_id, _mark, command, _before, _after = _edit(canvas, False)
    if direction == "redo":
        command.undo(canvas)
    expected = _exact_state(canvas)
    stacks = canvas.services.history_service.capture_stack_snapshot()
    service = atom_label_service(canvas)
    calls = []

    def fail_after_layout(*_args, **_kwargs):
        calls.append(canvas.model.atoms[atom_id].explicit_label)
        raise RuntimeError("synthetic label interaction unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(service, "restore_atom_item_interaction", fail_after_layout)
        with pytest.raises(RuntimeError, match="label interaction unavailable"):
            getattr(command, direction)(canvas)
    assert calls == [direction == "redo"]
    assert _exact_state(canvas) == expected
    canvas.services.history_service.verify_stack_snapshot(stacks)


@pytest.mark.parametrize("direction", ["undo", "redo"])
def test_real_canvas_restores_label_when_following_smiles_update_fails(
    canvas, monkeypatch, direction
):
    from chemvas.ui import history_commands

    atom_id, _mark, command, _before, _after = _edit(canvas, False)
    if direction == "redo":
        command.undo(canvas)
    expected = _exact_state(canvas)
    updates = []

    def fail_smiles_update(_canvas, value):
        assert canvas.model.atoms[atom_id].explicit_label is (direction == "redo")
        updates.append(value)
        raise RuntimeError("synthetic SMILES metadata update failure")

    with monkeypatch.context() as patch:
        patch.setattr(history_commands, "set_last_smiles_input_for", fail_smiles_update)
        with pytest.raises(RuntimeError, match="SMILES metadata update failure"):
            getattr(command, direction)(canvas)
    assert len(updates) == 1
    assert _exact_state(canvas) == expected


@pytest.mark.parametrize(
    ("element", "explicit"),
    [("C", True), ("N", False), ("Cl", True), ("Me", True), ("NH2", True)],
)
def test_label_replay_preserves_literal_alias_selection_smiles_and_other_atoms(
    canvas, element, explicit
):
    atoms = canvas.services.structure.canvas_atom_mutation_service
    atom_id = atoms.add_atom("C", 0.1, -0.3)
    partner = atoms.add_atom("C", 20.1, -0.3)
    add_bond_for(canvas, atom_id, partner)
    overlapping = atoms.add_atom("O", 0.1, -0.3)
    visible_atom_item_for(canvas, atom_id).setSelected(True)
    set_last_smiles_input_for(canvas, "before-label")
    history = canvas.services.history_service
    history.clear()
    before = snapshot_canvas_state_for(canvas)
    mark_document_clean_for(canvas, before)
    command = _command(canvas, atom_id, element=element, explicit=explicit)
    command.redo(canvas)
    assert history.push(command)
    after = snapshot_canvas_state_for(canvas)
    assert canvas.model.atoms[atom_id].element == element
    assert canvas.model.atoms[atom_id].explicit_label is explicit
    assert canvas.model.atoms[overlapping].element == "O"
    assert len(canvas.model.atoms) == 3  # Label replay must never merge overlaps.
    assert last_smiles_input_for(canvas) == "after-label"
    for _ in range(3):
        history.undo()
        assert snapshot_canvas_state_for(canvas) == before
        assert not document_is_dirty_for(canvas, snapshot_canvas_state_for(canvas))
        assert visible_atom_item_for(canvas, atom_id).isSelected()
        history.redo()
        assert snapshot_canvas_state_for(canvas) == after
        assert last_smiles_input_for(canvas) == "after-label"
        assert visible_atom_item_for(canvas, atom_id).isSelected()


@pytest.mark.parametrize("direction", ["undo", "redo"])
def test_compound_replay_captures_one_document_savepoint(canvas, direction):
    _atom_id, _mark, _command_value, _before, _after = _edit(canvas, True)
    history = canvas.services.history_service
    if direction == "redo":
        history.undo()
    with mock.patch.object(
        DocumentSavepoint, "capture", wraps=DocumentSavepoint.capture
    ) as capture:
        getattr(history, direction)()
    assert capture.call_count == 1


def test_nested_label_command_defers_to_existing_document_transaction(canvas):
    from chemvas.core.history import history_transaction_scope
    from chemvas.ui.transactions.document import document_transaction

    atom_id = canvas.services.structure.canvas_atom_mutation_service.add_atom("C", 0, 0)
    command = _command(canvas, atom_id)
    with mock.patch.object(
        DocumentSavepoint, "capture", wraps=DocumentSavepoint.capture
    ) as capture:
        with document_transaction(canvas), history_transaction_scope(canvas):
            command.redo(canvas)
    assert capture.call_count == 1
    assert canvas.model.atoms[atom_id].explicit_label
