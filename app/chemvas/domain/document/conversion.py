"""What the model-to-RDKit conversion hands back for a calculation handoff.

`core.rdkit_conversion` produces these records and the calculation feature
consumes them. They are defined here because the converter serves every
feature and must not depend on one of them, and because the record is a
statement about the document — which generated atom came from which drawn
atom — rather than about any calculation.
"""

from __future__ import annotations

from dataclasses import dataclass


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


__all__ = ["AtomMapEntry", "CalculationArtifacts"]
