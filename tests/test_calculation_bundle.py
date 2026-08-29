from __future__ import annotations

from itertools import combinations

import pytest

from chemvas.domain.document import (
    Atom,
    Bond,
    MoleculeModel,
    connected_atom_components,
    serialize_model_state,
)
from chemvas.features.calculation_bundle import (
    inspect_components,
    select_component,
    select_components,
)


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
    operations = (
        lambda: inspect_components(state),
        lambda: select_component(state, 0),
        lambda: select_components(state, [[0, 1]]),
    )

    for operation in operations:
        with pytest.raises(
            ValueError,
            match="does not support explicit charge or radical annotations",
        ):
            operation()


def test_select_component_preserves_original_atom_ids_bonds_and_annotations() -> None:
    model = MoleculeModel(
        atoms={3: Atom("N", 0.0, 0.0), 7: Atom("H", 1.0, 0.0)},
        bonds=[Bond(3, 7)],
        atom_annotations={3: {"formal_charge": 1}},
    )

    selected = select_component(_state(model, [_mark("plus", 3)]), 0)

    assert sorted(selected.model.atoms) == [3, 7]
    assert selected.model.bonds == [Bond(3, 7)]
    assert selected.model.atom_annotations == {3: {"formal_charge": 1}}
    assert selected.summary.formal_charge == 1


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


def test_select_component_rejects_empty_and_out_of_range_documents() -> None:
    with pytest.raises(ValueError, match="no chemical structure"):
        select_component(_state(MoleculeModel(), []), 0)

    one_atom = MoleculeModel(atoms={0: Atom("C", 0.0, 0.0)})
    with pytest.raises(ValueError, match="choose 0 to 0"):
        select_component(_state(one_atom, []), 1)
