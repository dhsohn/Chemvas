from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from chemvas.domain.document import MoleculeModel

Point2D = tuple[float, float]
LineSegment = tuple[float, float, float, float]
Rect = tuple[float, float, float, float]
SmilesPreviewAction = Literal["clear", "rebuild", "update"]


@dataclass(frozen=True)
class SmilesAtomPlacement:
    source_atom_id: int
    element: str
    x: float
    y: float
    color: str
    explicit_label: bool


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class SmilesPreviewSnapshot:
    bond_segment_counts: dict[int, int]
    atom_ids: tuple[int, ...]


@dataclass(frozen=True)
class SmilesPreviewGeometry:
    bond_segments: dict[int, tuple[LineSegment, ...]]
    atom_rects: dict[int, Rect]


@dataclass(frozen=True)
class SmilesPreviewPlan:
    action: SmilesPreviewAction
    geometry: SmilesPreviewGeometry | None = None


@dataclass(frozen=True)
class SmilesPreviewResolvers:
    parallel_bond_segments: Callable[
        [float, float, float, float, int], Sequence[LineSegment]
    ]


def build_smiles_preview_snapshot(
    bond_segment_counts: Mapping[int, int],
    atom_ids: Iterable[int],
) -> SmilesPreviewSnapshot:
    return SmilesPreviewSnapshot(
        bond_segment_counts={
            bond_id: count for bond_id, count in bond_segment_counts.items()
        },
        atom_ids=tuple(atom_ids),
    )


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
    dx, dy = _offset(preview_center, cursor_pos)
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
    atom_annotations = getattr(model, "atom_annotations", {})
    for atom_id, annotation in atom_annotations.items():
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


def build_smiles_preview_geometry(
    model: MoleculeModel | None,
    preview_center: Point2D | None,
    cursor_pos: Point2D,
    atom_radius: float | None,
    resolvers: SmilesPreviewResolvers,
) -> SmilesPreviewGeometry | None:
    if (
        model is None
        or preview_center is None
        or atom_radius is None
        or atom_radius <= 0.0
        or not model.atoms
    ):
        return None
    dx, dy = _offset(preview_center, cursor_pos)
    bond_segments: dict[int, tuple[LineSegment, ...]] = {}
    for bond_id, bond in enumerate(model.bonds):
        if bond is None:
            continue
        atom_a = model.atoms.get(bond.a)
        atom_b = model.atoms.get(bond.b)
        if atom_a is None or atom_b is None:
            return None
        x1 = atom_a.x + dx
        y1 = atom_a.y + dy
        x2 = atom_b.x + dx
        y2 = atom_b.y + dy
        if bond.order <= 1:
            bond_segments[bond_id] = ((x1, y1, x2, y2),)
        else:
            segments = tuple(
                resolvers.parallel_bond_segments(x1, y1, x2, y2, bond.order)
            )
            if not segments:
                return None
            bond_segments[bond_id] = segments
    atom_rects = {
        atom_id: (
            atom.x + dx - atom_radius,
            atom.y + dy - atom_radius,
            atom_radius * 2.0,
            atom_radius * 2.0,
        )
        for atom_id, atom in model.atoms.items()
    }
    return SmilesPreviewGeometry(bond_segments=bond_segments, atom_rects=atom_rects)


def snapshot_smiles_preview_geometry(
    geometry: SmilesPreviewGeometry,
) -> SmilesPreviewSnapshot:
    return build_smiles_preview_snapshot(
        {
            bond_id: len(segments)
            for bond_id, segments in geometry.bond_segments.items()
        },
        geometry.atom_rects.keys(),
    )


def plan_smiles_preview_update(
    model: MoleculeModel | None,
    preview_center: Point2D | None,
    cursor_pos: Point2D,
    atom_radius: float | None,
    existing: SmilesPreviewSnapshot,
    resolvers: SmilesPreviewResolvers,
) -> SmilesPreviewPlan:
    geometry = build_smiles_preview_geometry(
        model, preview_center, cursor_pos, atom_radius, resolvers
    )
    if geometry is None:
        return SmilesPreviewPlan(action="clear")
    if snapshot_smiles_preview_geometry(geometry) != existing:
        return SmilesPreviewPlan(action="rebuild", geometry=geometry)
    return SmilesPreviewPlan(action="update", geometry=geometry)


def _offset(preview_center: Point2D, cursor_pos: Point2D) -> Point2D:
    return (cursor_pos[0] - preview_center[0], cursor_pos[1] - preview_center[1])


__all__ = [
    "SmilesAtomPlacement",
    "SmilesBondPlacement",
    "SmilesCommitPlan",
    "SmilesMarkPlacement",
    "SmilesPreviewGeometry",
    "SmilesPreviewPlan",
    "SmilesPreviewResolvers",
    "SmilesPreviewSnapshot",
    "annotation_mark_direction",
    "annotation_mark_kinds",
    "build_smiles_preview_geometry",
    "build_smiles_preview_snapshot",
    "normalized_atom_annotation",
    "plan_smiles_commit",
    "plan_smiles_preview_update",
    "smiles_preview_center",
    "snapshot_smiles_preview_geometry",
]
