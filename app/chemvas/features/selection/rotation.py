from __future__ import annotations

import math
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from chemvas.domain.document import Atom


ROTATION_SNAP_STEP_DEGREES = 15.0


class Point2D(Protocol):
    """Anything with Qt's ``QPointF`` accessors; the feature stays Qt-free."""

    def x(self) -> float: ...
    def y(self) -> float: ...


def selection_transform_center(
    points: Iterable[tuple[float, float]],
) -> tuple[float, float] | None:
    points = list(points)
    if not points:
        return None
    xs, ys = zip(*points, strict=True)
    return (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0


def reflected_point(
    point: Point2D, center: Point2D, horizontal: bool
) -> tuple[float, float]:
    if horizontal:
        return center.x() - (point.x() - center.x()), point.y()
    return point.x(), center.y() - (point.y() - center.y())


def rotated_point_coordinates(
    point: Point2D, center: Point2D, angle_radians: float
) -> tuple[float, float]:
    cos_a = math.cos(angle_radians)
    sin_a = math.sin(angle_radians)
    dx = point.x() - center.x()
    dy = point.y() - center.y()
    return (
        center.x() + dx * cos_a - dy * sin_a,
        center.y() + dx * sin_a + dy * cos_a,
    )


def rotated_atom_positions(
    atom_ids: Iterable[int],
    *,
    atoms: Mapping[int, Atom],
    center: Point2D,
    angle_radians: float,
) -> dict[int, tuple[float, float]]:
    cos_a = math.cos(angle_radians)
    sin_a = math.sin(angle_radians)
    rotated: dict[int, tuple[float, float]] = {}
    for atom_id in atom_ids:
        atom = atoms.get(atom_id)
        if atom is None:
            continue
        dx = atom.x - center.x()
        dy = atom.y - center.y()
        rotated[atom_id] = (
            center.x() + dx * cos_a - dy * sin_a,
            center.y() + dx * sin_a + dy * cos_a,
        )
    return rotated


def rotation_drag_angle(
    center: Point2D,
    start: Point2D,
    pos: Point2D,
    *,
    snap_step: float | None = None,
) -> float:
    """Degrees the pointer has swept around ``center`` since ``start``.

    Positive is clockwise on screen (y grows downward). ``snap_step``
    rounds the sweep to that many degrees, for a Shift-constrained drag.
    """
    start_angle = math.atan2(start.y() - center.y(), start.x() - center.x())
    angle = math.atan2(pos.y() - center.y(), pos.x() - center.x())
    sweep = math.degrees(angle - start_angle)
    sweep = (sweep + 180.0) % 360.0 - 180.0
    if snap_step:
        sweep = round(sweep / snap_step) * snap_step
    return sweep


def selection_frame_applies(atom_count: int, rotatable_item_count: int) -> bool:
    """Whether a selection gets a frame with a rotation handle.

    Rotation only means something for two or more atoms, or for an item
    that turns about its own centre; a lone atom has nothing to rotate.
    """
    return atom_count >= 2 or rotatable_item_count >= 1


__all__ = [
    "ROTATION_SNAP_STEP_DEGREES",
    "orbital_handle_positions",
    "orbital_rotation_angle",
    "orbital_scale_factor",
    "reflected_point",
    "rotated_atom_positions",
    "rotated_point_coordinates",
    "rotation_drag_angle",
    "selection_frame_applies",
    "selection_transform_center",
]


def orbital_handle_positions(
    center: tuple[float, float], base_dist: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    return (center[0] + base_dist, center[1]), (center[0], center[1] - base_dist)


def orbital_scale_factor(
    center: Point2D,
    pos: Point2D,
    base_dist: float,
    *,
    minimum_scale: float = 0.2,
) -> float:
    safe_base_dist = max(float(base_dist), 1e-6)
    dist = math.hypot(pos.x() - center.x(), pos.y() - center.y())
    return max(minimum_scale, dist / safe_base_dist)


def orbital_rotation_angle(
    center: Point2D,
    pos: Point2D,
    *,
    snap_enabled: bool,
    snap_step: int,
) -> float:
    angle = math.degrees(math.atan2(pos.y() - center.y(), pos.x() - center.x()))
    if snap_enabled:
        step = max(1, int(snap_step))
        angle = round(angle / step) * step
    return angle
