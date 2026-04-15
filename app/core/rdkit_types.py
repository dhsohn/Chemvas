from __future__ import annotations

from dataclasses import dataclass


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


__all__ = ["Molecule3DAtom", "Molecule3DBond", "Molecule3DScene"]
