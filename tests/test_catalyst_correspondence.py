from __future__ import annotations

import copy
import importlib.util
from dataclasses import replace

import pytest

from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.domain.document import MoleculeModel

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("rdkit") is None,
    reason="optional RDKit dependency is not installed",
)


def _append_smiles(adapter, model, smiles):
    fragment = adapter.smiles_to_2d(smiles)
    assert fragment is not None, adapter.last_error
    offset = model.next_atom_id
    model.atoms.update(
        {
            atom_id + offset: copy.deepcopy(atom)
            for atom_id, atom in fragment.atoms.items()
        }
    )
    model.bonds.extend(
        replace(bond, a=bond.a + offset, b=bond.b + offset)
        for bond in fragment.bonds
        if bond is not None
    )
    model.atom_annotations.update(
        {
            atom_id + offset: dict(value)
            for atom_id, value in fragment.atom_annotations.items()
        }
    )
    model.next_atom_id = max(model.atoms) + 1
    return frozenset(atom_id + offset for atom_id in fragment.atoms)


def _reaction():
    adapter = RDKitAdapter()
    model = MoleculeModel()
    catalyst = _append_smiles(adapter, model, "CNC(=S)NC")
    reactant = _append_smiles(adapter, model, "C[N+](=O)[O-]")
    product = _append_smiles(adapter, model, "C=[N+]([O-])O")
    return adapter, model, catalyst, reactant, product


@pytest.mark.parametrize("anchored", [False, True])
def test_reviewed_identity_catalyst_does_not_hide_the_substrate(anchored):
    adapter, model, catalyst, reactant, product = _reaction()
    fixed = {atom_id: atom_id for atom_id in catalyst}
    reactive_anchor = {6: 10} if anchored else {}
    fixed.update(reactive_anchor)
    before = copy.deepcopy(model)
    baseline = adapter.suggest_atom_correspondence_result(
        model, reactant, product, reactive_anchor
    )
    assert baseline.error is None
    # Order-agnostic matching leaves the two oxygens interchangeable. Preserve
    # the existing substrate-only suggestion, not a claimed unique mechanism.
    assert set(baseline.value) == {(6, 10), (7, 11), (8, 12), (9, 13)}

    result = adapter.suggest_atom_correspondence_result(
        model, reactant | catalyst, product | catalyst, fixed
    )

    assert result.error is None
    assert set(result.value) == set(baseline.value) | {
        (atom_id, atom_id) for atom_id in catalyst
    }
    assert all(
        dict(result.value)[atom_id] == target for atom_id, target in fixed.items()
    )
    assert model == before


@pytest.mark.parametrize("partial", [False, True])
def test_unreviewed_or_partially_mapped_shared_component_is_not_removed(partial):
    adapter, model, catalyst, reactant, product = _reaction()
    fixed = {0: 0} if partial else {}

    result = adapter.suggest_atom_correspondence_result(
        model, reactant | catalyst, product | catalyst, fixed
    )

    assert result.error is None
    assert set(result.value) == {(atom_id, atom_id) for atom_id in catalyst}


def test_incompatible_reactive_anchor_is_not_dropped_with_the_catalyst():
    adapter, model, catalyst, reactant, product = _reaction()
    fixed = {atom_id: atom_id for atom_id in catalyst}
    fixed[6] = 11  # Carbon cannot map to the substrate nitrogen.

    result = adapter.suggest_atom_correspondence_result(
        model, reactant | catalyst, product | catalyst, fixed
    )

    assert result.value is None
    assert "existing atom mappings" in result.error


@pytest.mark.parametrize("extra_side", [None, "reactant", "product"])
def test_already_mapped_components_with_no_remaining_match_are_retained(extra_side):
    adapter, model, catalyst, reactant, product = _reaction()
    result = adapter.suggest_atom_correspondence_result(
        model,
        catalyst | (reactant if extra_side == "reactant" else frozenset()),
        catalyst | (product if extra_side == "product" else frozenset()),
        {atom_id: atom_id for atom_id in catalyst},
    )

    assert result.error is None
    assert result.value == [(atom_id, atom_id) for atom_id in sorted(catalyst)]


def test_empty_endpoint_still_reports_an_error():
    adapter, model, catalyst, _reactant, _product = _reaction()
    result = adapter.suggest_atom_correspondence_result(
        model, frozenset(), catalyst, {atom_id: atom_id for atom_id in catalyst}
    )

    assert result.value is None
    assert "reactant endpoint has no included structure" in result.error
