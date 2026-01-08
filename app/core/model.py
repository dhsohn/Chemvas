from dataclasses import dataclass, field
from typing import Dict, List, Tuple


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
    atoms: Dict[int, Atom] = field(default_factory=dict)
    bonds: List[Bond] = field(default_factory=list)
    next_atom_id: int = 0

    def __post_init__(self) -> None:
        if self.atoms:
            self.next_atom_id = max(self.atoms.keys()) + 1

    def add_atom(self, element: str, x: float, y: float) -> int:
        atom_id = self.next_atom_id
        self.next_atom_id += 1
        self.atoms[atom_id] = Atom(element=element, x=x, y=y)
        return atom_id

    def add_bond(self, a: int, b: int, order: int = 1) -> None:
        self.bonds.append(Bond(a=a, b=b, order=order))

    def bounds(self) -> Tuple[float, float, float, float]:
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
            if dist_sq <= nearest_dist_sq:
                nearest_id = atom_id
                nearest_dist_sq = dist_sq
        return nearest_id
