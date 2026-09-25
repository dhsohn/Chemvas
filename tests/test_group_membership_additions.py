from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id

"""New structure geometry keeps the editable molecule in its existing group."""

import pytest
from PyQt6.QtCore import QPointF

from chemvas.core.document_io import read_document
from chemvas.ui.canvas.canvas_group_state import register_group_for
from chemvas.ui.molecule.structure_mutation_access import add_bond_for
from chemvas.ui.scene.scene_group_operations import group_selection_for
from tests.native_canvas_support import app as app
from tests.native_canvas_support import canvas as canvas


def _group(canvas):
    a = canvas.services.canvas_atom_mutation_service.add_atom("C", 0, 0)
    b = canvas.services.canvas_atom_mutation_service.add_atom("C", 30, 0)
    add_bond_for(canvas, a, b)
    canvas.services.structure_build_service.render_model()
    note = canvas.services.scene_item_controller.create_scene_item_from_state(
        {"kind": "note", "text": "Compound", "x": 0, "y": 60}
    )
    group_id = register_group_for(
        canvas, {a, b}, [require_scene_record_id(item) for item in [note]]
    )
    return a, b, group_id


@pytest.mark.parametrize("kind", ["sprout", "fuse", "join-ungrouped"])
def test_new_geometry_extends_group_and_roundtrips(canvas, tmp_path, kind):
    a, b, group_id = _group(canvas)
    if kind == "join-ungrouped":
        c = canvas.services.canvas_atom_mutation_service.add_atom("C", 60, 0)
        d = canvas.services.canvas_atom_mutation_service.add_atom("O", 90, 0)
        add_bond_for(canvas, c, d)
    group = canvas.runtime_state.group_state.groups[group_id]
    before = canvas.services.canvas_document_session_service.snapshot_state()
    before_atom = canvas.model.next_atom_id
    before_bond = len(canvas.model.bonds)
    if kind == "sprout":
        c = canvas.services.canvas_atom_mutation_service.add_atom("C", 60, 0)
        add_bond_for(canvas, b, c)
    elif kind == "fuse":
        c = canvas.services.canvas_atom_mutation_service.add_atom("C", 30, 30)
        d = canvas.services.canvas_atom_mutation_service.add_atom("C", 0, 30)
        for x, y in ((b, c), (c, d), (d, a)):
            add_bond_for(canvas, x, y)
    else:
        add_bond_for(canvas, b, c)
    canvas.services.canvas_history_recording_service.record_additions(
        before_atom, before_bond
    )
    canvas.services.structure_build_service.render_model()
    assert canvas.runtime_state.group_state.groups[group_id].atom_ids == set(
        canvas.model.atoms
    )
    assert group.atom_ids == {a, b}, "The Undo snapshot must not be mutated in place"
    after = canvas.services.canvas_document_session_service.snapshot_state()
    history = canvas.services.history_service
    history.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert canvas.runtime_state.group_state.groups[group_id] is group
    history.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after
    path = tmp_path / "extended-group.chemvas"
    documents = canvas.services.canvas_document_session_service
    assert documents.save_to_file(str(path)) == []
    documents.apply_state(read_document(path).state)
    assert next(iter(canvas.runtime_state.group_state.groups.values())).atom_ids == set(
        canvas.model.atoms
    )


def test_sprout_builder_failure_restores_group_and_document(canvas, monkeypatch):
    _a, _b, group_id = _group(canvas)
    group = canvas.runtime_state.group_state.groups[group_id]
    before = canvas.services.canvas_document_session_service.snapshot_state()
    history = canvas.services.history_service
    stack = history.capture_stack_snapshot()
    builder = canvas.services.structure_build_service
    with monkeypatch.context() as patch:
        patch.setattr(
            history, "push", lambda _: (_ for _ in ()).throw(ValueError("failed"))
        )
        with pytest.raises(ValueError, match="failed"):
            builder.add_bond_between_points(QPointF(30, 0), QPointF(60, 0), "single", 1)
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert canvas.runtime_state.group_state.groups[group_id] is group
    history.verify_stack_snapshot(stack)
    assert builder.add_bond_between_points(QPointF(30, 0), QPointF(60, 0), "single", 1)
    assert canvas.runtime_state.group_state.groups[group_id].atom_ids == set(
        canvas.model.atoms
    )


def test_single_structure_group_refusal_is_actionable(canvas):
    a = canvas.services.canvas_atom_mutation_service.add_atom("C", 0, 0)
    b = canvas.services.canvas_atom_mutation_service.add_atom("C", 30, 0)
    add_bond_for(canvas, a, b)
    canvas.services.structure_build_service.render_model()
    canvas.services.selection.select_all()
    messages = []
    canvas.runtime_state.callback_state.error = messages.append
    before = canvas.services.canvas_document_session_service.snapshot_state()
    stack = canvas.services.history_service.capture_stack_snapshot()
    assert not group_selection_for(canvas)
    assert messages and "caption" in messages[-1] and "Group" in messages[-1]
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    canvas.services.history_service.verify_stack_snapshot(stack)
