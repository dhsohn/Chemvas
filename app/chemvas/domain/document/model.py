from __future__ import annotations

from dataclasses import dataclass, field


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
