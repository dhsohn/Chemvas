"""The periodic table's element symbols, shared by every chemistry format.

Formats keep their own label policy (aliases, ambiguous symbols, generic
nicknames); this module only says which symbols are elements and their
atomic numbers.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

# Element symbols in atomic-number order (Z = 1..118).
ELEMENT_SYMBOLS: Final[tuple[str, ...]] = tuple(
    """
    H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni
    Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe
    Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg
    Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg
    Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og
    """.split()
)

ATOMIC_NUMBERS: Final[Mapping[str, int]] = MappingProxyType(
    {symbol: z for z, symbol in enumerate(ELEMENT_SYMBOLS, start=1)}
)


def element_symbol(atomic_number: int) -> str | None:
    """The symbol for ``atomic_number``, or None outside 1..118."""
    if 0 < atomic_number <= len(ELEMENT_SYMBOLS):
        return ELEMENT_SYMBOLS[atomic_number - 1]
    return None


__all__ = ["ATOMIC_NUMBERS", "ELEMENT_SYMBOLS", "element_symbol"]
