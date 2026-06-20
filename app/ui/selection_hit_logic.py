from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

StructureKind = Literal["atom", "bond", "ring", "other"]
Point2D = tuple[float, float]


@dataclass(frozen=True)
class AtomHitCandidate:
    atom_id: int
    distance: float
    has_visible_label: bool


@dataclass(frozen=True)
class BondHitCandidate:
    bond_id: int
    distance: float


@dataclass(frozen=True)
class StructureHit:
    kind: StructureKind
    id: int | None = None


@dataclass(frozen=True)
class SelectionRect:
    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class SelectionSnapshot:
    selected_atom_ids: frozenset[int]
    selected_bond_ids: frozenset[int]
    selection_items: tuple[object, ...]


@dataclass(frozen=True)
class SelectionHitRequest:
    point: Point2D
    outline_hit: bool
    rects: tuple[SelectionRect, ...]
    pad: float
    hit: StructureHit | None
    selected_atom_ids: frozenset[int]
    selected_bond_ids: frozenset[int]
    bond_atom_ids: tuple[int, int] | None = None
    ring_atom_ids: tuple[int, ...] = ()
    item_is_selected: bool = False


def build_selection_snapshot(
    *,
    selected_atom_ids: Sequence[int],
    selected_bond_ids: Sequence[int],
    selection_items: Sequence[object],
    selected_bond_atom_ids: Sequence[tuple[int, int]] = (),
) -> SelectionSnapshot:
    atom_ids = set(selected_atom_ids)
    for atom_a, atom_b in selected_bond_atom_ids:
        atom_ids.add(atom_a)
        atom_ids.add(atom_b)
    return SelectionSnapshot(
        selected_atom_ids=frozenset(atom_ids),
        selected_bond_ids=frozenset(selected_bond_ids),
        selection_items=tuple(selection_items),
    )


def choose_preferred_structure_hit(
    atom_hit: AtomHitCandidate | None,
    bond_hit: BondHitCandidate | None,
    *,
    atom_pick_radius: float,
    bond_pick_radius: float,
    atom_hard_pick_ratio: float = 0.45,
    bond_tie_factor: float = 1.15,
) -> StructureHit | None:
    atom_score = None
    bond_score = None

    if atom_hit is not None:
        atom_radius = max(atom_pick_radius, 1e-6)
        atom_score = atom_hit.distance / atom_radius
        if atom_hit.distance <= atom_radius * atom_hard_pick_ratio:
            return StructureHit(kind="atom", id=atom_hit.atom_id)

    if bond_hit is not None:
        bond_score = bond_hit.distance / max(bond_pick_radius, 1e-6)

    if atom_hit is not None and bond_hit is not None and atom_score is not None and bond_score is not None:
        if bond_score <= atom_score * bond_tie_factor:
            return StructureHit(kind="bond", id=bond_hit.bond_id)
        return StructureHit(kind="atom", id=atom_hit.atom_id)
    if bond_hit is not None:
        return StructureHit(kind="bond", id=bond_hit.bond_id)
    if atom_hit is not None:
        return StructureHit(kind="atom", id=atom_hit.atom_id)
    return None


def nearest_ring_atom_id(
    atom_distances: Sequence[tuple[int, float]],
    *,
    max_distance: float,
) -> int | None:
    nearest_atom_id = None
    nearest_distance = max_distance
    for atom_id, distance in atom_distances:
        if distance <= nearest_distance:
            nearest_atom_id = atom_id
            nearest_distance = distance
    return nearest_atom_id


def structure_hit_is_selected(
    hit: StructureHit | None,
    *,
    selected_atom_ids: set[int],
    selected_bond_ids: set[int],
    bond_atom_ids: tuple[int, int] | None = None,
    ring_atom_ids: Sequence[int] | None = None,
    item_is_selected: bool = False,
) -> bool:
    if hit is None:
        return False
    if hit.kind == "atom":
        return hit.id in selected_atom_ids
    if hit.kind == "bond":
        if hit.id in selected_bond_ids:
            return True
        if bond_atom_ids is None:
            return False
        atom_a, atom_b = bond_atom_ids
        return atom_a in selected_atom_ids or atom_b in selected_atom_ids
    if hit.kind == "ring":
        if ring_atom_ids is None:
            return False
        return any(atom_id in selected_atom_ids for atom_id in ring_atom_ids)
    return item_is_selected


def padded_rect_contains_point(
    rect: SelectionRect,
    point: Point2D,
    *,
    pad: float,
) -> bool:
    x, y = point
    return (
        rect.left - pad <= x <= rect.right + pad
        and rect.top - pad <= y <= rect.bottom + pad
    )


def selection_hit_matches(request: SelectionHitRequest) -> bool:
    if request.outline_hit:
        return True
    if any(padded_rect_contains_point(rect, request.point, pad=request.pad) for rect in request.rects):
        return True
    return structure_hit_is_selected(
        request.hit,
        selected_atom_ids=set(request.selected_atom_ids),
        selected_bond_ids=set(request.selected_bond_ids),
        bond_atom_ids=request.bond_atom_ids,
        ring_atom_ids=request.ring_atom_ids,
        item_is_selected=request.item_is_selected,
    )


__all__ = [
    "AtomHitCandidate",
    "BondHitCandidate",
    "SelectionHitRequest",
    "SelectionRect",
    "SelectionSnapshot",
    "StructureHit",
    "build_selection_snapshot",
    "choose_preferred_structure_hit",
    "nearest_ring_atom_id",
    "padded_rect_contains_point",
    "selection_hit_matches",
    "structure_hit_is_selected",
]
