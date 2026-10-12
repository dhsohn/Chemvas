from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chemvas.domain.document import MoleculeModel

Point2D = tuple[float, float]


def normalized_atom_annotation(annotation: Mapping[str, int]) -> dict[str, int]:
    values: dict[str, int] = {}
    formal_charge = annotation.get("formal_charge", 0)
    if type(formal_charge) is int and formal_charge:
        values["formal_charge"] = formal_charge
    radical_electrons = annotation.get("radical_electrons", 0)
    if type(radical_electrons) is int and radical_electrons > 0:
        values["radical_electrons"] = radical_electrons
    return values


def annotation_mark_kinds(annotation: Mapping[str, int]) -> tuple[str, ...]:
    kinds: list[str] = []
    formal_charge = int(annotation.get("formal_charge", 0))
    radical_electrons = int(annotation.get("radical_electrons", 0))
    if formal_charge > 0:
        kinds.extend("plus" for _ in range(formal_charge))
    elif formal_charge < 0:
        kinds.extend("minus" for _ in range(abs(formal_charge)))
    if radical_electrons > 0:
        kinds.extend("radical" for _ in range(radical_electrons))
    return tuple(kinds)


def annotation_mark_direction(
    index: int, *, model: MoleculeModel, atom_id: int
) -> Point2D:
    """Choose a new annotation's compass direction away from incident bonds.

    This is a deterministic initial-placement heuristic, not a layout repair:
    saved offsets and manually positioned marks are never passed through it.
    All directions retain the old diagonal's length so headless composition
    and label-aware desktop placement use the same angular choice.
    """
    root_two = math.sqrt(2.0)
    candidates = [
        (1.0, -1.0),
        (-1.0, -1.0),
        (1.0, 1.0),
        (-1.0, 1.0),
        (0.0, -root_two),
        (0.0, root_two),
        (root_two, 0.0),
        (-root_two, 0.0),
    ]
    atom = model.atoms[atom_id]
    occupied = []
    for bond in model.bonds:
        if bond is None or atom_id not in (bond.a, bond.b):
            continue
        neighbor = model.atoms.get(bond.b if bond.a == atom_id else bond.a)
        if neighbor is None:
            continue
        dx, dy = neighbor.x - atom.x, neighbor.y - atom.y
        length = math.hypot(dx, dy)
        if length > 0.0:
            occupied.append((dx / length, dy / length))

    def clearance(direction: Point2D) -> float:
        # Maximizing angular separation is equivalent to minimizing the
        # largest dot product. Round only the comparison for stable ties.
        return round(
            min(
                (
                    1.0 - (direction[0] * x + direction[1] * y) / root_two
                    for x, y in occupied
                ),
                default=2.0,
            ),
            12,
        )

    selected = candidates[0]
    for _ in range(index % len(candidates) + 1):
        selected = max(candidates, key=clearance)
        candidates.remove(selected)
        occupied.append((selected[0] / root_two, selected[1] / root_two))
    return selected


__all__ = [
    "annotation_mark_direction",
    "annotation_mark_kinds",
    "normalized_atom_annotation",
]
