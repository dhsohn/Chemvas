from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsItem

from ui.scene_item_state import ARROW_KINDS


@dataclass(slots=True)
class TransformSelectionGroups:
    component_items: list[list[QGraphicsItem]]
    standalone_items: list[QGraphicsItem]


@dataclass(slots=True)
class FlipAtomPositionMaps:
    before_positions: dict[int, tuple[float, float]]
    after_positions: dict[int, tuple[float, float]]
    transformed_atom_positions: dict[int, tuple[float, float]]


def flip_bounds_for_item(
    item: QGraphicsItem,
    *,
    scene_item_state_getter: Callable[[QGraphicsItem], dict],
    bounds_from_points: Callable[[list[QPointF]], QRectF | None],
) -> QRectF | None:
    kind = item.data(0)
    if kind == "note":
        rect = item.sceneBoundingRect()
        return rect if rect.isValid() else None
    if kind in {"mark", "ts_bracket", "orbital"}:
        rect = item.sceneBoundingRect()
        return rect if rect.isValid() else None
    state = scene_item_state_getter(item)
    if not state:
        return None
    if kind == "ring":
        points = [QPointF(x, y) for x, y in state.get("points", [])]
        return bounds_from_points(points)
    if kind in ARROW_KINDS:
        points: list[QPointF] = []
        for key in ("start", "end", "control"):
            point = state.get(key)
            if point is not None:
                points.append(QPointF(*point))
        return bounds_from_points(points)
    rect = item.sceneBoundingRect()
    return rect if rect.isValid() else None


def flip_center_for_selection(
    atom_ids: set[int],
    items: Sequence[QGraphicsItem],
    *,
    atoms: Mapping[int, object],
    flip_bounds_getter: Callable[[QGraphicsItem], QRectF | None],
) -> QPointF | None:
    xs: list[float] = []
    ys: list[float] = []
    for atom_id in atom_ids:
        atom = atoms.get(atom_id)
        if atom is None:
            continue
        xs.append(atom.x)
        ys.append(atom.y)
    for item in items:
        kind = item.data(0)
        if kind in {"atom", "bond"}:
            continue
        bounds = flip_bounds_getter(item)
        if bounds is None:
            continue
        xs.extend([bounds.left(), bounds.right()])
        ys.extend([bounds.top(), bounds.bottom()])
    if not xs or not ys:
        return None
    return QPointF((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def center_for_flip_group(
    atom_ids: set[int],
    items: Sequence[QGraphicsItem],
    *,
    bounding_box_center_for_atoms: Callable[[set[int]], QPointF | None],
    flip_center_for_selection_getter: Callable[[set[int], Sequence[QGraphicsItem]], QPointF | None],
) -> QPointF | None:
    if atom_ids:
        return bounding_box_center_for_atoms(atom_ids)
    return flip_center_for_selection_getter(set(), items)


def flip_scene_item_state(
    item: QGraphicsItem,
    before_state: dict,
    *,
    center: QPointF,
    horizontal: bool,
    transformed_atom_positions: Mapping[int, tuple[float, float]],
    atoms: Mapping[int, object],
    flip_point: Callable[[QPointF, QPointF, bool], QPointF],
    ts_bracket_rect_from_state: Callable[[dict], QRectF | None],
) -> dict:
    if not before_state:
        return {}
    kind = before_state.get("kind")
    after_state = dict(before_state)
    if kind == "ring":
        after_state["points"] = [
            (flipped.x(), flipped.y())
            for flipped in (
                flip_point(QPointF(x, y), center, horizontal)
                for x, y in before_state.get("points", [])
            )
        ]
        return after_state
    if kind == "note":
        rect = item.sceneBoundingRect()
        if rect.isValid():
            if horizontal:
                after_state["x"] = center.x() - (rect.right() - center.x())
                after_state["y"] = before_state.get("y", 0.0)
            else:
                after_state["x"] = before_state.get("x", 0.0)
                after_state["y"] = center.y() - (rect.bottom() - center.y())
        else:
            flipped = flip_point(
                QPointF(before_state.get("x", 0.0), before_state.get("y", 0.0)),
                center,
                horizontal,
            )
            after_state["x"] = flipped.x()
            after_state["y"] = flipped.y()
        return after_state
    if kind == "mark":
        flipped = flip_point(
            QPointF(before_state.get("x", 0.0), before_state.get("y", 0.0)),
            center,
            horizontal,
        )
        after_state["x"] = flipped.x()
        after_state["y"] = flipped.y()
        atom_id = before_state.get("atom_id")
        if isinstance(atom_id, int):
            atom_position = transformed_atom_positions.get(atom_id)
            if atom_position is None:
                atom = atoms.get(atom_id)
                if atom is not None:
                    atom_position = (atom.x, atom.y)
            if atom_position is not None:
                after_state["dx"] = flipped.x() - atom_position[0]
                after_state["dy"] = flipped.y() - atom_position[1]
        return after_state
    if kind == "orbital":
        center_state = before_state.get("center")
        if center_state is not None:
            flipped = flip_point(QPointF(*center_state), center, horizontal)
            after_state["center"] = (flipped.x(), flipped.y())
        rotation = float(before_state.get("rotation", 0.0))
        after_state["rotation"] = 180.0 - rotation if horizontal else -rotation
        return after_state
    if kind == "ts_bracket":
        rect = ts_bracket_rect_from_state(before_state)
        if rect is None:
            return after_state
        flipped_rect = QRectF(
            flip_point(rect.topLeft(), center, horizontal),
            flip_point(rect.bottomRight(), center, horizontal),
        ).normalized()
        after_state["left"] = flipped_rect.left()
        after_state["top"] = flipped_rect.top()
        after_state["right"] = flipped_rect.right()
        after_state["bottom"] = flipped_rect.bottom()
        return after_state
    if kind in ARROW_KINDS:
        for key in ("start", "end", "control"):
            point = before_state.get(key)
            if point is None:
                continue
            flipped = flip_point(QPointF(*point), center, horizontal)
            after_state[key] = (flipped.x(), flipped.y())
        return after_state
    return {}


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
    "center_for_flip_group",
    "flip_bounds_for_item",
    "flip_center_for_selection",
    "flip_scene_item_state",
    "group_items_for_flip_transform",
]
