from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id

"""Initial Group publication rolls back through its existing document owner."""

from dataclasses import replace
from unittest import mock

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.ui.canvas.canvas_document_metadata_state import (
    document_is_dirty_for,
    mark_document_clean_for,
)
from chemvas.ui.canvas.canvas_group_state import register_group_for
from chemvas.ui.history.history_commands import (
    GroupSceneItemsCommand,
    UngroupSceneItemsCommand,
)
from chemvas.ui.molecule.structure_mutation_access import add_bond_for
from chemvas.ui.scene import scene_group_operations
from chemvas.ui.transactions.document import DocumentSavepoint
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    all_ids = []
    for offset in (0.0, 100.0, 200.0):
        ids = [
            view.services.canvas_atom_mutation_service.add_atom("C", offset, 10.0),
            view.services.canvas_atom_mutation_service.add_atom(
                "O", offset + 20.0, 20.0
            ),
        ]
        add_bond_for(view, *ids)
        all_ids.extend(ids)
        note = view.services.note_controller.create_text_note(
            QPointF(offset, 45.0), f"caption {int(offset)}"
        )
        register_group_for(
            view, set(ids), [require_scene_record_id(item) for item in [note]]
        )
    view.services.structure_build_service.render_model()
    # A real pre-existing Redo, including the detached arrow it references.
    arrow = view.services.scene_decoration_service.add_arrow(
        QPointF(0, 90), QPointF(40, 90), "arrow"
    )
    view.services.history_service.undo()
    assert arrow.scene() is None
    assert view.services.history_service.can_redo()
    view.services.selection.restore_ids(set(all_ids[:4]), set())
    view.services.selection.expand_selection_to_groups()
    mark_document_clean_for(
        view, view.services.canvas_document_session_service.snapshot_state()
    )
    yield view
    view.services.canvas_scene_reset_service.clear_scene()
    view.close()
    app.processEvents()


def _observe(canvas):
    groups = canvas.runtime_state.group_state
    history = canvas.services.history_service
    return {
        "document": canvas.services.canvas_document_session_service.snapshot_state(),
        "groups": groups.groups,
        "members": [
            (
                key,
                group,
                group.atom_ids,
                set(group.atom_ids),
                group.item_ids,
                list(group.item_ids),
            )
            for key, group in groups.groups.items()
        ],
        "next_group_id": groups.next_group_id,
        "expanding": groups.expanding,
        "items": list(canvas.scene().items()),
        "visuals": [
            (
                item,
                item.parentItem(),
                item.pos(),
                item.zValue(),
                item.isSelected(),
                item.isVisible(),
            )
            for item in canvas.scene().items()
        ],
        "rect": canvas.sceneRect(),
        "history": history.state.history,
        "redo": history.state.redo_stack,
        "stacks": history.capture_stack_snapshot(),
    }


def _assert_restored(canvas, before):
    assert (
        canvas.services.canvas_document_session_service.snapshot_state()
        == before["document"]
    )
    assert not document_is_dirty_for(
        canvas, canvas.services.canvas_document_session_service.snapshot_state()
    )
    groups = canvas.runtime_state.group_state
    assert groups.groups is before["groups"]
    assert list(groups.groups) == [member[0] for member in before["members"]]
    for key, group, atom_ids, atoms, items, members in before["members"]:
        assert groups.groups[key] is group
        assert group.atom_ids is atom_ids and group.atom_ids == atoms
        assert group.item_ids is items and group.item_ids == members
    assert groups.next_group_id == before["next_group_id"]
    assert groups.expanding is before["expanding"]
    assert list(canvas.scene().items()) == before["items"]
    for item, parent, position, z_value, selected, visible in before["visuals"]:
        assert item.scene() is canvas.scene()
        assert item.parentItem() is parent
        assert item.pos() == position
        assert item.zValue() == z_value
        assert item.isSelected() is selected
        assert item.isVisible() is visible
    assert canvas.sceneRect() == before["rect"]
    history = canvas.services.history_service
    assert history.state.history is before["history"]
    assert history.state.redo_stack is before["redo"]
    history.verify_stack_snapshot(before["stacks"])


def _operation(name):
    return (
        (scene_group_operations.group_selection_for, GroupSceneItemsCommand)
        if name == "group"
        else (scene_group_operations.ungroup_selection_for, UngroupSceneItemsCommand)
    )


@pytest.mark.parametrize("name", ["group", "ungroup"])
@pytest.mark.parametrize(
    "failure", ["false", "raise", "append_raise", "selection", "disabled"]
)
def test_initial_group_failure_restores_once_without_inverse_and_can_retry(
    canvas, name, failure
):
    action, command_type = _operation(name)
    history = canvas.services.history_service
    if failure == "disabled":
        history.state.enabled = False
    before = _observe(canvas)
    primary = RuntimeError("initial group publication failed")
    real_push = history.push
    real_refresh = canvas.services.selection.update_selection_outline

    def append_then_raise(command):
        assert real_push(command) is True
        raise primary

    def refresh_then_raise():
        real_refresh()
        raise primary

    if failure == "selection":
        injection = mock.patch.object(
            canvas.services.selection,
            "update_selection_outline",
            side_effect=refresh_then_raise,
        )
    elif failure == "disabled":
        injection = mock.patch.object(history, "push", wraps=real_push)
    else:
        injection = mock.patch.object(
            history,
            "push",
            return_value=False,
            side_effect=append_then_raise
            if failure == "append_raise"
            else primary
            if failure == "raise"
            else None,
        )
    with (
        injection,
        mock.patch.object(
            command_type, "undo", autospec=True, side_effect=command_type.undo
        ) as inverse,
        mock.patch.object(
            DocumentSavepoint, "capture", wraps=DocumentSavepoint.capture
        ) as capture,
        mock.patch.object(
            DocumentSavepoint,
            "restore",
            autospec=True,
            side_effect=DocumentSavepoint.restore,
        ) as restore,
        pytest.raises(RuntimeError) as caught,
    ):
        action(canvas)
    if failure in {"false", "disabled"}:
        assert str(caught.value) == "Group history push did not commit"
    else:
        assert caught.value is primary
    _assert_restored(canvas, before)
    assert capture.call_count == 1
    assert restore.call_count == 1
    inverse.assert_not_called()

    history.state.enabled = True
    assert action(canvas)
    after = canvas.services.canvas_document_session_service.snapshot_state()
    assert after != before["document"]
    assert document_is_dirty_for(canvas, after)
    assert len(history.state.history) == len(before["stacks"].history) + 1
    assert not history.can_redo()
    assert len(canvas.runtime_state.group_state.groups) == (2 if name == "group" else 1)
    history.undo()
    assert (
        canvas.services.canvas_document_session_service.snapshot_state()
        == before["document"]
    )
    for key, original, *_rest in before["members"]:
        assert canvas.runtime_state.group_state.groups[key] is original
    assert not document_is_dirty_for(
        canvas, canvas.services.canvas_document_session_service.snapshot_state()
    )
    history.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after


@pytest.mark.parametrize("name", ["group", "ungroup"])
@pytest.mark.parametrize("failure", ["returned", "raised"])
def test_initial_group_failure_keeps_primary_and_document_recovery_note(
    canvas, name, failure
):
    action, _command_type = _operation(name)
    before = _observe(canvas)
    primary = RuntimeError("history unavailable")
    secondary = RuntimeError("restore notification unavailable")
    real_restore = DocumentSavepoint.restore

    def restore_then_report(snapshot):
        outcome = real_restore(snapshot)
        assert outcome.authoritative and outcome.errors == ()
        if failure == "raised":
            raise secondary
        return replace(outcome, errors=(secondary,))

    with (
        mock.patch.object(canvas.services.history_service, "push", side_effect=primary),
        mock.patch.object(
            DocumentSavepoint, "restore", autospec=True, side_effect=restore_then_report
        ) as restore,
        pytest.raises(RuntimeError) as caught,
    ):
        action(canvas)
    assert caught.value is primary
    assert restore.call_count == 1
    _assert_restored(canvas, before)
    assert caught.value.__notes__ == [
        (
            "Transaction recovery also encountered an error during restoring the "
            "document savepoint: RuntimeError: restore notification unavailable"
        )
    ]


@pytest.mark.parametrize("name", ["group", "ungroup"])
def test_initial_group_noop_keeps_document_and_existing_redo(canvas, name):
    if name == "group":
        # The already-grouped selection adds no members.
        canvas.services.selection.restore_ids({0, 1}, set())
        canvas.services.selection.expand_selection_to_groups()
    else:
        canvas.runtime_state.group_state.groups.clear()
    mark_document_clean_for(
        canvas, canvas.services.canvas_document_session_service.snapshot_state()
    )
    before = _observe(canvas)
    action, _command_type = _operation(name)
    with mock.patch.object(canvas.services.history_service, "push") as push:
        assert action(canvas) is False
    push.assert_not_called()
    _assert_restored(canvas, before)
