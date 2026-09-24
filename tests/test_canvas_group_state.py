from __future__ import annotations

from types import SimpleNamespace

from chemvas.domain.document.groups import SceneGroup
from chemvas.ui.canvas.canvas_group_state import (
    CanvasGroupState,
    clear_groups_for,
    group_ids_for_members_for,
    register_group_for,
    restore_group_for,
)
from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id
from tests.runtime_state import canvas_runtime_state


def _canvas() -> SimpleNamespace:
    return SimpleNamespace(
        runtime_state=canvas_runtime_state(group_state=CanvasGroupState())
    )


def test_group_state_reads_the_canonical_container() -> None:
    canvas = _canvas()

    state = canvas.runtime_state.group_state

    assert canvas.runtime_state.group_state is state
    assert state.groups == {}
    assert state.next_group_id == 1
    assert state.expanding is False


def test_register_group_assigns_incrementing_ids() -> None:
    canvas = _canvas()
    item = SimpleNamespace(data=lambda role: 11 if role == 3 else None)

    first = register_group_for(
        canvas, {1, 2}, [require_scene_record_id(item) for item in [item]]
    )
    second = register_group_for(
        canvas, {3}, [require_scene_record_id(item) for item in []]
    )

    state = canvas.runtime_state.group_state
    assert (first, second) == (1, 2)
    assert state.groups[first].atom_ids == {1, 2}
    assert state.groups[first].item_ids == [11]
    assert state.groups[second].atom_ids == {3}
    assert state.next_group_id == 3


def test_remove_group_returns_removed_group() -> None:
    canvas = _canvas()
    group_id = register_group_for(
        canvas, {1}, [require_scene_record_id(item) for item in []]
    )

    removed = canvas.runtime_state.group_state.groups.pop(group_id, None)

    assert removed is not None
    assert removed.atom_ids == {1}
    assert canvas.runtime_state.group_state.groups == {}
    assert canvas.runtime_state.group_state.groups.pop(group_id, None) is None


def test_restore_group_reinstates_and_bumps_next_id() -> None:
    canvas = _canvas()

    restore_group_for(canvas, 5, SceneGroup({7}, []))

    state = canvas.runtime_state.group_state
    assert state.groups[5].atom_ids == {7}
    assert state.next_group_id == 6


def test_group_ids_for_members_matches_atoms_and_item_identity() -> None:
    canvas = _canvas()
    item = SimpleNamespace(data=lambda role: 11 if role == 3 else None)
    other_item = SimpleNamespace(data=lambda role: 12 if role == 3 else None)
    atom_group = register_group_for(
        canvas, {1, 2}, [require_scene_record_id(item) for item in []]
    )
    item_group = register_group_for(
        canvas, set(), [require_scene_record_id(item) for item in [item]]
    )

    assert group_ids_for_members_for(canvas, {2}, []) == {atom_group}
    assert group_ids_for_members_for(canvas, set(), [item]) == {item_group}
    assert group_ids_for_members_for(canvas, set(), [other_item]) == set()
    assert group_ids_for_members_for(canvas, {1}, [item]) == {atom_group, item_group}


def test_clear_groups_resets_state() -> None:
    canvas = _canvas()
    register_group_for(canvas, {1}, [require_scene_record_id(item) for item in []])
    state = canvas.runtime_state.group_state
    state.expanding = True

    clear_groups_for(canvas)

    assert state.groups == {}
    assert state.next_group_id == 1
    assert state.expanding is False
