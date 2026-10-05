from __future__ import annotations

from itertools import combinations

import pytest

import chemvas.domain.document.inspection as document_inspection
from chemvas.domain.document import (
    Atom,
    Bond,
    MoleculeModel,
    connected_atom_components,
    serialize_model_state,
)
from chemvas.domain.document.inspection import inspect_components


class _CountingBondList(list[Bond | None]):
    def __init__(self, values: list[Bond | None]) -> None:
        super().__init__(values)
        self.iterations = 0

    def __iter__(self):
        self.iterations += 1
        return super().__iter__()


def _state(model: MoleculeModel, marks: list[dict[str, object]]) -> dict[str, object]:
    return {"model": serialize_model_state(model), "marks": marks}


def _mark(kind: str, atom_id: int) -> dict[str, object]:
    return {
        "kind": kind,
        "text": None,
        "atom_id": atom_id,
        "dx": None,
        "dy": None,
        "x": 0.0,
        "y": 0.0,
    }


def test_inspect_components_uses_stable_atom_id_order_and_annotation_totals() -> None:
    model = MoleculeModel(
        atoms={
            8: Atom("Cl", 10.0, 1.0),
            2: Atom("C", 0.0, 0.0),
            4: Atom("O", 1.0, 0.0),
        },
        bonds=[Bond(2, 4, order=2)],
    )

    components = inspect_components(
        _state(model, [_mark("minus", 8), _mark("radical", 4)])
    )

    assert [component.atom_ids for component in components] == [(2, 4), (8,)]
    assert components[0].formula_labels == (("C", 1), ("O", 1))
    assert components[0].bond_count == 1
    assert components[0].radical_electrons == 1
    assert components[1].formal_charge == -1


def test_component_inspection_matches_domain_for_every_graph_through_four_nodes() -> (
    None
):
    for node_count in range(5):
        node_ids = tuple(range(node_count))
        possible_bonds = tuple(combinations(node_ids, 2))
        for mask in range(1 << len(possible_bonds)):
            bond_pairs = tuple(
                pair for index, pair in enumerate(possible_bonds) if mask & (1 << index)
            )
            model = MoleculeModel(
                atoms={
                    atom_id: Atom("C", float(atom_id), 0.0)
                    for atom_id in reversed(node_ids)
                },
                bonds=[Bond(first, second) for first, second in reversed(bond_pairs)],
            )

            inspected = inspect_components(_state(model, []))

            assert tuple(component.atom_ids for component in inspected) == (
                connected_atom_components(node_ids, bond_pairs)
            )


def test_bonded_component_apis_precompute_bonds_and_alias_attachments_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component_count = 64
    atoms = {
        atom_id: Atom(
            "PPh3" if atom_id % 2 else "C",
            float(atom_id),
            0.0,
        )
        for atom_id in range(component_count * 2)
    }
    bonds = _CountingBondList(
        [Bond(index * 2, index * 2 + 1) for index in range(component_count)]
    )
    model = MoleculeModel(atoms=atoms, bonds=bonds)
    state = _state(model, [])
    monkeypatch.setattr(
        document_inspection,
        "deserialize_model_state",
        lambda _model_state: model,
    )

    bonds.iterations = 0
    inspected = inspect_components(state)
    assert len(inspected) == component_count
    assert all(component.bond_count == 1 for component in inspected)
    assert all(component.formal_charge == 1 for component in inspected)
    assert bonds.iterations == 2


@pytest.mark.parametrize(
    ("neighbor_element", "bond_order", "bond_style"),
    [
        ("Pt", 1, "single"),
        ("N", 1, "single"),
        ("C", 2, "double"),
        ("C", 3, "triple"),
        ("C", 1, "dotted"),
        ("C", 1, "dotted_double"),
        ("C", 1, "bold_in"),
    ],
)
def test_component_inspection_rejects_ambiguous_pph3_attachment_contexts(
    neighbor_element: str,
    bond_order: int,
    bond_style: str,
) -> None:
    model = MoleculeModel(
        atoms={0: Atom(neighbor_element, 0.0, 0.0), 1: Atom("PPh3", 1.0, 0.0)},
        bonds=[Bond(0, 1, order=bond_order, style=bond_style)],
    )

    with pytest.raises(ValueError, match="requires one ordinary single bond to carbon"):
        inspect_components(_state(model, []))


@pytest.mark.parametrize("attachment_count", [0, 2])
def test_component_inspection_rejects_invalid_pph3_attachment_count(
    attachment_count: int,
) -> None:
    model = MoleculeModel(atoms={0: Atom("PPh3", 0.0, 0.0)})
    for index in range(attachment_count):
        neighbor = index + 1
        model.atoms[neighbor] = Atom("C", float(neighbor), 0.0)
        model.bonds.append(Bond(0, neighbor))

    with pytest.raises(ValueError, match="requires exactly one attachment bond"):
        inspect_components(_state(model, []))


@pytest.mark.parametrize("mark_kind", ["plus", "minus", "radical"])
def test_component_inspection_rejects_explicit_pph3_electronic_annotations(
    mark_kind: str,
) -> None:
    model = MoleculeModel(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("PPh3", 1.0, 0.0)},
        bonds=[Bond(0, 1)],
    )

    with pytest.raises(
        ValueError, match="does not support explicit charge or radical annotations"
    ):
        inspect_components(_state(model, [_mark(mark_kind, 1)]))


@pytest.mark.parametrize(
    "marks",
    [
        [_mark("plus", 1), _mark("minus", 1)],
        [_mark("circled_plus", 1), _mark("circled_minus", 1)],
    ],
)
def test_pph3_rejects_cancelling_explicit_charge_marks_across_component_apis(
    marks: list[dict[str, object]],
) -> None:
    model = MoleculeModel(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("PPh3", 1.0, 0.0)},
        bonds=[Bond(0, 1)],
    )
    state = _state(model, marks)
    operations = (lambda: inspect_components(state),)

    for operation in operations:
        with pytest.raises(
            ValueError,
            match="does not support explicit charge or radical annotations",
        ):
            operation()


def test_conflicting_mark_and_model_annotations_fail_closed() -> None:
    model = MoleculeModel(
        atoms={0: Atom("N", 0.0, 0.0)},
        atom_annotations={0: {"formal_charge": 1}},
    )

    with pytest.raises(ValueError, match="Conflicting charge/radical annotations"):
        inspect_components(_state(model, [_mark("minus", 0)]))


def test_model_annotation_without_matching_visible_mark_fails_closed() -> None:
    model = MoleculeModel(
        atoms={0: Atom("N", 0.0, 0.0)},
        atom_annotations={0: {"formal_charge": 1}},
    )

    with pytest.raises(ValueError, match="Conflicting charge/radical annotations"):
        inspect_components(_state(model, []))
