from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

ATOM_ANNOTATION_KEYS = frozenset({"formal_charge", "radical_electrons"})


@dataclass
class Atom:
    element: str
    x: float
    y: float
    color: str = "#000000"
    explicit_label: bool = False


@dataclass
class Bond:
    a: int
    b: int
    order: int = 1
    style: str = "single"
    color: str = "#000000"


@dataclass
class MoleculeModel:
    atoms: dict[int, Atom] = field(default_factory=dict)
    bonds: list[Bond | None] = field(default_factory=list)
    next_atom_id: int = 0
    atom_annotations: dict[int, dict[str, int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.atoms:
            self.next_atom_id = max(self.atoms.keys()) + 1

    def add_atom(self, element: str, x: float, y: float) -> int:
        atom_id = self.next_atom_id
        self.next_atom_id += 1
        self.atoms[atom_id] = Atom(element=element, x=x, y=y)
        return atom_id

    def add_bond(self, a: int, b: int, order: int = 1) -> int:
        if type(a) is not int or type(b) is not int:
            raise ValueError("Bond endpoints must be atom ids.")
        if a not in self.atoms or b not in self.atoms:
            raise ValueError("Bond endpoints must reference existing atoms.")
        if a == b:
            raise ValueError("Bond endpoints must be distinct.")
        if type(order) is not int or order not in (1, 2, 3):
            raise ValueError("Bond order must be 1, 2, or 3.")
        # Last line of defense: callers deduplicate through the graph index,
        # but a duplicate pair reaching the model would make every later save
        # fail document validation, so reject it loudly here instead.
        for bond in self.bonds:
            if bond is not None and {bond.a, bond.b} == {a, b}:
                raise ValueError("Bond endpoints are already bonded.")
        bond_id = len(self.bonds)
        self.bonds.append(Bond(a=a, b=b, order=order))
        return bond_id

    def atom_for_id(self, atom_id: int | None) -> Atom | None:
        if atom_id is None:
            return None
        return self.atoms.get(atom_id)

    def set_atom(self, atom_id: int, atom: Atom) -> None:
        """Store an atom record directly; the annotation for that id is reset."""
        self.atoms[atom_id] = atom
        self.clear_atom_annotation(atom_id)

    def pop_atom(self, atom_id: int) -> None:
        """Drop the atom record and its annotation; bonds are the caller's job."""
        self.atoms.pop(atom_id, None)
        self.clear_atom_annotation(atom_id)

    def ensure_next_atom_id_after(self, atom_id: int) -> None:
        if atom_id >= int(self.next_atom_id):
            self.next_atom_id = atom_id + 1

    def created_atom_ids_from(self, before_next_atom_id: int) -> list[int]:
        """Atom ids allocated since ``next_atom_id`` was ``before_next_atom_id``,
        highest first so callers can remove them in reverse order."""
        return sorted(
            (atom_id for atom_id in self.atoms if atom_id >= before_next_atom_id),
            reverse=True,
        )

    def bond_for_id(self, bond_id: int | None) -> Bond | None:
        if bond_id is None or bond_id < 0:
            return None
        try:
            return self.bonds[bond_id]
        except (IndexError, KeyError, TypeError):
            return None

    def bond_ids_from(self, start: int) -> range:
        return range(start, len(self.bonds))

    def has_bond_slot(self, bond_id: int) -> bool:
        return 0 <= bond_id < len(self.bonds)

    def set_bond(self, bond_id: int, bond: Bond | None) -> None:
        """Store a bond at a fixed slot, padding with ``None`` past the end."""
        if bond_id < len(self.bonds):
            self.bonds[bond_id] = bond
            return
        self.bonds.extend([None] * (bond_id - len(self.bonds)))
        self.bonds.append(bond)

    def clear_bond(self, bond_id: int) -> None:
        """Empty a bond slot; slots are never renumbered."""
        if 0 <= bond_id < len(self.bonds):
            self.bonds[bond_id] = None

    def trim_bonds(self, length: int) -> None:
        if len(self.bonds) > length:
            del self.bonds[length:]

    def atom_annotation_for(self, atom_id: int) -> dict[str, int] | None:
        annotation = self.atom_annotations.get(atom_id)
        if not isinstance(annotation, Mapping):
            return None
        return {
            str(key): int(value)
            for key, value in annotation.items()
            if key in ATOM_ANNOTATION_KEYS and type(value) is int
        }

    def set_atom_annotation(
        self, atom_id: int, annotation: Mapping[str, int] | None
    ) -> None:
        """Keep only the non-zero integer entries; an empty result removes the key."""
        if not annotation:
            self.atom_annotations.pop(atom_id, None)
            return
        cleaned = {
            str(key): int(value)
            for key, value in annotation.items()
            if key in ATOM_ANNOTATION_KEYS and type(value) is int and value
        }
        if cleaned:
            self.atom_annotations[atom_id] = cleaned
        else:
            self.atom_annotations.pop(atom_id, None)

    def clear_atom_annotation(self, atom_id: int) -> None:
        self.atom_annotations.pop(atom_id, None)

    def center(self) -> tuple[float, float]:
        """Mean atom position; the model must hold at least one atom."""
        atoms = self.atoms.values()
        return (
            sum(atom.x for atom in atoms) / len(self.atoms),
            sum(atom.y for atom in atoms) / len(self.atoms),
        )

    def scale_about(self, center_x: float, center_y: float, scale: float) -> None:
        for atom in self.atoms.values():
            atom.x = center_x + (atom.x - center_x) * scale
            atom.y = center_y + (atom.y - center_y) * scale

    def bounds(self) -> tuple[float, float, float, float]:
        if not self.atoms:
            return 0.0, 0.0, 0.0, 0.0
        xs = [atom.x for atom in self.atoms.values()]
        ys = [atom.y for atom in self.atoms.values()]
        return min(xs), min(ys), max(xs), max(ys)

    def find_atom_near(self, x: float, y: float, max_dist: float) -> int | None:
        nearest_id = None
        nearest_dist_sq = max_dist * max_dist
        for atom_id, atom in self.atoms.items():
            dx = atom.x - x
            dy = atom.y - y
            dist_sq = dx * dx + dy * dy
            # Lowest atom id breaks exact-distance ties, matching the spatial
            # index lookup so both paths pick the same atom.
            if dist_sq < nearest_dist_sq or (
                dist_sq == nearest_dist_sq
                and (nearest_id is None or atom_id < nearest_id)
            ):
                nearest_id = atom_id
                nearest_dist_sq = dist_sq
        return nearest_id
