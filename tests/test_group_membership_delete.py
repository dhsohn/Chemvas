from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id

"""Deleting group members preserves the surviving group and exact Undo."""

import math
from unittest import mock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.core.document_io import read_document, write_document
from chemvas.core.history import CompositeCommand
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.ui.annotations.state import scene_item_state_for
from chemvas.ui.canvas.canvas_document_metadata_state import (
    document_is_dirty_for,
    mark_document_clean_for,
)
from chemvas.ui.canvas.canvas_group_state import register_group_for
from chemvas.ui.molecule.structure_mutation_access import add_bond_for
from chemvas.ui.scene.scene_decoration_access import add_mark_for_atom_for
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    yield view
    view.services.canvas_scene_reset_service.clear_scene()
    view.close()


def _grouped_ring(canvas):
    ids = [
        canvas.services.canvas_atom_mutation_service.add_atom(
            "C", 20 * math.cos(i * math.pi / 3), 20 * math.sin(i * math.pi / 3)
        )
        for i in range(6)
    ]
    for i in range(6):
        add_bond_for(canvas, ids[i], ids[(i + 1) % 6])
    note = canvas.services.scene_item_controller.create_scene_item_from_state(
        {"kind": "note", "text": "Caption", "x": -20, "y": 70}
    )
    group_id = register_group_for(
        canvas, set(ids), [require_scene_record_id(item) for item in [note]]
    )
    canvas.services.structure_build_service.render_model()
    return ids, note, group_id


def _controller(canvas):
    return canvas.services.scene_delete_controller


def _assert_undo_redo(canvas, before, after, group_id, original):
    history = canvas.services.history_service
    history.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert canvas.runtime_state.group_state.groups[group_id] is original
    assert not document_is_dirty_for(
        canvas, canvas.services.canvas_document_session_service.snapshot_state()
    )
    history.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after


@pytest.mark.parametrize("route", ["direct", "session"])
def test_delete_ring_atom_shrinks_group_not_caption(canvas, tmp_path, route):
    ids, note, group_id = _grouped_ring(canvas)
    original = canvas.runtime_state.group_state.groups[group_id]
    before = canvas.services.canvas_document_session_service.snapshot_state()
    mark_document_clean_for(canvas, before)
    if route == "direct":
        _controller(canvas).delete_atom(ids[0])
    else:
        session = _controller(canvas).begin_delete_tool_session()
        command = session.delete_atom(ids[0])
        assert command is not None
        session.commit(command)
    group = canvas.runtime_state.group_state.groups[group_id]
    assert group.atom_ids == set(ids[1:])
    assert group.item_ids == [require_scene_record_id(note)]
    assert original.atom_ids == set(ids)
    after = canvas.services.canvas_document_session_service.snapshot_state()
    _assert_undo_redo(canvas, before, after, group_id, original)
    path = tmp_path / "surviving-group.chemvas"
    write_document(path, after, CANVAS_FILE_VERSION)
    canvas.services.canvas_document_session_service.restore_state(
        read_document(path).state
    )
    assert canvas.services.canvas_document_session_service.snapshot_state() == after


def test_repeated_erase_updates_reverse_indices_and_one_undo(canvas):
    ids, note, group_id = _grouped_ring(canvas)
    original = canvas.runtime_state.group_state.groups[group_id]
    before = canvas.services.canvas_document_session_service.snapshot_state()
    mark_document_clean_for(canvas, before)
    session = _controller(canvas).begin_delete_tool_session()
    commands = []
    for atom_id in ids[:3]:
        command = session.delete_atom(atom_id)
        assert command is not None
        commands.append(command)
        assert atom_id not in session.group_ids_by_atom
        assert group_id in session.group_ids_by_item[require_scene_record_id(note)]
    assert canvas.runtime_state.group_state.groups[group_id].atom_ids == set(ids[3:])
    assert session.group_members_by_id[group_id] == (
        set(ids[3:]),
        {require_scene_record_id(note)},
    )
    session.commit(CompositeCommand(commands))
    after = canvas.services.canvas_document_session_service.snapshot_state()
    assert len(canvas.services.history_service.state.history) == 1
    _assert_undo_redo(canvas, before, after, group_id, original)


@pytest.mark.parametrize("target", ["atom", "bond"])
def test_deleting_orphan_atoms_preserves_note_only_group_then_removes_empty(
    canvas, target
):
    first = canvas.services.canvas_atom_mutation_service.add_atom("C", 0, 0)
    second = canvas.services.canvas_atom_mutation_service.add_atom("C", 20, 0)
    bond_id = add_bond_for(canvas, first, second)
    note = canvas.services.scene_item_controller.create_scene_item_from_state(
        {"kind": "note", "text": "Caption", "x": 0, "y": 40}
    )
    group_id = register_group_for(
        canvas, {first, second}, [require_scene_record_id(item) for item in [note]]
    )
    original = canvas.runtime_state.group_state.groups[group_id]
    before = canvas.services.canvas_document_session_service.snapshot_state()
    mark_document_clean_for(canvas, before)
    if target == "atom":
        # Explicit atom removal and orphan cleanup touch this group twice.
        _controller(canvas).delete_atom(first)
    else:
        _controller(canvas).delete_bond(bond_id)
    group = canvas.runtime_state.group_state.groups[group_id]
    assert not group.atom_ids
    assert group.item_ids == [require_scene_record_id(note)]
    after = canvas.services.canvas_document_session_service.snapshot_state()
    _assert_undo_redo(canvas, before, after, group_id, original)
    session = _controller(canvas).begin_delete_tool_session()
    command = session.delete_scene_item(note, scene_item_state_for(canvas, note))
    session.commit(command)
    assert group_id not in canvas.runtime_state.group_state.groups
    canvas.services.history_service.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after


@pytest.mark.parametrize("failure", ["cancel", "remove", "publish"])
def test_partial_delete_failure_restores_original_group_and_retry(canvas, failure):
    ids, _note, group_id = _grouped_ring(canvas)
    original = canvas.runtime_state.group_state.groups[group_id]
    before = canvas.services.canvas_document_session_service.snapshot_state()
    history = canvas.services.history_service
    stack = history.capture_stack_snapshot()
    session = _controller(canvas).begin_delete_tool_session()
    command = session.delete_atom(ids[0])
    assert command is not None
    if failure == "remove":
        with mock.patch.object(
            _controller(canvas),
            "_remove_atom",
            side_effect=RuntimeError("delete failed"),
        ):
            with pytest.raises(RuntimeError, match="delete failed"):
                session.delete_atom(ids[1])
    elif failure == "publish":
        with mock.patch.object(
            history, "push", side_effect=RuntimeError("publish failed")
        ):
            with pytest.raises(RuntimeError, match="publish failed"):
                session.commit(command)
    assert session.rollback() == []
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert canvas.runtime_state.group_state.groups[group_id] is original
    history.verify_stack_snapshot(stack)
    retry = _controller(canvas).begin_delete_tool_session()
    retry.commit(retry.delete_atom(ids[0]))
    assert canvas.runtime_state.group_state.groups[group_id].atom_ids == set(ids[1:])
    history.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before


def test_real_eraser_click_keeps_caption_group_and_undo(canvas, app):
    ids, note, group_id = _grouped_ring(canvas)
    before = canvas.services.canvas_document_session_service.snapshot_state()
    canvas.resize(700, 500)
    canvas.show()
    canvas.centerOn(0, 20)
    canvas.services.tool_mode_controller.set_tool("delete")
    app.processEvents()
    atom = canvas.model.atoms[ids[0]]
    point = canvas.mapFromScene(QPointF(atom.x, atom.y))
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()
    assert canvas.runtime_state.group_state.groups[group_id].atom_ids == set(ids[1:])
    assert canvas.runtime_state.group_state.groups[group_id].item_ids == [
        require_scene_record_id(note)
    ]
    QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert canvas.services.canvas_document_session_service.snapshot_state() == before


@pytest.mark.parametrize("route", ["direct", "session"])
def test_atom_removal_also_removes_grouped_bound_mark_members(canvas, route):
    ids, note, group_id = _grouped_ring(canvas)
    mark = add_mark_for_atom_for(canvas, ids[0], QPointF(30, 0), kind="plus")
    group = canvas.runtime_state.group_state.groups[group_id]
    group.item_ids.append(require_scene_record_id(mark))
    before = canvas.services.canvas_document_session_service.snapshot_state()
    mark_document_clean_for(canvas, before)
    if route == "direct":
        _controller(canvas).delete_atom(ids[0])
    else:
        session = _controller(canvas).begin_delete_tool_session()
        session.commit(session.delete_atom(ids[0]))
    assert canvas.runtime_state.group_state.groups[group_id].item_ids == [
        require_scene_record_id(note)
    ]
    assert mark.scene() is None
    after = canvas.services.canvas_document_session_service.snapshot_state()
    _assert_undo_redo(canvas, before, after, group_id, group)


def test_caption_delete_keeps_molecule_and_reverse_index_without_rescan(canvas):
    ids, note, group_id = _grouped_ring(canvas)
    original = canvas.runtime_state.group_state.groups[group_id]
    before = canvas.services.canvas_document_session_service.snapshot_state()
    mark_document_clean_for(canvas, before)
    session = _controller(canvas).begin_delete_tool_session()
    with mock.patch(
        "chemvas.ui.scene.scene_delete_controller.group_ids_for_members_for",
        side_effect=AssertionError("full group rescan"),
    ):
        note_command = session.delete_scene_item(
            note, scene_item_state_for(canvas, note)
        )
        assert id(note) not in session.group_ids_by_item
        assert all(session.group_ids_by_atom[atom] == {group_id} for atom in ids)
        atom_command = session.delete_atom(ids[0])
    assert atom_command is not None
    session.commit(CompositeCommand([note_command, atom_command]))
    group = canvas.runtime_state.group_state.groups[group_id]
    assert group.atom_ids == set(ids[1:])
    assert group.item_ids == []
    after = canvas.services.canvas_document_session_service.snapshot_state()
    _assert_undo_redo(canvas, before, after, group_id, original)


@pytest.mark.parametrize("route", ["direct", "session"])
def test_enabled_history_refusal_rolls_back_group_and_allows_retry(canvas, route):
    ids, _note, group_id = _grouped_ring(canvas)
    original = canvas.runtime_state.group_state.groups[group_id]
    before = canvas.services.canvas_document_session_service.snapshot_state()
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    session = (
        _controller(canvas).begin_delete_tool_session() if route == "session" else None
    )
    with mock.patch.object(history, "push", return_value=False):
        with pytest.raises(RuntimeError, match="history push did not commit"):
            if session is not None:
                session.commit(session.delete_atom(ids[0]))
            else:
                _controller(canvas).delete_atom(ids[0])
    if session is not None:
        assert session.rollback() == []
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert canvas.runtime_state.group_state.groups[group_id] is original
    history.verify_stack_snapshot(stacks)
    _controller(canvas).delete_atom(ids[0])
    history.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before


@pytest.mark.parametrize("route", ["direct", "session"])
def test_intentionally_disabled_history_still_allows_unrecorded_group_shrink(
    canvas, route
):
    ids, note, group_id = _grouped_ring(canvas)
    history = canvas.services.history_service
    history.set_enabled(False)
    if route == "session":
        session = _controller(canvas).begin_delete_tool_session()
        session.commit(session.delete_atom(ids[0]))
    else:
        _controller(canvas).delete_atom(ids[0])
    assert canvas.runtime_state.group_state.groups[group_id].atom_ids == set(ids[1:])
    assert canvas.runtime_state.group_state.groups[group_id].item_ids == [
        require_scene_record_id(note)
    ]
    assert not history.can_undo()
    assert not history.is_enabled()
