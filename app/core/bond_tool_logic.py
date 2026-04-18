from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BondSnapTarget:
    pos: tuple[float, float]
    start_atom_id: int | None


def resolve_bond_press_target(
    *,
    atom_id: int | None,
    item_kind: str | None,
    item_bond_id,
    nearby_bond_id,
    hover_bond_id,
) -> int | None:
    if atom_id is not None:
        return None
    if item_kind == "bond" and isinstance(item_bond_id, int):
        return item_bond_id
    if isinstance(nearby_bond_id, int):
        return nearby_bond_id
    if isinstance(hover_bond_id, int):
        return hover_bond_id
    return None


def resolve_bond_snap_target(
    model,
    *,
    pos: tuple[float, float],
    atom_id: int | None,
    bond_id: int | None,
    start_atom_id: int | None,
    ignore_start: bool,
) -> BondSnapTarget:
    if atom_id is not None:
        if ignore_start and atom_id == start_atom_id:
            return BondSnapTarget(pos=pos, start_atom_id=start_atom_id)
        atom = model.atoms.get(atom_id)
        if atom is None:
            return BondSnapTarget(pos=pos, start_atom_id=start_atom_id)
        return BondSnapTarget(
            pos=(atom.x, atom.y),
            start_atom_id=start_atom_id if ignore_start else atom_id,
        )

    if bond_id is None or not (0 <= bond_id < len(model.bonds)):
        return BondSnapTarget(pos=pos, start_atom_id=start_atom_id)

    bond = model.bonds[bond_id]
    if bond is None:
        return BondSnapTarget(pos=pos, start_atom_id=start_atom_id)

    atom_a = model.atoms.get(bond.a)
    atom_b = model.atoms.get(bond.b)
    if atom_a is None or atom_b is None:
        return BondSnapTarget(pos=pos, start_atom_id=start_atom_id)

    x, y = pos
    da = (x - atom_a.x) ** 2 + (y - atom_a.y) ** 2
    db = (x - atom_b.x) ** 2 + (y - atom_b.y) ** 2
    target = atom_a if da <= db else atom_b
    return BondSnapTarget(pos=(target.x, target.y), start_atom_id=start_atom_id)


def resolve_bond_endpoint_target(
    model,
    *,
    start: tuple[float, float],
    end: tuple[float, float],
    atom_id: int | None,
    start_atom_id: int | None,
    snap_angle_step: int | float | None,
    bond_length: float,
) -> tuple[float, float]:
    if atom_id is not None and atom_id != start_atom_id:
        atom = model.atoms.get(atom_id)
        if atom is not None:
            return (atom.x, atom.y)

    start_x, start_y = start
    end_x, end_y = end
    dx = end_x - start_x
    dy = end_y - start_y
    length = (dx**2 + dy**2) ** 0.5
    if length == 0:
        return end

    angle = math.degrees(math.atan2(dy, dx))
    step = snap_angle_step or 30
    snap_angle = round(angle / step) * step
    rad = math.radians(snap_angle)
    return (
        start_x + math.cos(rad) * bond_length,
        start_y + math.sin(rad) * bond_length,
    )


__all__ = [
    "BondSnapTarget",
    "resolve_bond_endpoint_target",
    "resolve_bond_press_target",
    "resolve_bond_snap_target",
]
