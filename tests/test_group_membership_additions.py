"""New structure geometry keeps the editable molecule in its existing group."""

import pytest
from PyQt6.QtCore import QPointF

from chemvas.core.document_io import read_document
from chemvas.ui.canvas_callback_state import callback_state_for
from chemvas.ui.canvas_group_state import group_state_for, register_group_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.history_recording_access import record_additions_for
from chemvas.ui.scene_group_operations import group_selection_for
from chemvas.ui.scene_item_access import create_scene_item_from_state
from chemvas.ui.select_all_access import select_all_scene_items_for
from chemvas.ui.structure_mutation_access import add_atom_for, add_bond_for
from tests.test_native_geometry_backlog import app as app
from tests.test_native_geometry_backlog import canvas as canvas


def _group(canvas):
    a = add_atom_for(canvas, "C", 0, 0)
    b = add_atom_for(canvas, "C", 30, 0)
    add_bond_for(canvas, a, b)
    canvas.services.structure.structure_build_service.render_model()
    note = create_scene_item_from_state(
        canvas, {"kind": "note", "text": "Compound", "x": 0, "y": 60}
    )
    group_id = register_group_for(canvas, {a, b}, [note])
    return a, b, group_id


@pytest.mark.parametrize("kind", ["sprout", "fuse", "join-ungrouped"])
def test_new_geometry_extends_group_and_roundtrips(canvas, tmp_path, kind):
    a, b, group_id = _group(canvas)
    if kind == "join-ungrouped":
        c = add_atom_for(canvas, "C", 60, 0)
        d = add_atom_for(canvas, "O", 90, 0)
        add_bond_for(canvas, c, d)
    group = group_state_for(canvas).groups[group_id]
    before = snapshot_canvas_state_for(canvas)
    before_atom = canvas.model.next_atom_id
    before_bond = len(canvas.model.bonds)
    if kind == "sprout":
        c = add_atom_for(canvas, "C", 60, 0)
        add_bond_for(canvas, b, c)
    elif kind == "fuse":
        c = add_atom_for(canvas, "C", 30, 30)
        d = add_atom_for(canvas, "C", 0, 30)
        for x, y in ((b, c), (c, d), (d, a)):
            add_bond_for(canvas, x, y)
    else:
        add_bond_for(canvas, b, c)
    record_additions_for(canvas, before_atom, before_bond, None)
    canvas.services.structure.structure_build_service.render_model()
    assert group_state_for(canvas).groups[group_id].atom_ids == set(canvas.model.atoms)
    assert group.atom_ids == {a, b}, "The Undo snapshot must not be mutated in place"
    after = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    assert group_state_for(canvas).groups[group_id] is group
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after
    path = tmp_path / "extended-group.chemvas"
    documents = canvas.services.document.canvas_document_session_service
    assert documents.save_to_file(str(path)) == []
    documents.apply_state(read_document(path).state)
    assert next(iter(group_state_for(canvas).groups.values())).atom_ids == set(
        canvas.model.atoms
    )


def test_sprout_builder_failure_restores_group_and_document(canvas, monkeypatch):
    _a, _b, group_id = _group(canvas)
    group = group_state_for(canvas).groups[group_id]
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    stack = history.capture_stack_snapshot()
    builder = canvas.services.structure.structure_build_service
    with monkeypatch.context() as patch:
        patch.setattr(
            history, "push", lambda _: (_ for _ in ()).throw(ValueError("failed"))
        )
        with pytest.raises(ValueError, match="failed"):
            builder.add_bond_between_points(QPointF(30, 0), QPointF(60, 0), "single", 1)
    assert snapshot_canvas_state_for(canvas) == before
    assert group_state_for(canvas).groups[group_id] is group
    history.verify_stack_snapshot(stack)
    assert builder.add_bond_between_points(QPointF(30, 0), QPointF(60, 0), "single", 1)
    assert group_state_for(canvas).groups[group_id].atom_ids == set(canvas.model.atoms)


def test_single_structure_group_refusal_is_actionable(canvas):
    a = add_atom_for(canvas, "C", 0, 0)
    b = add_atom_for(canvas, "C", 30, 0)
    add_bond_for(canvas, a, b)
    canvas.services.structure.structure_build_service.render_model()
    select_all_scene_items_for(canvas)
    messages = []
    callback_state_for(canvas).error = messages.append
    before = snapshot_canvas_state_for(canvas)
    stack = canvas.services.history_service.capture_stack_snapshot()
    assert not group_selection_for(canvas)
    assert messages and "caption" in messages[-1] and "Group" in messages[-1]
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.verify_stack_snapshot(stack)
