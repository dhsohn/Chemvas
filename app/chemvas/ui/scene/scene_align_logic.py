"""Per-object translations that align or distribute a set of rectangles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from PyQt6.QtCore import QRectF

ALIGN_MODES = ("left", "center", "right", "top", "middle", "bottom")
DISTRIBUTE_AXES = ("horizontal", "vertical")


def _union(rects: Sequence[QRectF]) -> QRectF:
    overall = rects[0]
    for rect in rects[1:]:
        overall = overall.united(rect)
    return overall


def align_deltas(rects: Sequence[QRectF], mode: str) -> list[tuple[float, float]]:
    """Translation per rect that lines the given edge or center up across all."""
    if mode not in ALIGN_MODES:
        raise ValueError(f"Unknown align mode: {mode!r}")
    if len(rects) < 2:
        return [(0.0, 0.0) for _rect in rects]
    overall = _union(rects)
    deltas: list[tuple[float, float]] = []
    for rect in rects:
        if mode == "left":
            deltas.append((overall.left() - rect.left(), 0.0))
        elif mode == "center":
            deltas.append((overall.center().x() - rect.center().x(), 0.0))
        elif mode == "right":
            deltas.append((overall.right() - rect.right(), 0.0))
        elif mode == "top":
            deltas.append((0.0, overall.top() - rect.top()))
        elif mode == "middle":
            deltas.append((0.0, overall.center().y() - rect.center().y()))
        else:
            deltas.append((0.0, overall.bottom() - rect.bottom()))
    return deltas


def distribute_deltas(rects: Sequence[QRectF], axis: str) -> list[tuple[float, float]]:
    """Translation per rect that equalizes the gaps between neighbours.

    The outermost rects along the axis stay where they are; the others are
    spread so every gap between neighbouring rects is the same. Fewer than
    three rects have nothing to spread and get zero deltas.
    """
    if axis not in DISTRIBUTE_AXES:
        raise ValueError(f"Unknown distribute axis: {axis!r}")
    if len(rects) < 3:
        return [(0.0, 0.0) for _rect in rects]
    horizontal = axis == "horizontal"

    def low(rect: QRectF) -> float:
        return rect.left() if horizontal else rect.top()

    def size(rect: QRectF) -> float:
        return rect.width() if horizontal else rect.height()

    order = sorted(
        range(len(rects)),
        key=lambda index: low(rects[index]) + size(rects[index]) * 0.5,
    )
    first, last = rects[order[0]], rects[order[-1]]
    span = (low(last) + size(last)) - low(first)
    free = span - sum(size(rects[index]) for index in order)
    gap = free / (len(rects) - 1)
    deltas = [(0.0, 0.0)] * len(rects)
    cursor = low(first) + size(first) + gap
    for index in order[1:-1]:
        shift = cursor - low(rects[index])
        deltas[index] = (shift, 0.0) if horizontal else (0.0, shift)
        cursor += size(rects[index]) + gap
    return deltas


@dataclass(frozen=True, slots=True)
class AlignObject:
    """One thing Align/Distribute moves as a unit.

    A whole molecule (every atom of a structure that has a selected atom), a
    standalone scene item, or a group carrying both.
    """

    rect: QRectF
    atom_ids: frozenset[int]
    items: tuple[object, ...]


def alignment_objects(
    structures: Sequence[set[int]],
    items: list[Any],
    *,
    groups: Iterable[Any],
    object_rect: Callable[[set[int], list[Any]], QRectF | None],
) -> list[AlignObject]:
    objects: list[AlignObject] = []
    claimed_atoms: set[int] = set()
    claimed_items: set[int] = set()
    # A group is one object: its structures and items keep their layout.
    for group in groups:
        group_atoms: set[int] = set()
        for structure in structures:
            if structure & group.atom_ids:
                group_atoms |= structure
        group_items = [
            item for item in items if require_scene_record_id(item) in group.item_ids
        ]
        if not group_atoms and not group_items:
            continue
        rect = object_rect(group_atoms, group_items)
        if rect is None:
            continue
        objects.append(AlignObject(rect, frozenset(group_atoms), tuple(group_items)))
        claimed_atoms |= group_atoms
        claimed_items |= {id(item) for item in group_items}
    for structure in structures:
        if structure & claimed_atoms:
            continue
        rect = object_rect(structure, [])
        if rect is not None:
            objects.append(AlignObject(rect, frozenset(structure), ()))
    for item in items:
        if id(item) in claimed_items:
            continue
        rect = item.sceneBoundingRect()
        if rect.isValid():
            objects.append(AlignObject(rect, frozenset(), (item,)))
    return objects


__all__ = [
    "ALIGN_MODES",
    "DISTRIBUTE_AXES",
    "AlignObject",
    "align_deltas",
    "alignment_objects",
    "distribute_deltas",
]
