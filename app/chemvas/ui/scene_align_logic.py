"""Per-object translations that align or distribute a set of rectangles."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF

if TYPE_CHECKING:
    from collections.abc import Sequence

ALIGN_MODES = ("left", "center", "right", "top", "middle", "bottom")
DISTRIBUTE_AXES = ("horizontal", "vertical")


def _union(rects: Sequence[QRectF]) -> QRectF:
    overall = QRectF(rects[0])
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


__all__ = ["ALIGN_MODES", "DISTRIBUTE_AXES", "align_deltas", "distribute_deltas"]
