from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chemvas.domain.document import MoleculeModel

Point2D = tuple[float, float]


@dataclass(frozen=True, kw_only=True)
class SmilesAtomPlacement:
    source_atom_id: int
    element: str
    x: float
    y: float
    color: str
    explicit_label: bool


@dataclass(frozen=True, kw_only=True)
class SmilesBondPlacement:
    source_bond_id: int
    source_a: int
    source_b: int
    order: int
    style: str
    color: str


@dataclass(frozen=True)
class SmilesMarkPlacement:
    source_atom_id: int
    kind: str
    x: float
    y: float


@dataclass(frozen=True)
class SmilesCommitPlan:
    offset: Point2D
    atoms: list[SmilesAtomPlacement]
    bonds: list[SmilesBondPlacement]
    marks: list[SmilesMarkPlacement] = field(default_factory=list)
    annotations: dict[int, dict[str, int]] = field(default_factory=dict)


def smiles_preview_center(model: MoleculeModel | None) -> Point2D | None:
    if model is None or not model.atoms:
        return None
    left, top, right, bottom = model.bounds()
    return ((left + right) / 2.0, (top + bottom) / 2.0)


def plan_smiles_commit(
    model: MoleculeModel | None,
    preview_center: Point2D | None,
    cursor_pos: Point2D,
) -> SmilesCommitPlan | None:
    if model is None or preview_center is None or not model.atoms:
        return None
    dx, dy = smiles_preview_offset(preview_center, cursor_pos)
    atoms = [
        SmilesAtomPlacement(
            source_atom_id=atom_id,
            element=atom.element,
            x=atom.x + dx,
            y=atom.y + dy,
            color=atom.color,
            explicit_label=atom.explicit_label,
        )
        for atom_id, atom in model.atoms.items()
    ]
    bonds = []
    for bond_id, bond in enumerate(model.bonds):
        if bond is None:
            continue
        if bond.a not in model.atoms or bond.b not in model.atoms:
            return None
        bonds.append(
            SmilesBondPlacement(
                source_bond_id=bond_id,
                source_a=bond.a,
                source_b=bond.b,
                order=bond.order,
                style=bond.style,
                color=bond.color,
            )
        )
    marks = []
    annotations: dict[int, dict[str, int]] = {}
    for atom_id, annotation in model.atom_annotations.items():
        atom = model.atoms.get(atom_id)
        if atom is None:
            continue
        annotation_values = normalized_atom_annotation(annotation)
        if not annotation_values:
            continue
        annotations[atom_id] = annotation_values
        for index, kind in enumerate(annotation_mark_kinds(annotation_values)):
            direction_x, direction_y = annotation_mark_direction(index)
            marks.append(
                SmilesMarkPlacement(
                    source_atom_id=atom_id,
                    kind=kind,
                    x=atom.x + dx + direction_x,
                    y=atom.y + dy + direction_y,
                )
            )
    return SmilesCommitPlan(
        offset=(dx, dy), atoms=atoms, bonds=bonds, marks=marks, annotations=annotations
    )


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


def annotation_mark_direction(index: int) -> Point2D:
    directions = ((1.0, -1.0), (-1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))
    return directions[index % len(directions)]


def smiles_preview_offset(preview_center: Point2D, cursor_pos: Point2D) -> Point2D:
    """The translation that carries the converted model under the cursor.

    The preview ghost is positioned by this offset and the commit plan adds
    it to every atom, so the placed structure lands exactly where the ghost
    was shown.
    """
    return (cursor_pos[0] - preview_center[0], cursor_pos[1] - preview_center[1])


__all__ = [
    "SmilesAtomPlacement",
    "SmilesBondPlacement",
    "SmilesCommitPlan",
    "SmilesMarkPlacement",
    "annotation_mark_direction",
    "annotation_mark_kinds",
    "normalized_atom_annotation",
    "plan_smiles_commit",
    "smiles_preview_center",
    "smiles_preview_offset",
]
