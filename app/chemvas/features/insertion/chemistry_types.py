from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RDKitResult[T]:
    value: T | None
    error: str | None = None


@dataclass(frozen=True)
class Molecule3DAtom:
    symbol: str
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class Molecule3DBond:
    a: int
    b: int
    order: int


@dataclass(frozen=True)
class Molecule3DScene:
    atoms: tuple[Molecule3DAtom, ...]
    bonds: tuple[Molecule3DBond, ...]


@dataclass(frozen=True)
class MoleculeIdentifiers:
    formula: str | None = None
    mw: float | None = None
    smiles: str | None = None
    inchi: str | None = None
    inchikey: str | None = None


__all__ = [
    "Molecule3DAtom",
    "Molecule3DBond",
    "Molecule3DScene",
    "MoleculeIdentifiers",
    "RDKitResult",
]
