import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.ui.annotations.state import scene_item_state_for
from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas.canvas_document_metadata_state import (
    document_is_dirty_for,
    mark_document_clean_for,
)
from chemvas.ui.canvas.canvas_scene_items_state import mark_items_for, note_items_for
from chemvas.ui.history.history_commands import DeleteSceneItemsCommand
from chemvas.ui.molecule.structure_mutation_access import add_bond_for
from chemvas.ui.scene.scene_decoration_access import add_mark_for, add_mark_for_atom_for
from chemvas.ui.scene.scene_group_operations import group_selection_for
from chemvas.ui.tools.delete_tool_logic import erase_delete_tool_item
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def canvas():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    view = build_canvas_view()
    yield view
    sip.delete(view)


@pytest.mark.parametrize("selected", [(1,), (0, 2), (2, 0)])
@pytest.mark.parametrize("grouping", ["none", "notes", "mixed"])
def test_delete_undo_restores_note_order_and_clean_document(canvas, selected, grouping):
    notes = [
        canvas.services.note_controller.create_text_note(QPointF(20, 20), text)
        for text in ("first", "second", "third")
    ]
    selection = canvas.services.selection
    if grouping != "none":
        if grouping == "mixed":
            atom_id = canvas.services.canvas_atom_mutation_service.add_atom("C", 0, 0)
            visible_atom_item_for(canvas, atom_id).setSelected(True)
        for note in notes:
            selection.select_note(note, additive=True)
        assert group_selection_for(canvas)
        selection.clear_note_selection()
        canvas.scene().clearSelection()
    for index in selected:
        selection.select_note(notes[index], additive=True)

    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    mark_document_clean_for(canvas, before)
    stacking = [item for item in canvas.scene().items() if item in notes]
    deletion = canvas.services.scene_delete_controller
    assert deletion.delete_selected_items()
    for cycle in range(3):
        if cycle:
            canvas.services.history_service.redo()
        canvas.services.history_service.undo()
        assert note_items_for(canvas) == notes
        assert [item for item in canvas.scene().items() if item in notes] == stacking
        assert session.snapshot_state() == before
        assert not document_is_dirty_for(canvas, session.snapshot_state())


def test_interleaved_marks_and_bond_restore_after_failed_undo(canvas, monkeypatch):
    from chemvas.ui.history import history_operations as history_commands

    atoms = canvas.services.canvas_atom_mutation_service
    nitrogen = atoms.add_atom("N", 0, 0)
    oxygen = atoms.add_atom("O", 40, 0)
    add_bond_for(canvas, nitrogen, oxygen, 1)
    add_mark_for_atom_for(canvas, nitrogen, QPointF(10, -10), kind="plus")
    free = add_mark_for(canvas, QPointF(20, 20), kind="radical")
    add_mark_for_atom_for(canvas, nitrogen, QPointF(-10, -10), kind="radical")
    add_mark_for_atom_for(canvas, oxygen, QPointF(50, -10), kind="minus")
    add_mark_for(canvas, QPointF(60, 20), kind="plus")
    marks = list(mark_items_for(canvas))
    for mark in marks:
        mark.setZValue(5)
    stacking = [item for item in canvas.scene().items() if item in marks]
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    mark_document_clean_for(canvas, before)
    visible_atom_item_for(canvas, nitrogen).setSelected(True)
    free.setSelected(True)
    assert canvas.services.scene_delete_controller.delete_selected_items()
    deleted = session.snapshot_state()
    deleted_marks = list(mark_items_for(canvas))
    history = canvas.services.history_service
    commands = list(history.state.history)
    restore_item = history_commands.restore_scene_item

    def fail_after_mark_restore(view, item):
        restore_item(view, item)
        raise RuntimeError("mark restoration failed")

    with monkeypatch.context() as patch:
        patch.setattr(history_commands, "restore_scene_item", fail_after_mark_restore)
        with pytest.raises(RuntimeError, match="mark restoration failed"):
            history.undo()
    assert session.snapshot_state() == deleted
    assert mark_items_for(canvas) == deleted_marks
    assert history.state.history == commands
    for cycle in range(3):
        if cycle:
            history.redo()
        history.undo()
        assert mark_items_for(canvas) == marks
        assert [item for item in canvas.scene().items() if item in marks] == stacking
        assert session.snapshot_state() == before
        assert not document_is_dirty_for(canvas, session.snapshot_state())


def test_order_restore_failure_rolls_back_attachment_and_allows_retry(
    canvas, monkeypatch
):
    operations = canvas.services.history_service.operations
    notes = [
        canvas.services.note_controller.create_text_note(QPointF(20, 20), text)
        for text in ("first", "second", "third")
    ]
    command = DeleteSceneItemsCommand.capture(
        operations, [scene_item_state_for(canvas, notes[1])], [notes[1]]
    )
    command.redo(operations)
    session = canvas.services.canvas_document_session_service
    deleted_state = session.snapshot_state()
    deleted_stacking = list(canvas.scene().items())
    order = command._order
    assert order is not None
    restore = order.restore

    def fail_after_reordering(view):
        restore(view)
        raise RuntimeError("order restore failure")

    with monkeypatch.context() as patch:
        patch.setattr(order, "restore", fail_after_reordering)
        with pytest.raises(RuntimeError, match="order restore failure"):
            command.undo(operations)
    assert notes[1].scene() is None
    assert note_items_for(canvas) == [notes[0], notes[2]]
    assert list(canvas.scene().items()) == deleted_stacking
    assert session.snapshot_state() == deleted_state
    command.undo(operations)
    assert note_items_for(canvas) == notes


@pytest.mark.parametrize("delete_path", ["selection", "single", "eraser"])
@pytest.mark.parametrize("bound_first", [True, False])
@pytest.mark.parametrize("grouped", [True, False])
def test_atom_mark_delete_undo_restores_live_marks_order_and_clean_state(
    canvas, delete_path, bound_first, grouped
):
    atom_id = canvas.services.canvas_atom_mutation_service.add_atom("N", 0, 0)
    if not bound_first:
        free = add_mark_for(canvas, QPointF(20, 20), kind="radical")
    bound = add_mark_for_atom_for(canvas, atom_id, QPointF(10, -10), kind="plus")
    if bound_first:
        free = add_mark_for(canvas, QPointF(20, 20), kind="radical")
    bound.setZValue(free.zValue())
    if grouped:
        visible_atom_item_for(canvas, atom_id).setSelected(True)
        free.setSelected(True)
        assert group_selection_for(canvas)
        canvas.scene().clearSelection()
    marks = list(mark_items_for(canvas))
    stacking = [item for item in canvas.scene().items() if item in marks]
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    mark_document_clean_for(canvas, before)
    annotations = dict(canvas.model.atom_annotations)
    deletion = canvas.services.scene_delete_controller
    if delete_path == "selection":
        visible_atom_item_for(canvas, atom_id).setSelected(True)
        # Also selected explicitly: it must be deleted only once.
        bound.setSelected(True)
        free.setSelected(True)
        assert deletion.delete_selected_items()
    elif delete_path == "single":
        deletion.delete_atom(atom_id)
    else:
        changed, command = erase_delete_tool_item(
            canvas, visible_atom_item_for(canvas, atom_id), scene_ops=deletion
        )
        assert changed
        canvas.services.history_service.push(command)
    for cycle in range(3):
        if cycle:
            canvas.services.history_service.redo()
        assert atom_id not in canvas.model.atoms
        assert bound.scene() is None
        canvas.services.history_service.undo()
        assert mark_items_for(canvas) == marks
        assert [item for item in canvas.scene().items() if item in marks] == stacking
        assert canvas.model.atom_annotations == annotations
        assert session.snapshot_state() == before
        assert not document_is_dirty_for(canvas, session.snapshot_state())


@pytest.mark.parametrize("z", [0.0, 3.0])
def test_recreated_annotation_keeps_stacking_among_molecular_graphics(canvas, z):
    import gc
    import weakref

    from chemvas.ui.annotations.projections import find_projection
    from tests.test_annotation_document_ownership import (
        _assert_history_has_no_live_graphics,
    )

    mark = add_mark_for(canvas, QPointF(20, 20), kind="plus")
    mark.setZValue(z)
    key = mark.data(3)
    atoms = canvas.services.canvas_atom_mutation_service
    a = atoms.add_atom("N", 0, 0)
    b = atoms.add_atom("O", 40, 0)
    canvas.bond_renderer.add_bond_graphics(add_bond_for(canvas, a, b, 2))
    history = canvas.services.history_service
    history.clear()

    def stacking():
        return [
            "mark" if item.data(3) == key else id(item)
            for item in canvas.scene().items()
            if item.parentItem() is None and item.zValue() == z
        ]

    before = stacking()
    assert len(before) > 1
    command = DeleteSceneItemsCommand.capture(
        history.operations, [scene_item_state_for(canvas, mark)], [mark]
    )
    command.redo(history.operations)
    history.push(command)
    _assert_history_has_no_live_graphics(command)
    ref = weakref.ref(mark)
    del mark
    gc.collect()
    assert ref() is None
    history.undo()
    assert find_projection(canvas, key).scene() is canvas.scene()
    assert stacking() == before
    history.redo()
    history.undo()
    assert stacking() == before
