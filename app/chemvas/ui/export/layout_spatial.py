"""Bounded, exact broad phase for painted layout collision paths."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from PyQt6.QtGui import QPainterPath

MAX_LAYOUT_WORK_UNITS = 10_000
MAX_SPATIAL_PROBES = 2_000_000
MAX_PATH_ELEMENTS = 100_000
MAX_TOTAL_PATH_ELEMENTS = 2_000_000
MAX_INTERSECTION_ELEMENTS = 20_000_000
MAX_INTERSECTION_COMPLEXITY = 100_000_000
MAX_COLLISION_PATHS = 100_000


def layout_limit(reason: str, *, containment_only: bool = True) -> ValueError:
    return ValueError(
        f"input document exceeds the {reason}; "
        + (
            "use --sheet-only for containment only (collisions remain unchecked)"
            if containment_only
            else "reduce the geometry complexity before checking again"
        )
    )


def validate_path(path: QPainterPath) -> None:
    if path.elementCount() > MAX_PATH_ELEMENTS:
        raise layout_limit(
            f"layout path limit of {MAX_PATH_ELEMENTS} elements", containment_only=False
        )
    if not all(math.isfinite(v) for v in path.boundingRect().getRect()):
        raise ValueError("Cannot measure non-finite native content bounds.")


@dataclass
class _Node:
    bounds: QRectF
    indices: tuple[int, ...] = ()
    left: _Node | None = None
    right: _Node | None = None


def overlapping_bounds(paths: Sequence[QPainterPath]) -> Iterator[tuple[int, int]]:
    """Yield each positive-bounds pair once, with bounded tree traversal.

    Median subdivision along the wider axis handles both rows and columns.
    Bounding boxes only cull impossible intersections; glyph holes and dashed
    gaps still go through the caller's exact painted-path intersection.
    """
    if len(paths) > MAX_COLLISION_PATHS:
        raise layout_limit(f"layout path-count limit of {MAX_COLLISION_PATHS}")
    total = 0
    bounds = []
    for path in paths:
        validate_path(path)
        total += path.elementCount()
        if total > MAX_TOTAL_PATH_ELEMENTS:
            raise layout_limit(
                f"layout total-path limit of {MAX_TOTAL_PATH_ELEMENTS} elements"
            )
        bounds.append(path.boundingRect())

    def build(indices: list[int]) -> _Node:
        box = QRectF(bounds[indices[0]])
        for index in indices[1:]:
            box = box.united(bounds[index])
        if len(indices) <= 8:
            return _Node(box, tuple(indices))
        horizontal = box.width() >= box.height()
        indices.sort(
            key=lambda i: (
                bounds[i].center().x() if horizontal else bounds[i].center().y(),
                i,
            )
        )
        middle = len(indices) // 2
        return _Node(box, left=build(indices[:middle]), right=build(indices[middle:]))

    indices = [i for i, path in enumerate(paths) if not path.isEmpty()]
    if not indices:
        return
    root = build(indices)
    probes = 0
    for index in indices:
        stack = [root]
        while stack:
            node = stack.pop()
            probes += 1
            if probes > MAX_SPATIAL_PROBES:
                raise layout_limit(
                    f"layout spatial-search limit of {MAX_SPATIAL_PROBES}"
                )
            if not bounds[index].intersects(node.bounds):
                continue
            for other in node.indices:
                probes += 1
                if probes > MAX_SPATIAL_PROBES:
                    raise layout_limit(
                        f"layout spatial-search limit of {MAX_SPATIAL_PROBES}"
                    )
                if other > index and bounds[index].intersects(bounds[other]):
                    yield index, other
            if node.right is not None:
                stack.append(node.right)
            if node.left is not None:
                stack.append(node.left)
