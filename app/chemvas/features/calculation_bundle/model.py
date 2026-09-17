from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chemvas.domain.document import AtomMapEntry, CalculationArtifacts

if TYPE_CHECKING:
    from chemvas.domain.document import MoleculeModel


@dataclass(frozen=True)
class CalculationStateSelection:
    model: MoleculeModel
    component_indices: tuple[int, ...]
    atom_ids: tuple[int, ...]
    formal_charge: int
    radical_electrons: int


__all__ = [
    "AtomMapEntry",
    "CalculationArtifacts",
    "CalculationStateSelection",
]
