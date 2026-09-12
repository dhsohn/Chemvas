from unittest import mock

import pytest
from PyQt6.QtCore import QPointF

from chemvas.ui.scene_decoration_access import add_mark_for, add_mark_for_atom_for
from chemvas.ui.scene_item_state import scene_item_state_for
from chemvas.ui.select_all_access import select_all_scene_items_for
from tests.test_atom_charge_interaction import app as app
from tests.test_atom_charge_interaction import canvas as canvas
from tests.test_atom_charge_interaction import load, snapshot


def prepare(canvas):
    load(canvas, "C")
    dependent = add_mark_for_atom_for(canvas, 0, QPointF(-20, 0), kind="plus")
    independent = add_mark_for_atom_for(canvas, 2, QPointF(20, 0), kind="plus")
    free = add_mark_for(canvas, QPointF(90.1, 60.3), kind="minus")
    select_all_scene_items_for(canvas)
    canvas.services.scene_operations.scene_transform_controller.translate_selected_items(
        10, 0
    )
    canvas.services.history_service.undo()
    tool = canvas.services.tool_controller.tools["select"]
    assert tool._begin_selection_drag({0}, [dependent, independent, free], QPointF())
    assert tool._selection_items == [independent, free]
    return tool, dependent, independent, free


def frame(tool):
    tool._apply_drag_delta(QPointF(10, 7))
    tool._apply_drag_delta(QPointF(-2, 3))


def test_mixed_move_undo_redo_no_double_moved_mark(canvas):
    tool, dependent, independent, free = prepare(canvas)
    before = snapshot(canvas)
    before_mark = scene_item_state_for(canvas, independent)
    frame(tool)
    states = dict(tool._require_drag_token().before_item_states)
    assert set(states) == {dependent, independent, free}
    assert {
        key: value for key, value in states[independent].items() if key != "item_pos"
    } == before_mark
    tool._commit_selection_drag()
    after = snapshot(canvas)
    history = canvas.services.history_service
    assert not history.can_redo()
    history.undo()
    assert snapshot(canvas) == before
    history.redo()
    assert snapshot(canvas) == after


@pytest.mark.parametrize(
    "phase", ["cancel", "no-op", "move-fail", "push-fail", "return"]
)
def test_cancel_and_failure_keep_baseline_redo(canvas, phase):
    tool, dependent, independent, free = prepare(canvas)
    history = canvas.services.history_service
    before = snapshot(canvas)
    stacks = history.capture_stack_snapshot()
    if phase == "no-op":
        tool._apply_drag_delta(QPointF())
        assert tool._require_drag_token().before_item_states is None
        assert tool._require_drag_token().savepoint is None
        tool._commit_selection_drag()
    elif phase == "move-fail":
        import chemvas.ui.selection_drag_tool as subject

        real = subject.move_item_for
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("render failed")
            return real(*args, **kwargs)

        with mock.patch.object(subject, "move_item_for", side_effect=fail_second):
            with pytest.raises(RuntimeError, match="render failed"):
                frame(tool)
    else:
        frame(tool)
        if phase == "return":
            tool._apply_drag_delta(QPointF(-8, -10))
            assert not tool._drag_has_net_movement()
            tool._commit_selection_drag()
        elif phase == "cancel":
            tool._cancel_selection_drag()
        else:
            with mock.patch.object(history, "push", return_value=False):
                with pytest.raises(RuntimeError, match="did not commit"):
                    tool._commit_selection_drag()
    assert snapshot(canvas) == before
    history.verify_stack_snapshot(stacks)
    assert tool._drag_transaction is None
    assert not tool._drag_selection


@pytest.mark.parametrize("phase", ["undo", "redo"])
def test_history_failure_mixed_command_keeps_both_stacks_retryable(canvas, phase):
    tool, dependent, independent, free = prepare(canvas)
    frame(tool)
    tool._commit_selection_drag()
    history = canvas.services.history_service
    if phase == "redo":
        history.undo()
    before = snapshot(canvas)
    stacks = history.capture_stack_snapshot()
    with mock.patch(
        "chemvas.ui.history_commands._apply_scene_item_state",
        side_effect=RuntimeError("render failed"),
    ):
        with pytest.raises(RuntimeError, match="render failed"):
            getattr(history, phase)()
    assert snapshot(canvas) == before
    history.verify_stack_snapshot(stacks)
    getattr(history, phase)()
