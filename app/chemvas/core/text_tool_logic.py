from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from chemvas.core.history import AddAtomsCommand
from chemvas.domain.document import Atom, Bond, MoleculeModel

Point2D = tuple[float, float]


@dataclass(frozen=True)
class TextToolTarget:
    atom_id: int | None
    pos: Point2D


@dataclass(frozen=True)
class TextInputPlan:
    text: str | None
    needs_prompt: bool
    initial: str


def normalize_text_symbol(text: str) -> str:
    return text.strip()


def plan_text_input(current_symbol: str, existing_element: str = "") -> TextInputPlan:
    text = normalize_text_symbol(current_symbol)
    if text:
        return TextInputPlan(text=text, needs_prompt=False, initial=existing_element)
    return TextInputPlan(text=None, needs_prompt=True, initial=existing_element)


def resolve_text_tool_target(
    model: MoleculeModel,
    *,
    pos: Point2D,
    hover_atom_id: int | None = None,
    item_atom_id: int | None = None,
    hover_bond_id: int | None = None,
    nearby_bond_id: int | None = None,
    nearby_atom_id: int | None = None,
) -> TextToolTarget:
    atom = _atom(model.atoms, hover_atom_id)
    if atom is not None and hover_atom_id is not None:
        return TextToolTarget(atom_id=hover_atom_id, pos=(atom.x, atom.y))

    atom = _atom(model.atoms, item_atom_id)
    if atom is not None and item_atom_id is not None:
        return TextToolTarget(atom_id=item_atom_id, pos=(atom.x, atom.y))

    atom_id = _nearest_bond_atom_id(model, hover_bond_id, pos)
    if atom_id is not None:
        atom = model.atoms[atom_id]
        return TextToolTarget(atom_id=atom_id, pos=(atom.x, atom.y))

    atom_id = _nearest_bond_atom_id(model, nearby_bond_id, pos)
    if atom_id is not None:
        atom = model.atoms[atom_id]
        return TextToolTarget(atom_id=atom_id, pos=(atom.x, atom.y))

    atom = _atom(model.atoms, nearby_atom_id)
    if atom is not None and nearby_atom_id is not None:
        return TextToolTarget(atom_id=nearby_atom_id, pos=pos)

    return TextToolTarget(atom_id=None, pos=pos)


def build_created_atom_command(
    *,
    atom_id: int,
    atom_state: dict,
    before_next_atom_id: int,
    after_next_atom_id: int,
    before_smiles_input: str | None,
    after_smiles_input: str | None,
) -> AddAtomsCommand:
    return AddAtomsCommand(
        atom_states={atom_id: atom_state},
        before_next_atom_id=before_next_atom_id,
        after_next_atom_id=after_next_atom_id,
        before_smiles_input=before_smiles_input,
        after_smiles_input=after_smiles_input,
    )


def _nearest_bond_atom_id(
    model: MoleculeModel,
    bond_id: int | None,
    pos: Point2D,
) -> int | None:
    bond = _bond(model.bonds, bond_id)
    if bond is None:
        return None
    atom_a = model.atoms.get(bond.a)
    atom_b = model.atoms.get(bond.b)
    if atom_a is None or atom_b is None:
        return None
    da = (pos[0] - atom_a.x) ** 2 + (pos[1] - atom_a.y) ** 2
    db = (pos[0] - atom_b.x) ** 2 + (pos[1] - atom_b.y) ** 2
    return bond.a if da <= db else bond.b


def _atom(atoms: Mapping[int, Atom], atom_id: int | None) -> Atom | None:
    if not isinstance(atom_id, int):
        return None
    return atoms.get(atom_id)


def _bond(bonds: list[Bond | None], bond_id: int | None) -> Bond | None:
    if not isinstance(bond_id, int):
        return None
    if not (0 <= bond_id < len(bonds)):
        return None
    return bonds[bond_id]


__all__ = [
    "TextInputPlan",
    "TextToolTarget",
    "build_created_atom_command",
    "normalize_text_symbol",
    "plan_text_input",
    "resolve_text_tool_target",
]
