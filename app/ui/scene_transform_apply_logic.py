from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from core.history import HistoryCommand, SetAtomPositionsCommand
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem

from ui.history_commands import UpdateSceneItemCommand
from ui.scene_transform_logic import FlipAtomPositionMaps


@dataclass(slots=True)
class SceneItemStateUpdate:
    item: QGraphicsItem
    before_state: dict
    after_state: dict


def build_scene_item_flip_updates(
    item_states: Sequence[tuple[QGraphicsItem, dict]],
    *,
    center: QPointF,
    horizontal: bool,
    transformed_atom_positions: Mapping[int, tuple[float, float]],
    flip_state_getter: Callable[[QGraphicsItem, dict, QPointF, bool, Mapping[int, tuple[float, float]]], dict],
) -> list[SceneItemStateUpdate]:
    updates: list[SceneItemStateUpdate] = []
    for item, before_state in item_states:
        after_state = flip_state_getter(
            item,
            before_state,
            center,
            horizontal,
            transformed_atom_positions,
        )
        if not before_state or not after_state or before_state == after_state:
            continue
        updates.append(
            SceneItemStateUpdate(
                item=item,
                before_state=before_state,
                after_state=after_state,
            )
        )
    return updates


def apply_component_flip_transform(
    *,
    component_items: Sequence[QGraphicsItem],
    scene_item_state_getter: Callable[[QGraphicsItem], dict],
    position_maps: FlipAtomPositionMaps,
    center: QPointF,
    horizontal: bool,
    flip_state_getter: Callable[[QGraphicsItem, dict, QPointF, bool, Mapping[int, tuple[float, float]]], dict],
    set_atom_positions: Callable[[dict[int, tuple[float, float]], bool], None],
    apply_scene_item_state: Callable[[QGraphicsItem, dict], None],
) -> list[HistoryCommand]:
    commands: list[HistoryCommand] = []
    item_state_updates = build_scene_item_flip_updates(
        [(item, scene_item_state_getter(item)) for item in component_items],
        center=center,
        horizontal=horizontal,
        transformed_atom_positions=position_maps.transformed_atom_positions,
        flip_state_getter=flip_state_getter,
    )
    if position_maps.before_positions and position_maps.before_positions != position_maps.after_positions:
        set_atom_positions(position_maps.after_positions, update_selection=False)
        commands.append(
            SetAtomPositionsCommand(
                before_positions=position_maps.before_positions,
                after_positions=position_maps.after_positions,
                update_selection=True,
            )
        )
    for update in item_state_updates:
        apply_scene_item_state(update.item, update.after_state)
        commands.append(
            UpdateSceneItemCommand(
                update.item,
                update.before_state,
                update.after_state,
            )
        )
    return commands


def apply_standalone_flip_transform(
    item: QGraphicsItem,
    *,
    scene_item_state_getter: Callable[[QGraphicsItem], dict],
    center: QPointF,
    horizontal: bool,
    flip_state_getter: Callable[[QGraphicsItem, dict, QPointF, bool, Mapping[int, tuple[float, float]]], dict],
    apply_scene_item_state: Callable[[QGraphicsItem, dict], None],
) -> UpdateSceneItemCommand | None:
    updates = build_scene_item_flip_updates(
        [(item, scene_item_state_getter(item))],
        center=center,
        horizontal=horizontal,
        transformed_atom_positions={},
        flip_state_getter=flip_state_getter,
    )
    if not updates:
        return None
    update = updates[0]
    apply_scene_item_state(update.item, update.after_state)
    return UpdateSceneItemCommand(
        update.item,
        update.before_state,
        update.after_state,
    )


__all__ = [
    "SceneItemStateUpdate",
    "apply_component_flip_transform",
    "apply_standalone_flip_transform",
    "build_scene_item_flip_updates",
]
