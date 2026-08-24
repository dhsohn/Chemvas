from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

from PyQt6.QtCore import QPointF

from chemvas.domain.document import Atom


def rotated_atom_positions(
    atom_ids: Iterable[int],
    *,
    atoms: Mapping[int, Atom],
    center: QPointF,
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
