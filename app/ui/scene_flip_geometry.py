from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from core.model import Atom
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsItem

from ui.scene_item_state import ARROW_KINDS


def flip_point(point: QPointF, center: QPointF, horizontal: bool) -> QPointF:
    if horizontal:
        return QPointF(center.x() - (point.x() - center.x()), point.y())
    return QPointF(point.x(), center.y() - (point.y() - center.y()))


def bounds_from_points(points: list[QPointF]) -> QRectF | None:
    if not points:
        return None
    min_x = min(point.x() for point in points)
    max_x = max(point.x() for point in points)
    min_y = min(point.y() for point in points)
    max_y = max(point.y() for point in points)
    return QRectF(QPointF(min_x, min_y), QPointF(max_x, max_y))


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
        arrow_points: list[QPointF] = []
        for key in ("start", "end", "control"):
            point = state.get(key)
            if point is not None:
                arrow_points.append(QPointF(*point))
        return bounds_from_points(arrow_points)
    rect = item.sceneBoundingRect()
    return rect if rect.isValid() else None


def flip_center_for_selection(
    atom_ids: set[int],
    items: Sequence[QGraphicsItem],
    *,
    atoms: Mapping[int, Atom],
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


__all__ = [
    "bounds_from_points",
    "center_for_flip_group",
    "flip_bounds_for_item",
    "flip_center_for_selection",
    "flip_point",
]
