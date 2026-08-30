from __future__ import annotations

from dataclasses import dataclass

from chemvas.domain.document.precomplex_profile import (
    CURRENT_PROFILE_ID,
    precomplex_placement_profile,
)

Vector3 = tuple[float, float, float]


@dataclass(frozen=True, kw_only=True)
class GeometryAtom:
    path_index: int
    symbol: str
    source_atom_id: int | None
    parent_source_atom_id: int | None
    origin: str
    coordinates: Vector3


@dataclass(frozen=True)
class ComponentGeometry:
    component_atom_ids: tuple[int, ...]
    conformer_id: str
    atoms: tuple[GeometryAtom, ...]
    profile: str = CURRENT_PROFILE_ID


@dataclass(frozen=True)
class ContactRequest:
    id: str
    first_atom_id: int
    second_atom_id: int
    target_distance_angstrom: float
    tolerance_angstrom: float


@dataclass(frozen=True, kw_only=True)
class PlacementRequest:
    source_sha256: str
    plan_sha256: str
    step_id: str
    side: str
    contacts: tuple[ContactRequest, ...]
    candidate_cap: int = precomplex_placement_profile(CURRENT_PROFILE_ID).max_candidates
    profile: str = CURRENT_PROFILE_ID


@dataclass(frozen=True, kw_only=True)
class ValidationMetrics:
    hard_clash_count: int
    soft_overlap_score: float
    contact_error_angstrom: float
    limiting_pair: tuple[int, int] | None
    limiting_distance_angstrom: float | None
    limiting_threshold_angstrom: float | None


@dataclass(frozen=True)
class CandidateTransform:
    approach_index: int
    rotation_index: int
    approach_vector: Vector3


@dataclass(frozen=True, kw_only=True)
class GeneratedCandidate:
    id: str
    geometry_class: str
    profile: str
    atoms: tuple[GeometryAtom, ...]
    xyz: str
    xyz_sha256: str
    transform: CandidateTransform
    component_conformer_ids: tuple[str, ...]
    validation: ValidationMetrics


__all__ = [
    "CandidateTransform",
    "ComponentGeometry",
    "ContactRequest",
    "GeneratedCandidate",
    "GeometryAtom",
    "PlacementRequest",
    "ValidationMetrics",
    "Vector3",
]
