"""Conservative editor warnings for ordinary, explicitly drawn bonds.

This is a drawing aid, not a chemical validity gate. Aliases, radicals,
unsupported charge states, hypervalent elements and partial bonds are unassessed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemvas.domain.document import MoleculeModel

_LIMITS = {
    "H": {0: 1},
    "B": {0: 3, -1: 4},
    "C": {0: 4, -1: 3, 1: 3},
    "N": {0: 3, -1: 2, 1: 4},
    "O": {0: 2, -1: 1, 1: 3},
    "F": {0: 1, -1: 0},
}
_COVALENT_NEIGHBORS = frozenset(
    {"H", "B", "C", "N", "O", "F", "Si", "P", "S", "Cl", "Ge", "As", "Se", "Br", "I"}
)


def overvalent_atom_ids(model: MoleculeModel) -> set[int]:
    totals = dict.fromkeys(model.atoms, 0)
    partial: set[int] = set()
    for bond in model.bonds:
        if bond is None:
            continue
        if "dotted" in bond.style or any(
            model.atoms[atom_id].element not in _COVALENT_NEIGHBORS
            for atom_id in (bond.a, bond.b)
            if atom_id in model.atoms
        ):
            partial.update((bond.a, bond.b))
        for atom_id in (bond.a, bond.b):
            if atom_id in totals:
                totals[atom_id] += bond.order
    warnings = set()
    for atom_id, atom in model.atoms.items():
        annotation = model.atom_annotations.get(atom_id, {})
        if atom_id in partial or annotation.get("radical_electrons", 0):
            continue
        limit = _LIMITS.get(atom.element, {}).get(annotation.get("formal_charge", 0))
        if limit is not None and totals[atom_id] > limit:
            warnings.add(atom_id)
    return warnings
