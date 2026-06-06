from types import SimpleNamespace

from core.model import Atom, Bond, MoleculeModel
from ui.canvas_model_access import (
    add_atom_to_model_for,
    add_bond_to_model_for,
    atom_for_id,
    atoms_for,
    bond_count_for,
    bond_for_id,
    bond_ids_from,
    bonds_for,
    clear_bond_for_id,
    created_atom_ids_from,
    ensure_next_atom_id_after_for,
    has_atoms_for,
    has_bond_slot_for,
    model_for,
    next_atom_id_for,
    remove_atom_direct_for,
    set_atom_for_id,
    set_bond_for_id,
    set_model_for,
    set_next_atom_id_for,
    trim_bonds_direct_for,
)


def test_model_collection_accessors_return_underlying_model_collections() -> None:
    model = SimpleNamespace(atoms={1: Atom("C", 1.0, 2.0)}, bonds=[Bond(1, 2)], next_atom_id=2)
    canvas = SimpleNamespace(model=model)

    assert model_for(canvas) is model
    assert atoms_for(canvas) is model.atoms
    assert bonds_for(canvas) is model.bonds
    assert next_atom_id_for(canvas) == 2
    assert bond_count_for(canvas) == 1
    assert list(bond_ids_from(canvas, 0)) == [0]
    assert has_atoms_for(canvas) is True


def test_atom_and_bond_lookup_helpers_tolerate_missing_ids() -> None:
    atom = Atom("O", 3.0, 4.0)
    bond = Bond(1, 2)
    canvas = SimpleNamespace(model=SimpleNamespace(atoms={1: atom}, bonds=[None, bond]))

    assert atom_for_id(canvas, 1) is atom
    assert atom_for_id(canvas, 99) is None
    assert atom_for_id(canvas, None) is None

    assert bond_for_id(canvas, 1) is bond
    assert bond_for_id(canvas, 0) is None
    assert bond_for_id(canvas, -1) is None
    assert bond_for_id(canvas, None) is None
    assert bond_for_id(canvas, 99) is None


def test_has_atoms_for_is_false_for_empty_model() -> None:
    canvas = SimpleNamespace(model=SimpleNamespace(atoms={}, bonds=[]))

    assert has_atoms_for(canvas) is False


def test_model_mutation_helpers_trim_remove_and_restore_next_atom_id() -> None:
    canvas = SimpleNamespace(
        model=SimpleNamespace(
            atoms={0: Atom("C", 0.0, 0.0), 2: Atom("N", 2.0, 0.0), 3: Atom("O", 3.0, 0.0)},
            bonds=[Bond(0, 2), Bond(2, 3), Bond(3, 0)],
            next_atom_id=4,
        )
    )

    assert created_atom_ids_from(canvas, 2) == [3, 2]

    trim_bonds_direct_for(canvas, 1)
    clear_bond_for_id(canvas, 0)
    remove_atom_direct_for(canvas, 3)
    set_next_atom_id_for(canvas, 2)

    assert canvas.model.bonds == [None]
    assert set(canvas.model.atoms) == {0, 2}
    assert canvas.model.next_atom_id == 2


def test_bond_mutation_helpers_add_extend_set_and_validate_slots() -> None:
    canvas = SimpleNamespace(model=MoleculeModel())

    bond_id = add_bond_to_model_for(canvas, 1, 2, 2)
    set_bond_for_id(canvas, 3, Bond(4, 5, 1))

    assert bond_id == 0
    assert has_bond_slot_for(canvas, 0) is True
    assert has_bond_slot_for(canvas, 2) is True
    assert has_bond_slot_for(canvas, 99) is False
    assert canvas.model.bonds == [Bond(1, 2, 2), None, None, Bond(4, 5, 1)]


def test_atom_mutation_helpers_add_set_and_advance_next_atom_id() -> None:
    canvas = SimpleNamespace(model=MoleculeModel())

    atom_id = add_atom_to_model_for(canvas, "C", 1.0, 2.0)
    set_atom_for_id(canvas, 5, Atom("O", 5.0, 6.0))
    ensure_next_atom_id_after_for(canvas, 5)

    assert atom_id == 0
    assert canvas.model.atoms[0] == Atom("C", 1.0, 2.0)
    assert canvas.model.atoms[5] == Atom("O", 5.0, 6.0)
    assert canvas.model.next_atom_id == 6


def test_set_model_for_replaces_canvas_model() -> None:
    old_model = SimpleNamespace(atoms={}, bonds=[], next_atom_id=0)
    new_model = SimpleNamespace(atoms={1: Atom("C", 1.0, 1.0)}, bonds=[], next_atom_id=2)
    canvas = SimpleNamespace(model=old_model)

    set_model_for(canvas, new_model)

    assert canvas.model is new_model
