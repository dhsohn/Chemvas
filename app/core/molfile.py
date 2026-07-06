from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence

from core.model import Bond, MoleculeModel

# Element symbols (Z = 1..118). An atom whose stored label is not one of these
# (an abbreviation such as Me/Ph/OH, or a multi-atom label) cannot be written as
# a single MDL atom, so MOL export fails loudly instead of guessing.
_ELEMENTS = frozenset(
    """
    H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni
    Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe
    Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg
    Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg
    Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og
    """.split()
)

# MDL bond stereo flags for single bonds drawn with a wedge/hash style.
_STEREO_BY_STYLE = {"wedge": 1, "hash": 6}

# Target average bond length (in MDL coordinate units) used to normalise the
# canvas's scene coordinates so emitted depictions look conventional.
_TARGET_BOND_LENGTH = 1.5

# V2000 counts-line fields are 3 characters wide; exceeding them would shift
# the fixed-width columns and silently corrupt the file for every parser.
_V2000_MAX_ATOMS = 999
_V2000_MAX_BONDS = 999

# MDL "M  CHG" charge values are defined for -15..+15 only.
_MDL_MIN_CHARGE = -15
_MDL_MAX_CHARGE = 15


class MolfileError(ValueError):
    """Raised when a model cannot be represented as an MDL Molfile."""


def write_molfile(
    model: MoleculeModel,
    *,
    atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    title: str = "",
) -> str:
    """Serialise ``model`` as an MDL Molfile (V2000) block.

    The drawn 2D coordinates, bond orders, and wedge/hash stereo are preserved.
    Formal charges and radicals are read from ``atom_annotations`` (the same
    per-atom mapping the 3D export uses). RDKit is not required.
    """
    atom_ids = sorted(model.atoms)
    _reject_non_element_labels(model, atom_ids)

    index_by_id = {atom_id: position for position, atom_id in enumerate(atom_ids, start=1)}
    bonds = [
        bond
        for bond in model.bonds
        if bond is not None and bond.a in index_by_id and bond.b in index_by_id
    ]
    if len(atom_ids) > _V2000_MAX_ATOMS or len(bonds) > _V2000_MAX_BONDS:
        raise MolfileError(
            "Cannot export to MOL: V2000 molfiles support at most "
            f"{_V2000_MAX_ATOMS} atoms and {_V2000_MAX_BONDS} bonds "
            f"(this drawing has {len(atom_ids)} atoms and {len(bonds)} bonds). "
            "Export a smaller selection instead."
        )
    scale = _coordinate_scale(model, bonds)
    annotations = atom_annotations or {}

    lines: list[str] = [title, "  Chemvas", ""]
    lines.append(f"{len(atom_ids):>3}{len(bonds):>3}  0  0  0  0  0  0  0  0999 V2000")
    for atom_id in atom_ids:
        atom = model.atoms[atom_id]
        # Canvas y grows downward; MDL y grows upward, so negate it.
        lines.append(_atom_line(atom.x * scale, -atom.y * scale, atom.element))
    for bond in bonds:
        lines.append(_bond_line(index_by_id[bond.a], index_by_id[bond.b], bond))
    lines.extend(_property_lines("CHG", _charges(annotations, index_by_id)))
    lines.extend(_property_lines("RAD", _radicals(annotations, index_by_id)))
    lines.append("M  END")
    return "\n".join(lines) + "\n"


def _reject_non_element_labels(model: MoleculeModel, atom_ids: Sequence[int]) -> None:
    unsupported = sorted({model.atoms[atom_id].element for atom_id in atom_ids} - _ELEMENTS)
    if unsupported:
        raise MolfileError(
            "Cannot export these atom labels to MOL: "
            + ", ".join(unsupported)
            + ". Replace them with explicit element atoms first."
        )


def _coordinate_scale(model: MoleculeModel, bonds: Sequence[Bond]) -> float:
    lengths = []
    for bond in bonds:
        a = model.atoms[bond.a]
        b = model.atoms[bond.b]
        distance = math.hypot(a.x - b.x, a.y - b.y)
        if distance > 0.0:
            lengths.append(distance)
    if not lengths:
        return 1.0
    average = sum(lengths) / len(lengths)
    return _TARGET_BOND_LENGTH / average if average > 0.0 else 1.0


def _atom_line(x: float, y: float, element: str) -> str:
    return f"{x:>10.4f}{y:>10.4f}{0.0:>10.4f} {element:<3}{0:>2}" + "  0" * 11


def _bond_line(begin: int, end: int, bond: Bond) -> str:
    order = bond.order if bond.order in (1, 2, 3) else 1
    stereo = _STEREO_BY_STYLE.get(bond.style, 0)
    return f"{begin:>3}{end:>3}{order:>3}{stereo:>3}  0  0  0"


def _charges(
    annotations: Mapping[int, Mapping[str, int]],
    index_by_id: Mapping[int, int],
) -> list[tuple[int, int]]:
    entries = []
    for atom_id, values in annotations.items():
        charge = int(values.get("formal_charge", 0))
        if charge == 0 or atom_id not in index_by_id:
            continue
        if not _MDL_MIN_CHARGE <= charge <= _MDL_MAX_CHARGE:
            raise MolfileError(
                f"Cannot export to MOL: formal charge {charge:+d} is outside "
                f"the MDL range {_MDL_MIN_CHARGE}..{_MDL_MAX_CHARGE:+d}."
            )
        entries.append((index_by_id[atom_id], charge))
    return sorted(entries)


def _radicals(
    annotations: Mapping[int, Mapping[str, int]],
    index_by_id: Mapping[int, int],
) -> list[tuple[int, int]]:
    entries = []
    for atom_id, values in annotations.items():
        electrons = int(values.get("radical_electrons", 0))
        if electrons > 0 and atom_id in index_by_id:
            # MDL radical codes: 1 singlet, 2 doublet, 3 triplet.
            entries.append((index_by_id[atom_id], 3 if electrons >= 2 else 2))
    return sorted(entries)


def _property_lines(tag: str, entries: Sequence[tuple[int, int]]) -> list[str]:
    lines = []
    for chunk in _chunked(entries, 8):
        body = "".join(f"{index:>4}{value:>4}" for index, value in chunk)
        lines.append(f"M  {tag}{len(chunk):>3}{body}")
    return lines


def _chunked[T](items: Sequence[T], size: int) -> Iterable[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


__all__ = ["MolfileError", "write_molfile"]
