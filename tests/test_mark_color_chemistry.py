"""Mark display colors must not change the exported chemical meaning."""

import json
from copy import deepcopy

import pytest

from chemvas.core.molfile import write_molfile
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    build_document_payload,
    calculation_plan_from_state,
    extract_document_state,
    model_bond_pairs,
    serialize_model_state,
)
from chemvas.features.calculation_bundle import (
    inspect_component_inventory,
    precomplex_basis_sha256,
)
from tests.test_calculation_plan import _document_state, _plan


def _mark(kind, atom_id):
    return {
        "kind": kind,
        "text": None,
        "atom_id": atom_id,
        "dx": 7.0 if atom_id is not None else None,
        "dy": -9.0 if atom_id is not None else None,
        "x": 7.0,
        "y": -9.0,
    }


def _basis(state):
    # This is a structural hash regression, not a physically reviewed geometry.
    model = inspect_component_inventory(state).model
    plan = calculation_plan_from_state(
        _plan(), atom_ids=set(model.atoms), bond_pairs=model_bond_pairs(model)
    )
    return precomplex_basis_sha256(
        state,
        plan,
        step_id="S01",
        side="reactant",
        environment={"kind": "gas_phase"},
    )


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
@pytest.mark.parametrize("atom_id", [0, None])
def test_persisted_mark_color_does_not_change_chemistry_or_review_basis(kind, atom_id):
    original = _document_state()
    original["marks"] = [_mark(kind, atom_id)]
    colored = deepcopy(original)
    colored["marks"][0]["color"] = "#Ac3"
    restored = extract_document_state(
        json.loads(json.dumps(build_document_payload(colored, CANVAS_FILE_VERSION)))
    )
    assert restored["marks"][0]["color"] == "#Ac3"

    before = inspect_component_inventory(original)
    after = inspect_component_inventory(restored)
    assert before.components == after.components
    assert serialize_model_state(before.model) == serialize_model_state(after.model)
    assert write_molfile(
        before.model, atom_annotations=before.model.atom_annotations
    ) == write_molfile(after.model, atom_annotations=after.model.atom_annotations)
    assert _basis(original) == _basis(restored)

    # A semantic edit is not mistaken for another display-only change.
    changed = deepcopy(restored)
    changed["marks"][0]["atom_id"] = 0
    changed["marks"][0]["kind"] = (
        "minus" if kind in {"plus", "circled_plus"} else "plus"
    )
    assert _basis(changed) != _basis(restored)
    assert (
        inspect_component_inventory(changed).components
        != inspect_component_inventory(restored).components
    )
