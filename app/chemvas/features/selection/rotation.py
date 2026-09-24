from __future__ import annotations

import math
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from chemvas.domain.document import Atom


class Point2D(Protocol):
    """Anything with Qt's ``QPointF`` accessors; the feature stays Qt-free."""

    def x(self) -> float: ...
    def y(self) -> float: ...


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


__all__ = ["rotated_atom_positions"]
