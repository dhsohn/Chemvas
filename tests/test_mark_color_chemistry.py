"""Mark display colors must not change the exported chemical meaning."""

import json
from copy import deepcopy

import pytest

from chemvas.core.molfile import write_molfile
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    build_document_payload,
    extract_document_state,
    serialize_model_state,
)
from chemvas.domain.document.inspection import inspect_component_inventory
from chemvas.features.calculation_bundle import select_components
from tests.calculation_plan_support import _document_state


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


def _calculation_input(state):
    # The reactant calculation selection carries the modeled charge, radical
    # electrons and annotated model that pack-step hands to RDKit.
    return select_components(state, [[0, 1]])


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
@pytest.mark.parametrize("atom_id", [0, None])
def test_persisted_mark_color_does_not_change_chemistry_or_calculation_input(
    kind, atom_id
):
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
    assert _calculation_input(original) == _calculation_input(restored)

    # A semantic edit is not mistaken for another display-only change.
    changed = deepcopy(restored)
    changed["marks"][0]["atom_id"] = 0
    changed["marks"][0]["kind"] = (
        "minus" if kind in {"plus", "circled_plus"} else "plus"
    )
    assert _calculation_input(changed) != _calculation_input(restored)
    assert (
        inspect_component_inventory(changed).components
        != inspect_component_inventory(restored).components
    )
