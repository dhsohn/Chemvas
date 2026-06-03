from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from core.model import Atom, Bond
from PyQt6.QtCore import QPointF


@dataclass(frozen=True)
class BondPlacementContext:
    bond_id: int
    atom_a_id: int
    atom_b_id: int
    midpoint: QPointF


def fused_benzene_centers(center: QPointF, step: float, count: int, mode: str = "linear") -> list[QPointF]:
    if count == 2:
        return [
            QPointF(center.x() - step / 2.0, center.y()),
            QPointF(center.x() + step / 2.0, center.y()),
        ]
    if mode == "angled":
        return [
            QPointF(center.x() - step, center.y()),
            QPointF(center.x(), center.y()),
            QPointF(center.x() + step * 0.6, center.y() + step * 0.6),
        ]
    return [
        QPointF(center.x() - step, center.y()),
        QPointF(center.x(), center.y()),
        QPointF(center.x() + step, center.y()),
    ]


def crown_ether_elements(atoms: int, oxygens: int) -> list[str]:
    elements = ["C"] * atoms
    step = atoms // oxygens
    for index in range(0, atoms, step):
        elements[index] = "O"
    return elements


def other_atom_id_from_bond_result(anchor_atom_id: int, bond_result: tuple[int, int] | None) -> int | None:
    if bond_result is None:
        return None
    atom_a_id, atom_b_id = bond_result
    if atom_a_id == anchor_atom_id:
        return atom_b_id
    if atom_b_id == anchor_atom_id:
        return atom_a_id
    return None


def resolve_bond_placement_context(
    bond_id: int,
    *,
    bonds: Sequence[Bond | None],
    atoms: Mapping[int, Atom],
) -> BondPlacementContext | None:
    if not (0 <= bond_id < len(bonds)):
        return None
    bond = bonds[bond_id]
    if bond is None:
        return None
    atom_a = atoms.get(bond.a)
    atom_b = atoms.get(bond.b)
    if atom_a is None or atom_b is None:
        return None
    return BondPlacementContext(
        bond_id=bond_id,
        atom_a_id=bond.a,
        atom_b_id=bond.b,
        midpoint=QPointF((atom_a.x + atom_b.x) / 2.0, (atom_a.y + atom_b.y) / 2.0),
    )


def mirrored_local_points(points: Sequence[QPointF], mirrored: bool) -> list[QPointF]:
    if not mirrored:
        return [QPointF(point) for point in points]
    return [QPointF(point.x(), -point.y()) for point in points]


def alternating_ring_bond_specs(atom_ids: Sequence[int]) -> list[tuple[int, int, int]]:
    specs: list[tuple[int, int, int]] = []
    for index, atom_a_id in enumerate(atom_ids):
        atom_b_id = atom_ids[(index + 1) % len(atom_ids)]
        specs.append((atom_a_id, atom_b_id, 2 if index % 2 == 0 else 1))
    return specs


__all__ = [
    "BondPlacementContext",
    "alternating_ring_bond_specs",
    "crown_ether_elements",
    "fused_benzene_centers",
    "mirrored_local_points",
    "other_atom_id_from_bond_result",
    "resolve_bond_placement_context",
]
