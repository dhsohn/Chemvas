from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ui.canvas_state_lookup import ensure_canvas_state


@dataclass(slots=True)
class CanvasSceneGroup:
    atom_ids: set[int] = field(default_factory=set)
    items: list[Any] = field(default_factory=list)


@dataclass(slots=True)
class CanvasGroupState:
    groups: dict[int, CanvasSceneGroup] = field(default_factory=dict)
    next_group_id: int = 1
    expanding: bool = False


def group_state_for(canvas: Any) -> CanvasGroupState:
    return ensure_canvas_state(canvas, "group_state", CanvasGroupState)


def clear_groups_for(canvas: Any) -> None:
    state = group_state_for(canvas)
    state.groups.clear()
    state.next_group_id = 1
    state.expanding = False


def register_group_for(canvas: Any, atom_ids: set[int], items: list[Any]) -> int:
    state = group_state_for(canvas)
    group_id = state.next_group_id
    state.next_group_id += 1
    state.groups[group_id] = CanvasSceneGroup(set(atom_ids), list(items))
    return group_id


def restore_group_for(canvas: Any, group_id: int, group: CanvasSceneGroup) -> None:
    state = group_state_for(canvas)
    state.groups[group_id] = group
    if group_id >= state.next_group_id:
        state.next_group_id = group_id + 1


def remove_group_for(canvas: Any, group_id: int) -> CanvasSceneGroup | None:
    return group_state_for(canvas).groups.pop(group_id, None)


def group_ids_for_members_for(canvas: Any, atom_ids: set[int], items: list[Any]) -> set[int]:
    state = group_state_for(canvas)
    if not state.groups:
        return set()
    group_ids: set[int] = set()
    for group_id, group in state.groups.items():
        if group.atom_ids & atom_ids:
            group_ids.add(group_id)
            continue
        if any(any(member is item for member in group.items) for item in items):
            group_ids.add(group_id)
    return group_ids


__all__ = [
    "CanvasGroupState",
    "CanvasSceneGroup",
    "clear_groups_for",
    "group_ids_for_members_for",
    "group_state_for",
    "register_group_for",
    "remove_group_for",
    "restore_group_for",
]
