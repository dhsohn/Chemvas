from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chemvas.domain.document.groups import SceneGroup
from chemvas.features.groups import group_ids_for_members


@dataclass(slots=True)
class CanvasGroupState:
    groups: dict[int, SceneGroup] = field(default_factory=dict)
    next_group_id: int = 1
    expanding: bool = False


def clear_groups_for(canvas: Any) -> None:
    state = canvas.runtime_state.group_state
    state.groups.clear()
    state.next_group_id = 1
    state.expanding = False


def register_group_for(canvas: Any, atom_ids: set[int], item_ids: list[int]) -> int:
    state = canvas.runtime_state.group_state
    group_id = state.next_group_id
    state.next_group_id += 1
    state.groups[group_id] = SceneGroup(set(atom_ids), list(item_ids))
    return group_id


def restore_group_for(canvas: Any, group_id: int, group: SceneGroup) -> None:
    state = canvas.runtime_state.group_state
    state.groups[group_id] = group
    if group_id >= state.next_group_id:
        state.next_group_id = group_id + 1


def group_ids_for_members_for(
    canvas: Any, atom_ids: set[int], items: list[Any]
) -> set[int]:
    return group_ids_for_members(
        canvas.runtime_state.group_state.groups,
        atom_ids,
        [item.data(3) for item in items],
    )


__all__ = [
    "CanvasGroupState",
    "clear_groups_for",
    "group_ids_for_members_for",
    "register_group_for",
    "restore_group_for",
]
