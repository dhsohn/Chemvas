from __future__ import annotations

from types import SimpleNamespace

from chemvas.ui.canvas_group_state import (
    CanvasGroupState,
    CanvasSceneGroup,
    clear_groups_for,
    group_ids_for_members_for,
    group_state_for,
    register_group_for,
    remove_group_for,
    restore_group_for,
)
from tests.runtime_state import canvas_runtime_state


def _canvas() -> SimpleNamespace:
    return SimpleNamespace(
        runtime_state=canvas_runtime_state(group_state=CanvasGroupState())
    )


def test_group_state_reads_the_canonical_container() -> None:
    canvas = _canvas()

    state = group_state_for(canvas)

    assert group_state_for(canvas) is state
    assert state.groups == {}
    assert state.next_group_id == 1
    assert state.expanding is False


def test_register_group_assigns_incrementing_ids() -> None:
    canvas = _canvas()
    item = object()

    first = register_group_for(canvas, {1, 2}, [item])
    second = register_group_for(canvas, {3}, [])

    state = group_state_for(canvas)
    assert (first, second) == (1, 2)
    assert state.groups[first].atom_ids == {1, 2}
    assert state.groups[first].items == [item]
    assert state.groups[second].atom_ids == {3}
    assert state.next_group_id == 3


def test_remove_group_returns_removed_group() -> None:
    canvas = _canvas()
    group_id = register_group_for(canvas, {1}, [])

    removed = remove_group_for(canvas, group_id)

    assert removed is not None
    assert removed.atom_ids == {1}
    assert group_state_for(canvas).groups == {}
    assert remove_group_for(canvas, group_id) is None


def test_restore_group_reinstates_and_bumps_next_id() -> None:
    canvas = _canvas()

    restore_group_for(canvas, 5, CanvasSceneGroup({7}, []))

    state = group_state_for(canvas)
    assert state.groups[5].atom_ids == {7}
    assert state.next_group_id == 6


def test_group_ids_for_members_matches_atoms_and_item_identity() -> None:
    canvas = _canvas()
    item = object()
    other_item = object()
    atom_group = register_group_for(canvas, {1, 2}, [])
    item_group = register_group_for(canvas, set(), [item])

    assert group_ids_for_members_for(canvas, {2}, []) == {atom_group}
    assert group_ids_for_members_for(canvas, set(), [item]) == {item_group}
    assert group_ids_for_members_for(canvas, set(), [other_item]) == set()
    assert group_ids_for_members_for(canvas, {1}, [item]) == {atom_group, item_group}


def test_clear_groups_resets_state() -> None:
    canvas = _canvas()
    register_group_for(canvas, {1}, [])
    state = group_state_for(canvas)
    state.expanding = True

    clear_groups_for(canvas)

    assert state.groups == {}
    assert state.next_group_id == 1
    assert state.expanding is False
