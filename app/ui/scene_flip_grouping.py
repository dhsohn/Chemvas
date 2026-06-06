from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem


@dataclass(slots=True)
class TransformSelectionGroups:
    component_items: list[list[QGraphicsItem]]
    standalone_items: list[QGraphicsItem]


@dataclass(slots=True)
class FlipAtomPositionMaps:
    before_positions: dict[int, tuple[float, float]]
    after_positions: dict[int, tuple[float, float]]
    transformed_atom_positions: dict[int, tuple[float, float]]


def group_items_for_flip_transform(
    items: Sequence[QGraphicsItem],
    *,
    atom_components: Sequence[set[int]],
    marks_by_atom: Mapping[int, Sequence[QGraphicsItem]],
) -> TransformSelectionGroups:
    component_by_atom = {
        atom_id: index
        for index, component in enumerate(atom_components)
        for atom_id in component
    }
    group_items: list[list[QGraphicsItem]] = [[] for _ in atom_components]
    group_seen: list[set[QGraphicsItem]] = [set() for _ in atom_components]
    standalone_items: list[QGraphicsItem] = []
    standalone_seen: set[QGraphicsItem] = set()

    def assign_to_component(index: int, item: QGraphicsItem) -> None:
        if item in group_seen[index]:
            return
        group_seen[index].add(item)
        group_items[index].append(item)

    def assign_standalone(item: QGraphicsItem) -> None:
        if item in standalone_seen:
            return
        standalone_seen.add(item)
        standalone_items.append(item)

    for index, component in enumerate(atom_components):
        for atom_id in component:
            for mark in marks_by_atom.get(atom_id, []):
                assign_to_component(index, mark)

    for item in items:
        kind = item.data(0)
        if kind in {"atom", "bond"}:
            continue
        if kind == "ring":
            ring_atom_ids = item.data(2)
            if isinstance(ring_atom_ids, list):
                for atom_id in ring_atom_ids:
                    component_index = component_by_atom.get(atom_id)
                    if component_index is not None:
                        assign_to_component(component_index, item)
                        break
                else:
                    assign_standalone(item)
                continue
        if kind == "mark":
            data = item.data(1) or {}
            atom_id = data.get("atom_id")
            component_index = component_by_atom.get(atom_id) if isinstance(atom_id, int) else None
            if component_index is not None:
                assign_to_component(component_index, item)
            else:
                assign_standalone(item)
            continue
        assign_standalone(item)

    return TransformSelectionGroups(
        component_items=group_items,
        standalone_items=standalone_items,
    )


def build_flip_atom_position_maps(
    atom_ids: Sequence[int],
    *,
    atoms: Mapping[int, object],
    center: QPointF,
    flip_point: Callable[[QPointF, QPointF], QPointF],
) -> FlipAtomPositionMaps:
    before_positions: dict[int, tuple[float, float]] = {}
    after_positions: dict[int, tuple[float, float]] = {}
    transformed_atom_positions: dict[int, tuple[float, float]] = {}

    for atom_id in atom_ids:
        atom = atoms.get(atom_id)
        if atom is None:
            continue
        before_positions[atom_id] = (atom.x, atom.y)
        flipped = flip_point(QPointF(atom.x, atom.y), center)
        position = (flipped.x(), flipped.y())
        after_positions[atom_id] = position
        transformed_atom_positions[atom_id] = position

    return FlipAtomPositionMaps(
        before_positions=before_positions,
        after_positions=after_positions,
        transformed_atom_positions=transformed_atom_positions,
    )


__all__ = [
    "FlipAtomPositionMaps",
    "TransformSelectionGroups",
    "build_flip_atom_position_maps",
    "group_items_for_flip_transform",
]
