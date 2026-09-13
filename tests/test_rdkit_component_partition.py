from __future__ import annotations

from copy import deepcopy

import pytest

from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.domain.document import Atom, Bond, MoleculeModel, connected_atom_components
from chemvas.features.insertion import Molecule3DAtom, Molecule3DScene


def test_shared_components_preserve_sparse_ids_and_ignore_nonlive_edges():
    atoms = [19, 2, 7, 31, 45]
    bonds = [(19, 2), (2, 19), (7, 7), (31, 999), (999, 45)]
    assert connected_atom_components(iter(atoms), iter(bonds)) == (
        (2, 19),
        (7,),
        (31,),
        (45,),
    )
    assert connected_atom_components([], []) == ()


def test_disconnected_seed_traversal_does_not_rescan_remaining_atoms_quadratically():
    class CountedId(int):
        comparisons = 0

        def __lt__(self, other):
            type(self).comparisons += 1
            return super().__lt__(other)

    count = 512
    atoms = [CountedId(index) for index in range(count)]
    assert connected_atom_components(atoms, []) == tuple(
        (index,) for index in range(count)
    )
    # A sorted seed pass is well within this bound; repeated min(remaining)
    # needs count*(count-1)/2 comparisons. No wall-clock timing in the gate.
    assert CountedId.comparisons < count * 16


def test_rdkit_partition_keeps_spatial_then_id_order_and_model_identity():
    model = MoleculeModel(
        atoms={
            30: Atom("N", -20.125, 4.3),
            40: Atom("C", -10.125, 4.3),
            3: Atom("O", 30.2, 0.0),
            4: Atom("C", 40.2, 0.0),
            1: Atom("F", -15.125, 4.3),
            2: Atom("Cl", -15.125, -8.7),
        },
        bonds=[Bond(30, 40), None, Bond(3, 4), Bond(30, 40), Bond(1, 1), Bond(2, 999)],
        atom_annotations={30: {"formal_charge": 1}},
    )
    before = deepcopy(model)
    atoms = dict(model.atoms)
    bonds = list(model.bonds)
    helper = RDKitAdapter()._conversion_helper
    assert helper._model_components(model) == [{2}, {1}, {30, 40}, {3, 4}]
    assert model == before
    assert all(model.atoms[key] is atom for key, atom in atoms.items())
    assert all(
        first is second for first, second in zip(model.bonds, bonds, strict=True)
    )
    assert helper._model_components(MoleculeModel()) == []


def _capture_preview_components(monkeypatch, model, atom_annotations=None):
    adapter = RDKitAdapter()
    adapter._rdkit = (object(), object())
    components = []

    def build(component, *, atom_annotations):
        components.append((component, atom_annotations))
        return component

    monkeypatch.setattr(adapter, "_build_conversion_rdkit_mol", build)
    monkeypatch.setattr(adapter, "_embed_3d_molecule", lambda mol, *_: mol)
    monkeypatch.setattr(
        adapter._conversion_helper,
        "_scene_from_embedded_mol",
        lambda mol: Molecule3DScene(
            atoms=tuple(
                Molecule3DAtom(atom.element, atom.x, atom.y, 0.0)
                for atom in mol.atoms.values()
            ),
            bonds=(),
        ),
    )
    assert (
        adapter.model_to_3d_scene(model, atom_annotations=atom_annotations) is not None
    )
    return components


@pytest.mark.parametrize("component_count", [1, 4, 64, 257])
def test_preview_component_split_visits_source_bonds_linearly(
    monkeypatch, component_count
):
    class CountedBonds(list):
        visits = 0

        def __iter__(self):
            for bond in super().__iter__():
                self.visits += 1
                yield bond

    model = MoleculeModel(
        atoms={
            index: Atom("C", float(index), 0.0) for index in range(component_count * 2)
        },
        bonds=CountedBonds(
            Bond(index, index + 1) for index in range(0, component_count * 2, 2)
        ),
    )
    components = _capture_preview_components(monkeypatch, model)
    assert len(components) == component_count
    assert all(len(component.bonds) == 1 for component, _ in components)
    # Bound source-list traversal, not RDKit embedding time or private call count.
    # Scanning every source bond for every component grows quadratically.
    assert model.bonds.visits <= component_count * 3


@pytest.mark.parametrize("override", [None, {}, {30: {"formal_charge": -1}}])
def test_preview_component_split_keeps_order_ids_annotations_and_independent_copies(
    monkeypatch, override
):
    model = MoleculeModel(
        atoms={
            30: Atom("N", -20.125, 4.3, "#123456", True),
            40: Atom("C", -10.125, 4.3),
            3: Atom("O", 30.2, 0.0),
            4: Atom("C", 40.2, 0.0),
            1: Atom("F", -15.125, 4.3),
            2: Atom("Cl", -15.125, -8.7),
        },
        bonds=[
            Bond(40, 30, 1, "wedge", "#123456"),
            None,
            Bond(3, 4, 2, "double", "#234567"),
            Bond(30, 40, 1, "hashed", "#345678"),
            Bond(1, 1),
            Bond(2, 999),
        ],
        atom_annotations={30: {"formal_charge": 1}, 3: {"radical_electrons": 1}},
    )
    before = deepcopy(model)
    override_before = deepcopy(override)
    source_atoms = dict(model.atoms)
    source_bonds = list(model.bonds)
    components = _capture_preview_components(monkeypatch, model, override)
    assert [list(component.atoms) for component, _ in components] == [
        [2],
        [1],
        [30, 40],
        [3, 4],
    ]
    assert [component.bonds for component, _ in components] == [
        [],
        [Bond(1, 1)],
        [Bond(40, 30, 1, "wedge", "#123456"), Bond(30, 40, 1, "hashed", "#345678")],
        [Bond(3, 4, 2, "double", "#234567")],
    ]
    expected_annotations = (
        [{}, {}, {30: {"formal_charge": 1}}, {3: {"radical_electrons": 1}}]
        if override is None
        else [{}, {}, override, {}]
    )
    assert [annotations for _, annotations in components] == expected_annotations
    assert [component.next_atom_id for component, _ in components] == [3, 2, 41, 5]
    for component, component_annotations in components:
        assert component.atom_annotations is component_annotations
        for atom_id, atom in component.atoms.items():
            assert atom == model.atoms[atom_id]
            assert atom is not model.atoms[atom_id]
            atom.x += 100
        for bond in component.bonds:
            assert all(bond is not source for source in model.bonds)
            bond.color = "#ffffff"
        for values in component_annotations.values():
            values["formal_charge"] = 99
    assert model == before
    assert override == override_before
    assert all(model.atoms[key] is atom for key, atom in source_atoms.items())
    assert all(
        first is second for first, second in zip(model.bonds, source_bonds, strict=True)
    )
