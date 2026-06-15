from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence

from core.model import Atom, Bond
from PyQt6.QtCore import QPointF


def selected_rotation_atom_ids(
    atom_ids: Iterable[int],
    bond_ids: Iterable[int],
    *,
    bonds: Sequence[Bond | None],
) -> set[int]:
    expanded = set(atom_ids)
    for bond_id in bond_ids:
        if not (0 <= bond_id < len(bonds)):
            continue
        bond = bonds[bond_id]
        if bond is None:
            continue
        expanded.add(bond.a)
        expanded.add(bond.b)
    return expanded


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


__all__ = ["rotated_atom_positions", "selected_rotation_atom_ids"]
