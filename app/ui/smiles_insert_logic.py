from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from core.model import MoleculeModel

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
class SmilesCommitPlan:
    offset: Point2D
    atoms: list[SmilesAtomPlacement]
    bonds: list[SmilesBondPlacement]


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
    parallel_bond_segments: Callable[[float, float, float, float, int], Sequence[LineSegment]]


def build_smiles_preview_snapshot(
    bond_segment_counts: Mapping[int, int],
    atom_ids: Iterable[int],
) -> SmilesPreviewSnapshot:
    return SmilesPreviewSnapshot(
        bond_segment_counts={bond_id: count for bond_id, count in bond_segment_counts.items()},
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
    return SmilesCommitPlan(offset=(dx, dy), atoms=atoms, bonds=bonds)


def build_smiles_preview_geometry(
    model: MoleculeModel | None,
    preview_center: Point2D | None,
    cursor_pos: Point2D,
    atom_radius: float | None,
    resolvers: SmilesPreviewResolvers,
) -> SmilesPreviewGeometry | None:
    if model is None or preview_center is None or atom_radius is None or atom_radius <= 0.0 or not model.atoms:
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
            segments = tuple(resolvers.parallel_bond_segments(x1, y1, x2, y2, bond.order))
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


def snapshot_smiles_preview_geometry(geometry: SmilesPreviewGeometry) -> SmilesPreviewSnapshot:
    return build_smiles_preview_snapshot(
        {bond_id: len(segments) for bond_id, segments in geometry.bond_segments.items()},
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
    geometry = build_smiles_preview_geometry(model, preview_center, cursor_pos, atom_radius, resolvers)
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
    "SmilesPreviewGeometry",
    "SmilesPreviewPlan",
    "SmilesPreviewResolvers",
    "SmilesPreviewSnapshot",
    "build_smiles_preview_geometry",
    "build_smiles_preview_snapshot",
    "plan_smiles_commit",
    "plan_smiles_preview_update",
    "smiles_preview_center",
    "snapshot_smiles_preview_geometry",
]
