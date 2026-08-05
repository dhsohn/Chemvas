from __future__ import annotations

import pytest
from chemvas.domain.document import Atom, Bond, MoleculeModel, serialize_model_state
from chemvas.features.calculation_bundle import inspect_components, select_component


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
