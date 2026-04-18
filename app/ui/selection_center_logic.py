from __future__ import annotations

from collections.abc import Collection, Mapping

from PyQt6.QtCore import QPointF


def center_for_atoms(
    atom_ids: Collection[int],
    *,
    atoms: Mapping[int, object],
) -> QPointF | None:
    xs: list[float] = []
    ys: list[float] = []
    for atom_id in atom_ids:
        atom = atoms.get(atom_id)
        if atom is None:
            continue
        xs.append(atom.x)
        ys.append(atom.y)
    if not xs:
        return None
    return QPointF(sum(xs) / len(xs), sum(ys) / len(ys))


def bounding_box_center_for_atoms(
    atom_ids: Collection[int],
    *,
    atoms: Mapping[int, object],
) -> QPointF | None:
    xs: list[float] = []
    ys: list[float] = []
    for atom_id in atom_ids:
        atom = atoms.get(atom_id)
        if atom is None:
            continue
        xs.append(atom.x)
        ys.append(atom.y)
    if not xs:
        return None
    return QPointF((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


__all__ = ["bounding_box_center_for_atoms", "center_for_atoms"]
