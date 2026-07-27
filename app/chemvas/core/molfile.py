from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence

from chemvas.domain.document import Bond, MoleculeModel

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

# Import-side inverses. A plain bond takes the canvas style that matches its
# order; stereo flags 1/6 map back to the wedge/hash styles the writer encodes.
_STYLE_BY_STEREO = {stereo: style for style, stereo in _STEREO_BY_STYLE.items()}
_STYLE_BY_ORDER = {1: "single", 2: "double", 3: "triple"}

# MDL radical codes -> unpaired electron counts. Code 1 is a singlet and cannot
# be represented by the current annotation model without losing multiplicity.
_RADICAL_ELECTRONS_BY_CODE = {2: 1, 3: 2}

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

# Fixed-width atom-block fields after the element symbol. The current reader
# does not implement any of them; accepting a non-zero value would silently
# discard chemical or stereochemical data. Blank/missing optional fields and
# the all-zero form emitted by our writer remain accepted.
_UNSUPPORTED_ATOM_FIELDS = (
    (34, 36, "mass-difference field"),
    (36, 39, "atom-block charge code"),
    (39, 42, "atom stereo parity"),
    (42, 45, "hydrogen-count field"),
    (45, 48, "stereo-care field"),
    (48, 51, "valence field"),
    (51, 54, "H0-designator field"),
    (54, 57, "reserved atom field"),
    (57, 60, "reserved atom field"),
    (60, 63, "atom-mapping field"),
    (63, 66, "inversion/retention field"),
    (66, 69, "exact-change field"),
)

_UNSUPPORTED_COUNTS_FIELDS = (
    (6, 9, "atom-list count"),
    (9, 12, "obsolete counts field"),
    (12, 15, "chiral flag"),
    (15, 18, "stext-entry count"),
    (18, 21, "obsolete counts field"),
    (21, 24, "obsolete counts field"),
    (24, 27, "obsolete counts field"),
    (27, 30, "obsolete counts field"),
)

_UNSUPPORTED_BOND_FIELDS = (
    (12, 15, "reserved bond field"),
    (15, 18, "bond topology"),
    (18, 21, "reacting-center status"),
)


class MolfileError(ValueError):
    """Raised when a model cannot be represented as, or read back from, an
    MDL Molfile."""


class MolfileParseError(MolfileError):
    """Raised when MOL text cannot be read as the V2000 subset Chemvas writes.

    The parser is deliberately fail-closed: anything outside the constructs
    :func:`write_molfile` emits (V3000 files, unknown element symbols,
    3D coordinates, unsupported property lines, malformed fields) raises this
    error with a specific message instead of guessing.
    """


class MolfileLimitError(MolfileError):
    """Raised for hard V2000 capacity/range limits.

    Unlike plain :class:`MolfileError` (e.g. abbreviation labels, which an
    RDKit fallback can expand), these limits hold for any V2000 writer, so
    callers must surface them instead of retrying through a fallback.
    """


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
    index_by_id = {
        atom_id: position for position, atom_id in enumerate(atom_ids, start=1)
    }
    bonds = [
        bond
        for bond in model.bonds
        if bond is not None and bond.a in index_by_id and bond.b in index_by_id
    ]
    # Capacity limits come before alias rejection: a too-large drawing must
    # raise MolfileLimitError even when it also contains abbreviation labels,
    # or the caller's RDKit expansion fallback would swallow the hard limit.
    if len(atom_ids) > _V2000_MAX_ATOMS or len(bonds) > _V2000_MAX_BONDS:
        raise MolfileLimitError(
            "Cannot export to MOL: V2000 molfiles support at most "
            f"{_V2000_MAX_ATOMS} atoms and {_V2000_MAX_BONDS} bonds "
            f"(this drawing has {len(atom_ids)} atoms and {len(bonds)} bonds). "
            "Export a smaller selection instead."
        )
    _reject_non_element_labels(model, atom_ids)
    scale = _coordinate_scale(model, bonds)
    center_x, center_y = _coordinate_center(model, atom_ids)
    annotations = atom_annotations or {}

    lines: list[str] = [title, "  Chemvas", ""]
    lines.append(f"{len(atom_ids):>3}{len(bonds):>3}  0  0  0  0  0  0  0  0999 V2000")
    for atom_id in atom_ids:
        atom = model.atoms[atom_id]
        # Canvas y grows downward; MDL y grows upward, so negate it.
        lines.append(
            _atom_line(
                (atom.x - center_x) * scale, -(atom.y - center_y) * scale, atom.element
            )
        )
    for bond in bonds:
        lines.append(_bond_line(index_by_id[bond.a], index_by_id[bond.b], bond))
    lines.extend(_property_lines("CHG", _charges(annotations, index_by_id)))
    lines.extend(_property_lines("RAD", _radicals(annotations, index_by_id)))
    lines.append("M  END")
    return "\n".join(lines) + "\n"


def _reject_non_element_labels(model: MoleculeModel, atom_ids: Sequence[int]) -> None:
    unsupported = sorted(
        {model.atoms[atom_id].element for atom_id in atom_ids} - _ELEMENTS
    )
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
        if not math.isfinite(distance):
            raise MolfileLimitError(
                "Cannot export to MOL: a bond length is outside the finite V2000 "
                "coordinate scaling range."
            )
        if distance > 0.0:
            lengths.append(distance)
    if not lengths:
        return 1.0
    average = sum(lengths) / len(lengths)
    if not math.isfinite(average) or average <= 0.0:
        raise MolfileLimitError(
            "Cannot export to MOL: bond lengths are outside the finite V2000 "
            "coordinate scaling range."
        )
    scale = _TARGET_BOND_LENGTH / average
    if not math.isfinite(scale) or scale <= 0.0:
        raise MolfileLimitError(
            "Cannot export to MOL: bond lengths are outside the finite V2000 "
            "coordinate scaling range."
        )
    return scale


def _coordinate_center(
    model: MoleculeModel, atom_ids: Sequence[int]
) -> tuple[float, float]:
    if not atom_ids:
        return (0.0, 0.0)
    xs = [model.atoms[atom_id].x for atom_id in atom_ids]
    ys = [model.atoms[atom_id].y for atom_id in atom_ids]
    return (_safe_midpoint(min(xs), max(xs)), _safe_midpoint(min(ys), max(ys)))


def _safe_midpoint(low: float, high: float) -> float:
    midpoint = low + (high - low) / 2.0
    if not math.isfinite(midpoint):
        raise MolfileLimitError(
            "Cannot export to MOL: coordinates are outside the finite V2000 "
            "centering range."
        )
    return midpoint


def _atom_line(x: float, y: float, element: str) -> str:
    return (
        f"{_coordinate_field(x)}{_coordinate_field(y)}{_coordinate_field(0.0)} "
        f"{element:<3}{0:>2}" + "  0" * 11
    )


def _coordinate_field(value: float) -> str:
    if not math.isfinite(value):
        raise MolfileLimitError(
            "Cannot export to MOL: a coordinate is outside the finite V2000 "
            "atom-field range after centering."
        )
    if value == 0.0:
        value = 0.0
    field = f"{value:>10.4f}"
    if len(field) > 10:
        raise MolfileLimitError(
            "Cannot export to MOL: a coordinate is outside the V2000 "
            "10-character atom-field range after centering."
        )
    return field


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
            raise MolfileLimitError(
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
        if atom_id not in index_by_id:
            continue
        electrons = int(values.get("radical_electrons", 0))
        if electrons == 0:
            continue
        if electrons not in (1, 2):
            raise MolfileLimitError(
                "Cannot export to MOL: radical electron count "
                f"{electrons} cannot be represented without data loss; "
                "Chemvas supports one- and two-electron radicals."
            )
        # MDL radical codes: 2 doublet, 3 triplet.
        entries.append((index_by_id[atom_id], 2 if electrons == 1 else 3))
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


def parse_molfile(text: str) -> MoleculeModel:
    """Parse an MDL Molfile (V2000) block into a :class:`MoleculeModel`.

    Supports the V2000 subset that :func:`write_molfile` emits: the counts
    line, the atom block (element symbol, 2D coordinates), the bond block
    (orders 1/2/3, wedge/hash stereo flags), and ``M  CHG`` / ``M  RAD``
    property lines terminated by ``M  END``. The property-line count may be
    the writer's ``999`` sentinel or the exact number of lines through
    ``M  END``. Formal charges and radicals are stored in
    ``model.atom_annotations`` (the same per-atom mapping the writer reads).
    The MDL y axis is flipped back to the canvas orientation, but the
    coordinates keep the MDL scale — use :func:`fit_molfile_model` to map them
    onto a canvas. Anything outside this subset raises
    :class:`MolfileParseError`.
    """
    lines = text.splitlines()
    atom_count, bond_count, property_line_count = _parse_counts_line(lines)
    atom_block_end = 4 + atom_count
    bond_block_end = atom_block_end + bond_count
    if len(lines) < bond_block_end:
        raise MolfileParseError(
            "Cannot import MOL: the file ends before the "
            f"{atom_count} atom and {bond_count} bond lines its counts line "
            "declares."
        )
    model = MoleculeModel()
    for line_number, line in enumerate(lines[4:atom_block_end], start=5):
        element, x, y = _parse_atom_line(line, line_number)
        # MDL y grows upward; canvas y grows downward, so negate it back.
        model.add_atom(element, x, -y)
    for line_number, line in enumerate(
        lines[atom_block_end:bond_block_end], start=atom_block_end + 1
    ):
        begin, end, order, style = _parse_bond_line(line, line_number, atom_count)
        try:
            bond_id = model.add_bond(begin, end, order)
        except ValueError as exc:
            raise MolfileParseError(
                f"Cannot import MOL: bond line {line_number} is invalid ({exc})"
            ) from exc
        bond = model.bonds[bond_id]
        if bond is not None:
            bond.style = style
    _parse_property_block(
        lines,
        bond_block_end,
        model,
        atom_count,
        property_line_count=property_line_count,
    )
    return model


def fit_molfile_model(
    model: MoleculeModel,
    *,
    bond_length: float,
    center: tuple[float, float] = (0.0, 0.0),
) -> None:
    """Map a parsed molfile's MDL coordinates onto canvas coordinates.

    Inverts the writer's normalisation: the structure is rescaled so its
    average bond length becomes ``bond_length`` canvas units (an isolated
    atom set without bonds treats :data:`_TARGET_BOND_LENGTH` MDL units as one
    bond length) and its bounding-box centre moves to ``center`` — the sheet
    is centred on the scene origin, so the default centres it on the sheet.
    """
    if not math.isfinite(bond_length) or bond_length <= 0.0:
        raise ValueError("bond_length must be a positive, finite number.")
    atom_ids = sorted(model.atoms)
    if not atom_ids:
        return
    lengths = []
    for bond in model.bonds:
        if bond is None:
            continue
        a = model.atoms[bond.a]
        b = model.atoms[bond.b]
        distance = math.hypot(a.x - b.x, a.y - b.y)
        if distance > 0.0:
            lengths.append(distance)
    average = sum(lengths) / len(lengths) if lengths else _TARGET_BOND_LENGTH
    scale = bond_length / average
    center_x, center_y = _coordinate_center(model, atom_ids)
    for atom in model.atoms.values():
        atom.x = (atom.x - center_x) * scale + center[0]
        atom.y = (atom.y - center_y) * scale + center[1]


def _parse_counts_line(lines: Sequence[str]) -> tuple[int, int, int]:
    if len(lines) < 4:
        raise MolfileParseError(
            "Cannot import MOL: the file ends before the V2000 counts line (line 4)."
        )
    counts_line = lines[3]
    trimmed = counts_line.rstrip()
    if trimmed.endswith("V3000"):
        raise MolfileParseError(
            "Cannot import MOL: this is a V3000 molfile; Chemvas reads V2000 "
            "only. Re-export it as V2000 first."
        )
    if not trimmed.endswith("V2000"):
        raise MolfileParseError(
            "Cannot import MOL: the counts line (line 4) does not declare a "
            "V2000 molfile."
        )
    atom_count = _parse_count_field(counts_line[0:3], "atom")
    bond_count = _parse_count_field(counts_line[3:6], "bond")
    property_line_count = _validate_counts_fields(counts_line)
    return atom_count, bond_count, property_line_count


def _validate_counts_fields(line: str) -> int:
    for start, end, name in _UNSUPPORTED_COUNTS_FIELDS:
        field = line[start:end]
        if not field.strip():
            continue
        try:
            value = int(field)
        except ValueError:
            raise MolfileParseError(
                "Cannot import MOL: the counts line has a malformed "
                f"{name} ({field.strip()!r})."
            ) from None
        if value != 0:
            raise MolfileParseError(
                "Cannot import MOL: the counts line has unsupported "
                f"{name} {value}; Chemvas imports only the zero-valued counts "
                "fields its V2000 writer emits."
            )
    if line[33:].strip() != "V2000":
        raise MolfileParseError(
            "Cannot import MOL: the counts line has unsupported data outside "
            "the V2000 fields."
        )
    return _parse_count_field(line[30:33], "property-line")


def _parse_count_field(field: str, kind: str) -> int:
    try:
        value = int(field)
    except ValueError:
        raise MolfileParseError(
            f"Cannot import MOL: the counts line has a malformed {kind} count "
            f"({field.strip()!r})."
        ) from None
    if value < 0:
        raise MolfileParseError(
            f"Cannot import MOL: the counts line has a negative {kind} count."
        )
    return value


def _parse_atom_line(line: str, line_number: int) -> tuple[str, float, float]:
    if len(line) < 34:
        raise MolfileParseError(
            f"Cannot import MOL: atom line {line_number} is shorter than the "
            "V2000 atom-block format."
        )
    x = _parse_atom_coordinate(line[0:10], line_number, "x")
    y = _parse_atom_coordinate(line[10:20], line_number, "y")
    z = _parse_atom_coordinate(line[20:30], line_number, "z")
    if z != 0.0:
        raise MolfileParseError(
            f"Cannot import MOL: atom line {line_number} has a non-zero z "
            "coordinate; Chemvas imports 2D (z = 0) molfiles only."
        )
    symbol = line[31:34].strip()
    if symbol not in _ELEMENTS:
        raise MolfileParseError(
            f"Cannot import MOL: atom line {line_number} has an unsupported "
            f"element symbol {symbol!r}."
        )
    _reject_unsupported_atom_fields(line, line_number)
    return symbol, x, y


def _reject_unsupported_atom_fields(line: str, line_number: int) -> None:
    for start, end, name in _UNSUPPORTED_ATOM_FIELDS:
        field = line[start:end]
        if not field.strip():
            continue
        try:
            value = int(field)
        except ValueError:
            raise MolfileParseError(
                f"Cannot import MOL: atom line {line_number} has a malformed "
                f"{name} ({field.strip()!r})."
            ) from None
        if value != 0:
            raise MolfileParseError(
                f"Cannot import MOL: atom line {line_number} has unsupported "
                f"{name} {value}; Chemvas imports only the zero-valued atom "
                "fields its V2000 writer emits."
            )
    if line[69:].strip():
        raise MolfileParseError(
            f"Cannot import MOL: atom line {line_number} has unsupported data "
            "after the V2000 atom fields."
        )


def _parse_atom_coordinate(field: str, line_number: int, axis: str) -> float:
    try:
        value = float(field)
    except ValueError:
        raise MolfileParseError(
            f"Cannot import MOL: atom line {line_number} has a malformed "
            f"{axis} coordinate ({field.strip()!r})."
        ) from None
    if not math.isfinite(value):
        raise MolfileParseError(
            f"Cannot import MOL: atom line {line_number} has a non-finite "
            f"{axis} coordinate."
        )
    return value


def _parse_bond_line(
    line: str, line_number: int, atom_count: int
) -> tuple[int, int, int, str]:
    if len(line) < 12:
        raise MolfileParseError(
            f"Cannot import MOL: bond line {line_number} is shorter than the "
            "V2000 bond-block format."
        )
    begin = _parse_bond_atom_index(line[0:3], line_number, atom_count)
    end = _parse_bond_atom_index(line[3:6], line_number, atom_count)
    order = _parse_bond_field(line[6:9], line_number, "order")
    stereo = _parse_bond_field(line[9:12], line_number, "stereo flag")
    if order not in _STYLE_BY_ORDER:
        raise MolfileParseError(
            f"Cannot import MOL: bond line {line_number} has unsupported bond "
            f"order {order}; Chemvas supports orders 1, 2, and 3."
        )
    if stereo not in (0, *_STYLE_BY_STEREO):
        raise MolfileParseError(
            f"Cannot import MOL: bond line {line_number} has unsupported "
            f"stereo flag {stereo}; Chemvas supports 0 (plain), 1 (wedge), "
            "and 6 (hash)."
        )
    if stereo != 0 and order != 1:
        raise MolfileParseError(
            f"Cannot import MOL: bond line {line_number} puts a wedge/hash "
            "stereo flag on a bond of order "
            f"{order}; stereo bonds must be single."
        )
    _reject_unsupported_bond_fields(line, line_number)
    style = _STYLE_BY_STEREO.get(stereo, _STYLE_BY_ORDER[order])
    return begin - 1, end - 1, order, style


def _reject_unsupported_bond_fields(line: str, line_number: int) -> None:
    for start, end, name in _UNSUPPORTED_BOND_FIELDS:
        field = line[start:end]
        if not field.strip():
            continue
        try:
            value = int(field)
        except ValueError:
            raise MolfileParseError(
                f"Cannot import MOL: bond line {line_number} has a malformed "
                f"{name} ({field.strip()!r})."
            ) from None
        if value != 0:
            raise MolfileParseError(
                f"Cannot import MOL: bond line {line_number} has unsupported "
                f"{name} {value}; Chemvas imports only the zero-valued bond "
                "fields its V2000 writer emits."
            )
    if line[21:].strip():
        raise MolfileParseError(
            f"Cannot import MOL: bond line {line_number} has unsupported data "
            "after the V2000 bond fields."
        )


def _parse_bond_atom_index(field: str, line_number: int, atom_count: int) -> int:
    index = _parse_bond_field(field, line_number, "atom index")
    if not 1 <= index <= atom_count:
        raise MolfileParseError(
            f"Cannot import MOL: bond line {line_number} references atom "
            f"{index}, outside this file's 1..{atom_count} atom block."
        )
    return index


def _parse_bond_field(field: str, line_number: int, kind: str) -> int:
    try:
        return int(field)
    except ValueError:
        raise MolfileParseError(
            f"Cannot import MOL: bond line {line_number} has a malformed "
            f"{kind} ({field.strip()!r})."
        ) from None


def _parse_property_block(
    lines: Sequence[str],
    start_index: int,
    model: MoleculeModel,
    atom_count: int,
    *,
    property_line_count: int,
) -> None:
    end_index = None
    for index in range(start_index, len(lines)):
        line = lines[index]
        line_number = index + 1
        if line.rstrip() == "M  END":
            end_index = index
            break
        if line.startswith("M  CHG"):
            _apply_charge_entries(line, line_number, model, atom_count)
        elif line.startswith("M  RAD"):
            _apply_radical_entries(line, line_number, model, atom_count)
        else:
            raise MolfileParseError(
                f"Cannot import MOL: unsupported line {line_number} "
                f"({line.strip()!r}); Chemvas reads only 'M  CHG', 'M  RAD', "
                "and 'M  END' after the bond block."
            )
    if end_index is None:
        raise MolfileParseError(
            "Cannot import MOL: the file has no 'M  END' terminator."
        )
    actual_property_line_count = end_index - start_index + 1
    if property_line_count != 999 and property_line_count != actual_property_line_count:
        raise MolfileParseError(
            "Cannot import MOL: the counts line declares "
            f"{property_line_count} property lines, but the block through "
            f"'M  END' contains {actual_property_line_count}."
        )
    for index in range(end_index + 1, len(lines)):
        if lines[index].strip():
            raise MolfileParseError(
                f"Cannot import MOL: unexpected content on line {index + 1}, "
                "after 'M  END'."
            )


def _apply_charge_entries(
    line: str, line_number: int, model: MoleculeModel, atom_count: int
) -> None:
    for index, charge in _parse_property_entries(line, line_number, "CHG"):
        _validate_property_atom_index(index, line_number, "CHG", atom_count)
        if not _MDL_MIN_CHARGE <= charge <= _MDL_MAX_CHARGE:
            raise MolfileParseError(
                f"Cannot import MOL: line {line_number} has formal charge "
                f"{charge:+d} for atom {index}, outside the MDL range "
                f"{_MDL_MIN_CHARGE}..{_MDL_MAX_CHARGE:+d}."
            )
        annotation = model.atom_annotations.setdefault(index - 1, {})
        if "formal_charge" in annotation:
            raise MolfileParseError(
                f"Cannot import MOL: line {line_number} assigns atom {index} "
                "a second formal charge."
            )
        annotation["formal_charge"] = charge


def _apply_radical_entries(
    line: str, line_number: int, model: MoleculeModel, atom_count: int
) -> None:
    for index, code in _parse_property_entries(line, line_number, "RAD"):
        _validate_property_atom_index(index, line_number, "RAD", atom_count)
        if code == 1:
            raise MolfileParseError(
                f"Cannot import MOL: line {line_number} assigns singlet radical "
                f"code 1 to atom {index}; Chemvas cannot preserve singlet spin "
                "multiplicity."
            )
        electrons = _RADICAL_ELECTRONS_BY_CODE.get(code)
        if electrons is None:
            raise MolfileParseError(
                f"Cannot import MOL: line {line_number} has unsupported "
                f"radical code {code} for atom {index}; MDL defines codes "
                "1 (singlet), 2 (doublet), and 3 (triplet)."
            )
        annotation = model.atom_annotations.setdefault(index - 1, {})
        if "radical_electrons" in annotation:
            raise MolfileParseError(
                f"Cannot import MOL: line {line_number} assigns atom {index} "
                "a second radical code."
            )
        annotation["radical_electrons"] = electrons


def _validate_property_atom_index(
    index: int, line_number: int, tag: str, atom_count: int
) -> None:
    if not 1 <= index <= atom_count:
        raise MolfileParseError(
            f"Cannot import MOL: line {line_number} has an 'M  {tag}' entry "
            f"for atom {index}, outside this file's 1..{atom_count} atom "
            "block."
        )


def _parse_property_entries(
    line: str, line_number: int, tag: str
) -> list[tuple[int, int]]:
    try:
        numbers = [int(token) for token in line.split()[2:]]
    except ValueError:
        raise MolfileParseError(
            f"Cannot import MOL: line {line_number} has a malformed 'M  {tag}' entry."
        ) from None
    if not numbers or numbers[0] < 1 or len(numbers) != 1 + 2 * numbers[0]:
        raise MolfileParseError(
            f"Cannot import MOL: line {line_number} does not carry the "
            f"index/value pairs its 'M  {tag}' count declares."
        )
    return [(numbers[i], numbers[i + 1]) for i in range(1, len(numbers), 2)]


__all__ = [
    "MolfileError",
    "MolfileLimitError",
    "MolfileParseError",
    "fit_molfile_model",
    "parse_molfile",
    "write_molfile",
]
