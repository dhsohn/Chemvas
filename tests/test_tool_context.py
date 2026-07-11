from types import SimpleNamespace
from unittest import mock

import pytest
from PyQt6.QtCore import QPointF
from ui.tool_context import ToolContext


def _hit_testing_port(**overrides):
    defaults = dict(
        scene_pos_from_event=mock.Mock(),
        item_at_scene_pos=mock.Mock(),
        item_at_event=mock.Mock(),
        find_atom_near=mock.Mock(),
        find_bond_near=mock.Mock(),
        bond_id_from_event=mock.Mock(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _selection_port(**overrides):
    defaults = dict(
        toggle_item_selection=mock.Mock(),
        preferred_structure_hit_at_scene_pos=mock.Mock(),
        preferred_structure_item_at_scene_pos=mock.Mock(),
        selection_hit_test=mock.Mock(),
        select_structure_for_item=mock.Mock(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _note_port(**overrides):
    defaults = dict(
        create_text_note=mock.Mock(),
        begin_note_edit=mock.Mock(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _handle_port(**overrides):
    defaults = dict(update_handle_drag=mock.Mock())
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _selection_rotation_port(**overrides):
    defaults = dict(
        begin_selection_3d_rotation=mock.Mock(),
        update_selection_3d_rotation=mock.Mock(),
        end_selection_3d_rotation=mock.Mock(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _scene_transform_port(**overrides):
    defaults = dict(
        apply_bond_style=mock.Mock(),
        cycle_bond_style=mock.Mock(),
        flip_bond_direction=mock.Mock(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _style_port(**overrides):
    defaults = dict(suspend_selection_outline=mock.Mock())
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _history_port(**overrides):
    defaults = dict(push=mock.Mock())
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _color_port(**overrides):
    defaults = dict(
        apply_color_to_item=mock.Mock(),
        apply_color_to_items=mock.Mock(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_tool_context_delegates_hit_testing_ports_to_injected_service() -> None:
    event = object()
    pos = QPointF(3.0, 4.0)
    item = object()
    hit_testing = _hit_testing_port(
        scene_pos_from_event=mock.Mock(return_value=pos),
        item_at_scene_pos=mock.Mock(return_value=item),
        item_at_event=mock.Mock(return_value=item),
        find_atom_near=mock.Mock(return_value=7),
        find_bond_near=mock.Mock(return_value=5),
        bond_id_from_event=mock.Mock(return_value=2),
    )
    context = ToolContext(
        object(),
        hit_testing_service=hit_testing,
        selection_controller=_selection_port(),
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_transform_controller=_scene_transform_port(),
    )

    assert context.scene_pos_from_event(event) == pos
    assert context.item_at_scene_pos(pos) is item
    assert context.item_at_event(event) is item
    assert context.find_atom_near(1.0, 2.0, 6.0) == 7
    assert context.find_bond_near(pos, 8.0) == 5
    assert context.bond_id_from_event(event) == 2
    hit_testing.scene_pos_from_event.assert_called_once_with(event)
    hit_testing.item_at_scene_pos.assert_called_once_with(pos)
    hit_testing.item_at_event.assert_called_once_with(event)
    hit_testing.find_atom_near.assert_called_once_with(1.0, 2.0, 6.0)
    hit_testing.find_bond_near.assert_called_once_with(pos, 8.0)
    hit_testing.bond_id_from_event.assert_called_once_with(event)


def test_tool_context_delegates_selection_ports_to_injected_controller() -> None:
    pos = QPointF(3.0, 4.0)
    item = object()
    hit = object()
    snapshot = object()
    selection = _selection_port(
        toggle_item_selection=mock.Mock(return_value=True),
        preferred_structure_hit_at_scene_pos=mock.Mock(return_value=hit),
        preferred_structure_item_at_scene_pos=mock.Mock(return_value=item),
        selection_hit_test=mock.Mock(return_value=True),
        select_structure_for_item=mock.Mock(return_value=True),
    )
    context = ToolContext(
        object(),
        hit_testing_service=_hit_testing_port(),
        selection_controller=selection,
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_transform_controller=_scene_transform_port(),
    )

    assert context.toggle_item_selection(item)
    assert context.preferred_structure_hit_at_scene_pos(pos) is hit
    assert context.preferred_structure_item_at_scene_pos(pos) is item
    assert context.selection_hit_test(pos, snapshot=snapshot)
    assert context.select_structure_for_item(item)
    selection.toggle_item_selection.assert_called_once_with(item)
    selection.preferred_structure_hit_at_scene_pos.assert_called_once_with(pos)
    selection.preferred_structure_item_at_scene_pos.assert_called_once_with(pos)
    selection.selection_hit_test.assert_called_once_with(pos, snapshot=snapshot)
    selection.select_structure_for_item.assert_called_once_with(item)


def test_tool_context_delegates_bond_set_lookup_to_injected_port() -> None:
    bond_sets_for_atoms = mock.Mock(return_value=({1}, {2}))
    context = ToolContext(
        object(),
        hit_testing_service=_hit_testing_port(),
        selection_controller=_selection_port(),
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_transform_controller=_scene_transform_port(),
        bond_sets_for_atoms=bond_sets_for_atoms,
    )

    assert context.bond_sets_for_atoms({3, 4}) == ({1}, {2})
    bond_sets_for_atoms.assert_called_once_with({3, 4})


def test_tool_context_delegates_selection_outline_suspend_to_injected_style_controller() -> (
    None
):
    style_controller = _style_port(suspend_selection_outline=mock.Mock())
    context = ToolContext(
        object(),
        hit_testing_service=_hit_testing_port(),
        selection_controller=_selection_port(),
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_transform_controller=_scene_transform_port(),
        style_controller=style_controller,
    )

    context.suspend_selection_outline(True)

    style_controller.suspend_selection_outline.assert_called_once_with(True)


def test_tool_context_delegates_tool_specific_canvas_ports() -> None:
    item = object()
    color = object()
    selected_item = object()
    color_service = _color_port()
    selected_scene_items = mock.Mock(return_value=[selected_item])
    select_single_structure_item = mock.Mock(return_value=True)
    atom_symbol_provider = mock.Mock(return_value="Cl")
    context = ToolContext(
        object(),
        hit_testing_service=_hit_testing_port(),
        selection_controller=_selection_port(),
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_transform_controller=_scene_transform_port(),
        color_mutation_service=color_service,
        selected_scene_items=selected_scene_items,
        select_single_structure_item=select_single_structure_item,
        atom_symbol_provider=atom_symbol_provider,
    )

    context.apply_color_to_item(item, color)
    context.apply_color_to_items([item], color)

    color_service.apply_color_to_item.assert_called_once_with(item, color)
    color_service.apply_color_to_items.assert_called_once_with([item], color)
    assert context.selected_scene_items(excluded_kinds={"selection_outline"}) == [
        selected_item
    ]
    selected_scene_items.assert_called_once_with(excluded_kinds={"selection_outline"})
    assert context.select_single_structure_item(selected_item)
    select_single_structure_item.assert_called_once_with(selected_item)
    assert context.current_atom_symbol() == "Cl"
    atom_symbol_provider.assert_called_once_with()


def test_tool_context_delegates_drag_mode_to_injected_view_port() -> None:
    set_drag_mode = mock.Mock()
    context = ToolContext(
        object(),
        hit_testing_service=_hit_testing_port(),
        selection_controller=_selection_port(),
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_transform_controller=_scene_transform_port(),
        set_drag_mode=set_drag_mode,
        rubber_band_drag_mode="rubber",
    )

    context.set_rubber_band_drag_mode()

    set_drag_mode.assert_called_once_with("rubber")


def test_tool_context_does_not_fallback_to_canvas_facade_when_ports_are_injected() -> (
    None
):
    pos = QPointF(1.0, 2.0)
    item = object()
    hit = object()
    canvas = SimpleNamespace(
        scene_pos_from_event=mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        ),
        item_at_scene_pos=mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        ),
        item_at_event=mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        ),
        find_atom_near=mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        ),
        find_bond_near=mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        ),
        bond_id_from_event=mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        ),
        toggle_item_selection=mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        ),
        preferred_structure_hit_at_scene_pos=mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        ),
        preferred_structure_item_at_scene_pos=mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        ),
        selection_hit_test=mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        ),
        select_structure_for_item=mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        ),
        select_single_structure_item=mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        ),
        apply_color_to_item=mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        ),
        apply_color_to_items=mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        ),
        get_atom_symbol=mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        ),
    )
    hit_testing = _hit_testing_port(
        scene_pos_from_event=mock.Mock(return_value=pos),
        item_at_scene_pos=mock.Mock(return_value=item),
        item_at_event=mock.Mock(return_value=item),
        find_atom_near=mock.Mock(return_value=None),
        find_bond_near=mock.Mock(return_value=None),
        bond_id_from_event=mock.Mock(return_value=3),
    )
    selection = _selection_port(
        toggle_item_selection=mock.Mock(return_value=True),
        preferred_structure_hit_at_scene_pos=mock.Mock(return_value=hit),
        preferred_structure_item_at_scene_pos=mock.Mock(return_value=item),
        selection_hit_test=mock.Mock(return_value=False),
        select_structure_for_item=mock.Mock(return_value=True),
    )
    context = ToolContext(
        canvas,
        hit_testing_service=hit_testing,
        selection_controller=selection,
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_transform_controller=_scene_transform_port(),
        color_mutation_service=_color_port(
            apply_color_to_item=mock.Mock(),
            apply_color_to_items=mock.Mock(),
        ),
        selected_scene_items=mock.Mock(return_value=[item]),
        select_single_structure_item=mock.Mock(return_value=True),
        atom_symbol_provider=mock.Mock(return_value="N"),
    )

    assert context.scene_pos_from_event(object()) == pos
    assert context.item_at_scene_pos(pos) is item
    assert context.item_at_event(object()) is item
    assert context.find_atom_near(1.0, 2.0, 3.0) is None
    assert context.find_bond_near(pos, 4.0) is None
    assert context.bond_id_from_event(object()) == 3
    assert context.toggle_item_selection(item)
    assert context.preferred_structure_hit_at_scene_pos(pos) is hit
    assert context.preferred_structure_item_at_scene_pos(pos) is item
    assert not context.selection_hit_test(QPointF(1.0, 2.0))
    assert context.select_structure_for_item(item)
    context.apply_color_to_item(item, object())
    context.apply_color_to_items([item], object())
    assert context.selected_scene_items(excluded_kinds=set()) == [item]
    assert context.select_single_structure_item(item)
    assert context.current_atom_symbol() == "N"
    canvas.scene_pos_from_event.assert_not_called()
    canvas.item_at_scene_pos.assert_not_called()
    canvas.item_at_event.assert_not_called()
    canvas.find_atom_near.assert_not_called()
    canvas.find_bond_near.assert_not_called()
    canvas.bond_id_from_event.assert_not_called()
    canvas.toggle_item_selection.assert_not_called()
    canvas.preferred_structure_hit_at_scene_pos.assert_not_called()
    canvas.preferred_structure_item_at_scene_pos.assert_not_called()
    canvas.selection_hit_test.assert_not_called()
    canvas.select_structure_for_item.assert_not_called()
    canvas.select_single_structure_item.assert_not_called()
    canvas.apply_color_to_item.assert_not_called()
    canvas.apply_color_to_items.assert_not_called()
    canvas.get_atom_symbol.assert_not_called()


def test_tool_context_does_not_use_canvas_fallbacks_when_ports_are_missing() -> None:
    pos = QPointF(3.0, 4.0)
    item = object()
    hit = object()
    canvas = SimpleNamespace(
        scene_pos_from_event=mock.Mock(return_value=pos),
        item_at_scene_pos=mock.Mock(return_value=item),
        item_at_event=mock.Mock(return_value=item),
        find_atom_near=mock.Mock(return_value=7),
        find_bond_near=mock.Mock(return_value=5),
        bond_id_from_event=mock.Mock(return_value=2),
        toggle_item_selection=mock.Mock(return_value=True),
        preferred_structure_hit_at_scene_pos=mock.Mock(return_value=hit),
        preferred_structure_item_at_scene_pos=mock.Mock(return_value=item),
        selection_hit_test=mock.Mock(return_value=True),
        select_structure_for_item=mock.Mock(return_value=True),
    )
    context = ToolContext(
        canvas,
        hit_testing_service=SimpleNamespace(),
        selection_controller=SimpleNamespace(),
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_transform_controller=_scene_transform_port(),
    )

    with pytest.raises(AttributeError, match="scene_pos_from_event"):
        context.scene_pos_from_event(object())
    assert context.item_at_scene_pos(pos) is None
    assert context.item_at_event(object()) is None
    assert context.find_atom_near(1.0, 2.0, 6.0) is None
    assert context.find_bond_near(pos, 8.0) is None
    assert context.bond_id_from_event(object()) is None
    assert not context.toggle_item_selection(item)
    assert context.preferred_structure_hit_at_scene_pos(pos) is None
    assert context.preferred_structure_item_at_scene_pos(pos) is None
    assert not context.selection_hit_test(pos)
    assert not context.select_structure_for_item(item)
    assert not context.select_single_structure_item(item)
    assert context.selected_scene_items(excluded_kinds=set()) == []
    assert context.current_atom_symbol() == ""
    canvas.scene_pos_from_event.assert_not_called()
    canvas.item_at_scene_pos.assert_not_called()
    canvas.item_at_event.assert_not_called()
    canvas.find_atom_near.assert_not_called()
    canvas.find_bond_near.assert_not_called()
    canvas.bond_id_from_event.assert_not_called()
    canvas.toggle_item_selection.assert_not_called()
    canvas.preferred_structure_hit_at_scene_pos.assert_not_called()
    canvas.preferred_structure_item_at_scene_pos.assert_not_called()
    canvas.selection_hit_test.assert_not_called()
    canvas.select_structure_for_item.assert_not_called()


def test_tool_context_composes_item_at_event_from_hit_testing_ports_before_canvas_fallback() -> (
    None
):
    event = object()
    pos = QPointF(5.0, 6.0)
    item = object()
    canvas = SimpleNamespace(
        item_at_event=mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        ),
    )
    hit_testing = SimpleNamespace(
        scene_pos_from_event=mock.Mock(return_value=pos),
        item_at_scene_pos=mock.Mock(return_value=item),
    )
    context = ToolContext(
        canvas,
        hit_testing_service=hit_testing,
        selection_controller=_selection_port(),
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_transform_controller=_scene_transform_port(),
    )

    assert context.item_at_event(event) is item
    hit_testing.scene_pos_from_event.assert_called_once_with(event)
    hit_testing.item_at_scene_pos.assert_called_once_with(pos)
    canvas.item_at_event.assert_not_called()


def test_tool_context_delegates_note_ports_to_injected_controller() -> None:
    pos = QPointF(3.0, 4.0)
    item = object()
    note = _note_port(create_text_note=mock.Mock(return_value=item))
    context = ToolContext(
        object(),
        hit_testing_service=_hit_testing_port(),
        selection_controller=_selection_port(),
        note_controller=note,
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_transform_controller=_scene_transform_port(),
    )

    assert context.create_text_note(pos, "Scheme") is item
    context.begin_note_edit(item)
    note.create_text_note.assert_called_once_with(pos, "Scheme")
    note.begin_note_edit.assert_called_once_with(item)


def test_tool_context_delegates_history_push_to_injected_service() -> None:
    command = object()
    history = _history_port()
    context = ToolContext(
        object(),
        hit_testing_service=_hit_testing_port(),
        selection_controller=_selection_port(),
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_transform_controller=_scene_transform_port(),
        history_service=history,
    )

    context.push_history(command)

    history.push.assert_called_once_with(command)


def test_tool_context_rolls_back_command_when_history_push_is_blocked() -> None:
    canvas = object()
    primary = RuntimeError("re-entrant history mutation is not allowed")
    command = SimpleNamespace(undo=mock.Mock())
    history = _history_port(
        state=SimpleNamespace(history=[], redo_stack=[]),
        push=mock.Mock(side_effect=primary),
    )
    context = ToolContext(
        canvas,
        hit_testing_service=_hit_testing_port(),
        selection_controller=_selection_port(),
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_transform_controller=_scene_transform_port(),
        history_service=history,
    )

    with pytest.raises(RuntimeError) as caught:
        context.push_history(command)

    assert caught.value is primary
    command.undo.assert_called_once_with(canvas)


def test_tool_context_delegates_delete_gesture_session_lifecycle() -> None:
    rollback_error = RuntimeError("rollback warning")
    session = SimpleNamespace(
        delete_atom=mock.Mock(),
        delete_bond=mock.Mock(),
        delete_ring=mock.Mock(),
        delete_scene_item=mock.Mock(),
        commit=mock.Mock(),
        rollback=mock.Mock(return_value=[rollback_error]),
    )
    delete_controller = SimpleNamespace(
        begin_delete_tool_session=mock.Mock(return_value=session),
    )
    context = ToolContext(
        object(),
        hit_testing_service=_hit_testing_port(),
        selection_controller=_selection_port(),
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_delete_controller=delete_controller,
        scene_transform_controller=_scene_transform_port(),
    )

    assert context.begin_delete_tool_session() is session
    command = object()
    context.commit_delete_tool_session(session, command)
    assert context.rollback_delete_tool_session(session) == [rollback_error]

    delete_controller.begin_delete_tool_session.assert_called_once_with()
    session.commit.assert_called_once_with(command)
    session.rollback.assert_called_once_with()


def test_tool_context_requires_delete_gesture_session_port() -> None:
    context = ToolContext(
        object(),
        hit_testing_service=_hit_testing_port(),
        selection_controller=_selection_port(),
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_delete_controller=SimpleNamespace(),
        scene_transform_controller=_scene_transform_port(),
    )

    with pytest.raises(AttributeError, match="begin_delete_tool_session"):
        context.begin_delete_tool_session()


@pytest.mark.parametrize(
    ("session", "error_type", "message"),
    [
        (None, RuntimeError, "returned no session"),
        (
            SimpleNamespace(commit=mock.Mock(), rollback=mock.Mock()),
            AttributeError,
            "delete_atom",
        ),
    ],
)
def test_tool_context_rejects_incomplete_delete_gesture_sessions(
    session,
    error_type,
    message: str,
) -> None:
    context = ToolContext(
        object(),
        hit_testing_service=_hit_testing_port(),
        selection_controller=_selection_port(),
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_delete_controller=SimpleNamespace(
            begin_delete_tool_session=mock.Mock(return_value=session),
        ),
        scene_transform_controller=_scene_transform_port(),
    )

    with pytest.raises(error_type, match=message):
        context.begin_delete_tool_session()

    if session is not None:
        session.rollback.assert_called_once_with()


def test_tool_context_rejected_delete_session_restores_guard_and_observers() -> None:
    group_callback = object()
    outline_callback = object()
    runtime = SimpleNamespace(
        active=True,
        guard_depth=1,
        group_callback=None,
        outline_callback=None,
        rollback_calls=0,
    )

    class IncompleteSession:
        delete_bond = staticmethod(lambda _bond_id: None)
        delete_ring = staticmethod(lambda _item: None)
        delete_scene_item = staticmethod(lambda _item, _state: None)
        commit = staticmethod(lambda _command=None: None)

        @staticmethod
        def rollback() -> list[BaseException]:
            runtime.rollback_calls += 1
            runtime.active = False
            runtime.guard_depth = 0
            runtime.group_callback = group_callback
            runtime.outline_callback = outline_callback
            return []

    session = IncompleteSession()
    context = ToolContext(
        object(),
        hit_testing_service=_hit_testing_port(),
        selection_controller=_selection_port(),
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_delete_controller=SimpleNamespace(
            begin_delete_tool_session=mock.Mock(return_value=session),
        ),
        scene_transform_controller=_scene_transform_port(),
    )

    with pytest.raises(AttributeError, match="delete_atom"):
        context.begin_delete_tool_session()

    assert runtime.rollback_calls == 1
    assert runtime.active is False
    assert runtime.guard_depth == 0
    assert runtime.group_callback is group_callback
    assert runtime.outline_callback is outline_callback


@pytest.mark.parametrize("primary_type", [KeyboardInterrupt, SystemExit])
def test_tool_context_validation_preserves_primary_when_rollback_retries_and_notes_break(
    primary_type,
) -> None:
    class BrokenPrimary(primary_type):
        def add_note(self, _note: str) -> None:
            raise RuntimeError("broken diagnostic hook")

    primary = BrokenPrimary("validation failed")
    rollback_failure = RuntimeError("rollback failed before recovery")
    group_callback = object()
    outline_callback = object()
    runtime = SimpleNamespace(
        active=True,
        guard_depth=1,
        group_callback=None,
        outline_callback=None,
        rollback_calls=0,
    )

    class FailOnceRollbackSession:
        @property
        def delete_atom(self):
            raise primary

        delete_bond = staticmethod(lambda _bond_id: None)
        delete_ring = staticmethod(lambda _item: None)
        delete_scene_item = staticmethod(lambda _item, _state: None)
        commit = staticmethod(lambda _command=None: None)

        @staticmethod
        def rollback() -> list[BaseException]:
            runtime.rollback_calls += 1
            if runtime.rollback_calls == 1:
                raise rollback_failure
            runtime.active = False
            runtime.guard_depth = 0
            runtime.group_callback = group_callback
            runtime.outline_callback = outline_callback
            return []

    session = FailOnceRollbackSession()
    context = ToolContext(
        object(),
        hit_testing_service=_hit_testing_port(),
        selection_controller=_selection_port(),
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_delete_controller=SimpleNamespace(
            begin_delete_tool_session=mock.Mock(return_value=session),
        ),
        scene_transform_controller=_scene_transform_port(),
    )

    with pytest.raises(primary_type) as raised:
        context.begin_delete_tool_session()

    assert raised.value is primary
    assert runtime.rollback_calls == 2
    assert runtime.active is False
    assert runtime.guard_depth == 0
    assert runtime.group_callback is group_callback
    assert runtime.outline_callback is outline_callback


@pytest.mark.parametrize("failure_stage", ["lookup", "call"])
def test_tool_context_retries_delete_session_rollback_port_once(
    failure_stage: str,
) -> None:
    first_failure = KeyboardInterrupt(f"rollback {failure_stage} failed once")

    class FailOnceRollbackSession:
        def __init__(self) -> None:
            self.lookups = 0
            self.calls = 0
            self.active = True
            self.guard_depth = 1

        @property
        def rollback(self):
            self.lookups += 1
            if failure_stage == "lookup" and self.lookups == 1:
                raise first_failure
            return self._rollback

        def _rollback(self) -> list[BaseException]:
            self.calls += 1
            if failure_stage == "call" and self.calls == 1:
                raise first_failure
            self.active = False
            self.guard_depth = 0
            return []

    session = FailOnceRollbackSession()

    errors = ToolContext.rollback_delete_tool_session(session)

    assert errors == [first_failure]
    assert session.lookups == (2 if failure_stage == "lookup" else 2)
    assert session.calls == (1 if failure_stage == "lookup" else 2)
    assert session.active is False
    assert session.guard_depth == 0


def test_tool_context_retries_returned_active_production_session() -> None:
    first_error = SystemExit("observer ports stayed unavailable once")

    class ActiveUntilSecondRollback:
        def __init__(self) -> None:
            self.active = True
            self.calls = 0

        def rollback(self) -> list[BaseException]:
            self.calls += 1
            if self.calls == 1:
                return [first_error]
            self.active = False
            return []

    session = ActiveUntilSecondRollback()

    errors = ToolContext.rollback_delete_tool_session(session)

    assert errors == [first_error]
    assert errors.completed is True
    assert session.calls == 2
    assert session.active is False


def test_tool_context_marks_persistently_active_rollback_incomplete() -> None:
    class PersistentlyActiveSession:
        active = True

        def __init__(self) -> None:
            self.calls = 0

        def rollback(self) -> list[BaseException]:
            self.calls += 1
            return []

    session = PersistentlyActiveSession()

    errors = ToolContext.rollback_delete_tool_session(session)

    assert errors.completed is False
    assert session.calls == 2
    assert any("remained active" in str(error) for error in errors)


def test_tool_context_delegates_handle_ports_to_injected_controller() -> None:
    pos = QPointF(3.0, 4.0)
    handle = object()
    handle_controller = _handle_port()
    context = ToolContext(
        object(),
        hit_testing_service=_hit_testing_port(),
        selection_controller=_selection_port(),
        note_controller=_note_port(),
        handle_controller=handle_controller,
        selection_rotation_controller=_selection_rotation_port(),
        scene_transform_controller=_scene_transform_port(),
    )

    context.update_handle_drag(handle, pos)
    handle_controller.update_handle_drag.assert_called_once_with(handle, pos)


def test_tool_context_delegates_selection_rotation_ports_to_injected_controller() -> (
    None
):
    pos = QPointF(3.0, 4.0)
    selection_rotation = _selection_rotation_port(
        begin_selection_3d_rotation=mock.Mock(return_value=True),
    )
    context = ToolContext(
        object(),
        hit_testing_service=_hit_testing_port(),
        selection_controller=_selection_port(),
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=selection_rotation,
        scene_transform_controller=_scene_transform_port(),
    )

    assert context.begin_selection_3d_rotation(axis_hint=7, press_pos=pos)
    context.update_selection_3d_rotation(1.0, 2.0)
    context.end_selection_3d_rotation()
    selection_rotation.begin_selection_3d_rotation.assert_called_once_with(
        axis_hint=7, press_pos=pos
    )
    selection_rotation.update_selection_3d_rotation.assert_called_once_with(1.0, 2.0)
    selection_rotation.end_selection_3d_rotation.assert_called_once_with()


def test_tool_context_delegates_scene_transform_ports_to_injected_controller() -> None:
    scene_transform = _scene_transform_port()
    context = ToolContext(
        object(),
        hit_testing_service=_hit_testing_port(),
        selection_controller=_selection_port(),
        note_controller=_note_port(),
        handle_controller=_handle_port(),
        selection_rotation_controller=_selection_rotation_port(),
        scene_transform_controller=scene_transform,
    )

    context.apply_bond_style(3, "double", 2)
    context.cycle_bond_style(4)
    context.flip_bond_direction(5)
    scene_transform.apply_bond_style.assert_called_once_with(3, "double", 2)
    scene_transform.cycle_bond_style.assert_called_once_with(4)
    scene_transform.flip_bond_direction.assert_called_once_with(5)
