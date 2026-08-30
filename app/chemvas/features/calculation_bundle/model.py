from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemvas.domain.document import MoleculeModel


@dataclass(frozen=True, kw_only=True)
class ComponentSummary:
    index: int
    atom_ids: tuple[int, ...]
    bond_count: int
    formula_labels: tuple[tuple[str, int], ...]
    formal_charge: int
    radical_electrons: int
    bounds: tuple[float, float, float, float]


@dataclass(frozen=True)
class ComponentSelection:
    model: MoleculeModel
    summary: ComponentSummary


@dataclass(frozen=True)
class CalculationStateSelection:
    model: MoleculeModel
    component_indices: tuple[int, ...]
    atom_ids: tuple[int, ...]
    formal_charge: int
    radical_electrons: int


@dataclass(frozen=True, kw_only=True)
class AtomMapEntry:
    xyz_index: int
    mol_index: int | None
    symbol: str
    origin: str
    chemvas_atom_id: int | None
    parent_xyz_index: int | None = None
    parent_chemvas_atom_id: int | None = None


@dataclass(frozen=True, kw_only=True)
class CalculationArtifacts:
    mol_block: str
    xyz_block: str
    atom_map: tuple[AtomMapEntry, ...]
    rdkit_version: str
    rdkit_formal_charge: int
    rdkit_radical_electrons: int
    electron_count: int
    geometry_embedding: str
    geometry_random_seed: int
    geometry_optimization_policy: str
    geometry_optimization_result: str
    mol_atom_count: int
    xyz_atom_count: int


__all__ = [
    "AtomMapEntry",
    "CalculationArtifacts",
    "CalculationStateSelection",
    "ComponentSelection",
    "ComponentSummary",
]
