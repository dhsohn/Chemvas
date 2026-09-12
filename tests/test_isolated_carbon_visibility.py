from __future__ import annotations

from unittest.mock import patch

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.features.document_composition import compose_document_state
from chemvas.ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from chemvas.ui.canvas_document_state import snapshot_canvas_document_state
from chemvas.ui.canvas_service_ports import mark_scene_service_for_access
from chemvas.ui.scene_decoration_access import add_mark_for_atom_for
from chemvas.ui.scene_item_access import remove_scene_item
from chemvas.ui.scene_item_state import mark_state_dict_for
from chemvas.ui.structure_mutation_access import add_bond_for

KINDS = ("plus", "minus", "radical", "circled_plus", "circled_minus")


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def canvas():
    source = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": 0, "element": "C", "x": 0.125, "y": -0.35, "color": "#2486ac"},
                {"id": 1, "element": "C", "x": 80.0, "y": 30.0},
                {"id": 2, "element": "N", "x": 160.0, "y": 80.0},
            ],
            "bonds": [],
        }
    )
    with offscreen_canvas(source, command="test-isolated-carbon") as (view, _):
        yield view


def _mark(canvas, kind="plus", atom_id=0):
    atom = canvas.model.atoms[atom_id]
    item = add_mark_for_atom_for(
        canvas, atom_id, QPointF(atom.x + 4.25, atom.y - 6.75), kind=kind
    )
    canvas.services.history_service.clear()
    return item


def _delete(canvas, marks, route="selected"):
    controller = canvas.services.scene_operations.scene_delete_controller
    if route == "selected":
        canvas.scene().clearSelection()
        for mark in marks:
            mark.setSelected(True)
        assert controller.delete_selected_items()
        return
    from chemvas.core.history import CompositeCommand

    session = controller.begin_delete_tool_session()
    try:
        commands = [
            session.delete_scene_item(mark, mark_state_dict_for(canvas, mark))
            for mark in marks
        ]
        session.commit(
            commands[0] if len(commands) == 1 else CompositeCommand(commands)
        )
    except Exception:
        if session.active:
            assert not session.rollback()
        raise


def _assert_visible(canvas, atom_id=0):
    atom = canvas.model.atoms[atom_id]
    assert atom.element == "C"
    assert atom.explicit_label
    label = atom_items_for(canvas)[atom_id]
    assert label.toPlainText() == "C"
    assert label.defaultTextColor().name() == atom.color
    assert atom_id not in atom_dots_for(canvas)
    assert not label.export_scene_bounding_rect().isEmpty()


def _roundtrip(canvas, before, after):
    history = canvas.services.history_service
    assert len(history.state.history) == 1
    for _ in range(3):
        history.undo()
        assert snapshot_canvas_document_state(canvas) == before
        history.redo()
        assert snapshot_canvas_document_state(canvas) == after


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("route", ["selected", "eraser"])
def test_last_mark_deletion_reveals_only_its_owner_in_one_edit(canvas, kind, route):
    mark = _mark(canvas, kind)
    before = snapshot_canvas_document_state(canvas)
    original = (canvas.model.atoms[0].x, canvas.model.atoms[0].y)
    _delete(canvas, [mark], route)
    _assert_visible(canvas)
    after = snapshot_canvas_document_state(canvas)
    assert set(canvas.model.atoms) == {0, 1, 2}
    assert (canvas.model.atoms[0].x, canvas.model.atoms[0].y) == original
    assert not canvas.model.atoms[1].explicit_label
    assert 1 not in atom_items_for(canvas)
    assert not canvas.model.atom_annotations
    _roundtrip(canvas, before, after)


@pytest.mark.parametrize(
    "kind,delta",
    [("plus", -1), ("circled_plus", -1), ("minus", 1), ("circled_minus", 1)],
)
def test_cancel_last_charge_reveals_carbon_in_same_edit(canvas, kind, delta):
    _mark(canvas, kind)
    before = snapshot_canvas_document_state(canvas)
    mark_scene_service_for_access(canvas).change_charge_for_atom(0, delta)
    _assert_visible(canvas)
    _roundtrip(canvas, before, snapshot_canvas_document_state(canvas))


@pytest.mark.parametrize("kind", KINDS)
def test_reassigning_last_mark_reveals_old_owner_in_same_edit(canvas, kind):
    mark = _mark(canvas, kind)
    before = snapshot_canvas_document_state(canvas)
    original_position = mark.pos()
    assert mark_scene_service_for_access(canvas).rebind_mark(mark, 2)
    _assert_visible(canvas)
    assert mark.pos() == original_position
    assert mark.data(1)["atom_id"] == 2
    _roundtrip(canvas, before, snapshot_canvas_document_state(canvas))


@pytest.mark.parametrize(
    "control", ["bonded", "remaining_mark", "noncarbon", "explicit"]
)
def test_existing_visible_or_bonded_owner_is_not_promoted(canvas, control):
    from chemvas.ui.atom_label_access import add_or_update_atom_label

    atom_id = 2 if control == "noncarbon" else 0
    if control == "bonded":
        add_bond_for(canvas, 0, 1)
    if control == "explicit":
        add_or_update_atom_label(canvas, 0, "C", show_carbon=True)
    if control == "remaining_mark":
        _mark(canvas, "radical")
    mark = _mark(canvas, atom_id=atom_id)
    before = snapshot_canvas_document_state(canvas)
    _delete(canvas, [mark])
    assert canvas.model.atoms[atom_id].explicit_label == (control == "explicit")
    _roundtrip(canvas, before, snapshot_canvas_document_state(canvas))


def test_load_and_low_level_removal_and_undo_add_do_not_repair_old_state(canvas):
    raw = snapshot_canvas_document_state(canvas)
    assert not canvas.model.atoms[0].explicit_label
    mark = add_mark_for_atom_for(canvas, 0, QPointF(4, -6), kind="plus")
    canvas.services.history_service.undo()
    assert snapshot_canvas_document_state(canvas) == raw
    canvas.services.history_service.redo()
    remove_scene_item(canvas, mark)
    assert snapshot_canvas_document_state(canvas) == raw
    assert not atom_items_for(canvas).get(0)


def test_reassign_to_current_owner_is_noop_and_preserves_redo(canvas):
    mark = _mark(canvas)
    extra = add_mark_for_atom_for(canvas, 2, QPointF(165, 74), kind="radical")
    history = canvas.services.history_service
    history.undo()
    assert extra.scene() is None
    before = snapshot_canvas_document_state(canvas)
    stacks = history.capture_stack_snapshot()
    assert not mark_scene_service_for_access(canvas).rebind_mark(mark, 0)
    assert snapshot_canvas_document_state(canvas) == before
    assert history.capture_stack_snapshot() == stacks


@pytest.mark.parametrize("route", ["selected", "eraser"])
def test_multiple_owner_deletion_reveals_only_affected_surviving_carbons(canvas, route):
    marks = [_mark(canvas, atom_id=0), _mark(canvas, "radical", atom_id=1)]
    before = snapshot_canvas_document_state(canvas)
    _delete(canvas, marks, route)
    _assert_visible(canvas, 0)
    _assert_visible(canvas, 1)
    _roundtrip(canvas, before, snapshot_canvas_document_state(canvas))


@pytest.mark.parametrize("route", ["selected", "eraser", "cancel", "rebind"])
def test_initial_promotion_reuses_the_callers_single_savepoint(canvas, route):
    from chemvas.ui.transactions.document import DocumentSavepoint

    marks = [_mark(canvas), _mark(canvas, "radical", atom_id=1)]
    real_capture = DocumentSavepoint.capture
    with patch.object(DocumentSavepoint, "capture", wraps=real_capture) as capture:
        if route in {"selected", "eraser"}:
            _delete(canvas, marks, route)
        elif route == "cancel":
            mark_scene_service_for_access(canvas).change_charge_for_atom(0, -1)
        else:
            mark_scene_service_for_access(canvas).rebind_mark(marks[0], 2)
    _assert_visible(canvas)
    assert capture.call_count == 1


def test_explicitly_selected_atom_is_deleted_not_recreated(canvas):
    _mark(canvas)
    before = snapshot_canvas_document_state(canvas)
    atom_dots_for(canvas)[0].setSelected(True)
    assert (
        canvas.services.scene_operations.scene_delete_controller.delete_selected_items()
    )
    assert 0 not in canvas.model.atoms
    assert 0 not in atom_items_for(canvas)
    assert not snapshot_canvas_document_state(canvas)["marks"]
    _roundtrip(canvas, before, snapshot_canvas_document_state(canvas))


def test_selecting_bond_and_mark_preserves_existing_orphan_cleanup(canvas):
    from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id

    bond_id = add_bond_for(canvas, 0, 1)
    canvas.services.structure.structure_build_service.render_model()
    mark = _mark(canvas)
    before = snapshot_canvas_document_state(canvas)
    mark.setSelected(True)
    bond_items_for_id(canvas, bond_id)[0].setSelected(True)
    assert (
        canvas.services.scene_operations.scene_delete_controller.delete_selected_items()
    )
    assert set(canvas.model.atoms) == {2}
    _roundtrip(canvas, before, snapshot_canvas_document_state(canvas))


def test_eraser_cancel_restores_original_implicit_owner_and_mark(canvas):
    mark = _mark(canvas)
    before = snapshot_canvas_document_state(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    session = canvas.services.scene_operations.scene_delete_controller.begin_delete_tool_session()
    session.delete_scene_item(mark, mark_state_dict_for(canvas, mark))
    _assert_visible(canvas)
    assert not session.rollback()
    assert snapshot_canvas_document_state(canvas) == before
    assert history.capture_stack_snapshot() == stacks
    assert mark.scene() is canvas.scene()


@pytest.mark.parametrize("route", ["selected", "cancel", "rebind", "eraser"])
def test_disabled_history_keeps_existing_operation_policy(canvas, route):
    mark = _mark(canvas)
    history = canvas.services.history_service
    before = snapshot_canvas_document_state(canvas)
    history.state.enabled = False
    if route in {"selected", "eraser"}:
        _delete(canvas, [mark], route)
        _assert_visible(canvas)
        assert not history.state.history
    else:
        service = mark_scene_service_for_access(canvas)
        with pytest.raises(RuntimeError):
            if route == "cancel":
                service.change_charge_for_atom(0, -1)
            else:
                service.rebind_mark(mark, 2)
        assert snapshot_canvas_document_state(canvas) == before
    assert not history.state.enabled


@pytest.mark.parametrize("route", ["selected", "cancel", "rebind", "eraser"])
@pytest.mark.parametrize("phase", ["label_after_real", "push_false", "undo", "redo"])
def test_failed_promotion_edit_preserves_state_and_history(canvas, route, phase):
    from chemvas.ui import history_commands

    mark = _mark(canvas)
    history = canvas.services.history_service
    service = mark_scene_service_for_access(canvas)

    if route == "selected":
        mark.setSelected(True)

    def action():
        if route == "cancel":
            return service.change_charge_for_atom(0, -1)
        if route == "rebind":
            return service.rebind_mark(mark, 2)
        if route == "selected":
            return canvas.services.scene_operations.scene_delete_controller.delete_selected_items()
        return _delete(canvas, [mark], route)

    if phase in {"undo", "redo"}:
        action()
        _assert_visible(canvas)
        if phase == "redo":
            history.undo()
        action = getattr(history, phase)
    before = snapshot_canvas_document_state(canvas)
    stacks = history.capture_stack_snapshot()
    original_mark_pos = mark.pos()
    original_items = set(canvas.scene().items())
    original_selected = set(canvas.scene().selectedItems())
    original_rect = canvas.scene().sceneRect()
    error = RuntimeError("injected carbon-label failure")
    real = history_commands.add_or_update_atom_label
    calls = 0

    def fail_after_real(*args, **kwargs):
        nonlocal calls
        real(*args, **kwargs)
        calls += 1
        if calls == 1:
            raise error

    with (
        patch.object(history, "push", return_value=False)
        if phase == "push_false"
        else patch.object(
            history_commands, "add_or_update_atom_label", side_effect=fail_after_real
        )
    ):
        with pytest.raises((ValueError, RuntimeError)) as caught:
            action()
    if phase != "push_false":
        assert caught.value is error
    assert snapshot_canvas_document_state(canvas) == before
    assert history.capture_stack_snapshot() == stacks
    assert mark.pos() == original_mark_pos
    assert set(canvas.scene().items()) == original_items
    assert set(canvas.scene().selectedItems()) == original_selected
    assert canvas.scene().sceneRect() == original_rect
    action()
