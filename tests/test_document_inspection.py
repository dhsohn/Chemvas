from __future__ import annotations

import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from textwrap import dedent

import pytest

from chemvas.domain.document import Atom, Bond, MoleculeModel, serialize_model_state
from chemvas.domain.document.inspection import (
    component_inventory,
    document_model,
    inspect_component_inventory,
    inspect_components,
)
from tests.subprocess_support import source_subprocess_env


def _state(kinds=(), annotation=None):
    model = MoleculeModel(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("N", 18.0, 0.0)},
        bonds=[Bond(0, 1)],
    )
    state = {
        "model": serialize_model_state(model),
        "marks": [{"atom_id": 1, "kind": kind} for kind in kinds],
    }
    if annotation is not None:
        # Literal input matters: the writer normally omits numerical zeroes.
        state["model"]["atom_annotations"] = {1: annotation}
    return state


@pytest.mark.parametrize(
    ("kinds", "annotation", "effective", "charge", "radicals"),
    [
        (("plus", "minus"), None, {"formal_charge": 0}, 0, 0),
        (
            ("circled_plus", "circled_minus"),
            {"formal_charge": 0},
            {"formal_charge": 0},
            0,
            0,
        ),
        (
            ("radical", "radical"),
            {"radical_electrons": 2},
            {"radical_electrons": 2},
            0,
            2,
        ),
        (
            ("plus", "radical"),
            {"formal_charge": 1, "radical_electrons": 1},
            {"formal_charge": 1, "radical_electrons": 1},
            1,
            1,
        ),
    ],
)
def test_effective_electronic_annotations_preserve_presence_and_totals(
    kinds, annotation, effective, charge, radicals
):
    state = _state(kinds, annotation)
    before = deepcopy(state)

    inventory = inspect_component_inventory(state)

    assert inventory.model.atom_annotations == {1: effective}
    assert inventory.components == inspect_components(state)
    assert inventory.components[0].atom_ids == (0, 1)
    assert inventory.components[0].bond_count == 1
    assert inventory.components[0].formula_labels == (("C", 1), ("N", 1))
    assert inventory.components[0].formal_charge == charge
    assert inventory.components[0].radical_electrons == radicals
    assert state == before


@pytest.mark.parametrize("field", ["formal_charge", "radical_electrons"])
def test_literal_zero_without_visible_electronic_marks_is_still_a_conflict(field):
    state = _state(annotation={field: 0})
    before = deepcopy(state)

    with pytest.raises(ValueError, match="Conflicting charge/radical annotations"):
        inspect_components(state)

    assert state == before


@pytest.mark.parametrize(
    ("marks", "annotation", "message"),
    [
        ("invalid", None, "marks are invalid"),
        ([None], None, "mark entry is invalid"),
        ([{"atom_id": 9, "kind": "plus"}], None, "mark atom is invalid"),
        ([{"atom_id": 1, "kind": None}], None, "mark kind is invalid"),
        (
            [{"atom_id": 1, "kind": "plus"}],
            {"formal_charge": -1},
            "Conflicting charge/radical annotations",
        ),
        (
            [{"atom_id": 1, "kind": "radical"}],
            {"radical_electrons": 2},
            "Conflicting charge/radical annotations",
        ),
    ],
)
def test_annotation_errors_keep_priority_over_unrelated_alias_errors(
    marks, annotation, message
):
    state = _state(annotation=annotation)
    state["marks"] = marks
    state["model"]["atoms"][2] = {
        "element": "PPh3",
        "x": 90.0,
        "y": 0.0,
        "color": "#000000",
        "explicit_label": True,
    }
    before = deepcopy(state)

    with pytest.raises(ValueError, match=message):
        inspect_component_inventory(state)

    assert state == before


def test_standalone_calculation_selection_does_not_inspect_unselected_alias():
    from chemvas.features.calculation_bundle import select_components

    model = MoleculeModel(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("C", 18.0, 0.0),
            2: Atom("PPh3", 90.0, 0.0),
        },
        bonds=[Bond(0, 1)],
    )
    state = {"model": serialize_model_state(model), "marks": []}
    before = deepcopy(state)

    with pytest.raises(ValueError, match="PPh3"):
        inspect_components(state)
    selection = select_components(state, [[0, 1]])
    assert selection.atom_ids == (0, 1)
    assert selection.formal_charge == 0
    with pytest.raises(ValueError, match="PPh3"):
        select_components(state, [[2]])
    assert state == before


def test_inventory_reuses_only_the_supplied_request_local_model():
    state = _state(("plus",), {"formal_charge": 1})
    before = deepcopy(state)
    model = document_model(state)

    first = component_inventory(state, model)

    assert first.model is model
    assert first.components == inspect_components(state)
    assert state == before
    state["model"]["atoms"][1]["x"] = 36.0
    state["model"]["atom_annotations"] = {1: {"formal_charge": -1}}
    state["marks"][0]["kind"] = "minus"
    second = inspect_component_inventory(state)
    assert first.model.atoms[1].x == 18.0
    assert first.components[0].bounds == (0.0, 0.0, 18.0, 0.0)
    assert first.components[0].formal_charge == 1
    assert second.model is not model
    assert second.components[0].bounds == (0.0, 0.0, 36.0, 0.0)
    assert second.components[0].formal_charge == -1
    model.atoms[1].x = -100.0
    assert state["model"]["atoms"][1]["x"] == 36.0
    assert second.model.atoms[1].x == 36.0


_PURE_INSPECTION = dedent(
    """
    import importlib.abc
    import json
    import sys
    from copy import deepcopy

    operation = sys.argv[1]
    forbidden = (
        "chemvas.features.calculation_bundle",
        "chemvas.bootstrap.calculation_bundle",
        "rdkit",
    )
    if operation == "inventory":
        forbidden += ("PyQt6",)
    def blocked(name):
        return any(name == root or name.startswith(root + ".") for root in forbidden)

    class RejectOptionalDependencies(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if blocked(fullname):
                raise AssertionError("unexpected dependency: " + fullname)

    assert not any(blocked(name) for name in sys.modules)
    sys.meta_path.insert(0, RejectOptionalDependencies())
    from chemvas.core.document_io import read_document
    document = read_document(sys.argv[2])
    state = document.state
    before = deepcopy(state)
    if operation == "inventory":
        from chemvas.domain.document.inspection import inspect_components
        components = inspect_components(state)
        assert len(components) == 1 and components[0].atom_ids == (0, 1)
    elif operation == "compose":
        from chemvas.features.document_composition import compose_document_state
        result = compose_document_state({
            "format": "chemvas-document-composition", "version": 1,
            "atoms": [
                {"id": 0, "element": "C", "x": 0.0, "y": 0.0},
                {"id": 1, "element": "O", "x": 18.0, "y": 0.0},
            ],
            "bonds": [{"a": 0, "b": 1, "order": 1}],
        })
        assert len(result["model"]["atoms"]) == 2
    elif operation == "inspect":
        from chemvas.features.document_patch import inspect_document_graph
        report = inspect_document_graph(state)
        assert report["atom_count"] == 2 and report["bond_count"] == 1
    elif operation == "patch":
        from chemvas.features.document_patch import apply_document_patch
        result = apply_document_patch(state, {
            "format": "chemvas-graph-patch", "version": 1,
            "source_sha256": document.source_sha256,
            "operations": [{"op": "update_atom", "atom_id": 0,
                            "changes": {"color": "#123456"}}],
        }, source_sha256=document.source_sha256, document_version=7)
        expected = deepcopy(state)
        expected["model"]["atoms"]["0"]["color"] = "#123456"
        assert json.loads(json.dumps(result.state)) == expected
    elif operation == "template-source":
        from chemvas.bootstrap.document_template import validate_template_request
        request = validate_template_request(state, {
            "format": "chemvas-template-insertion", "version": 1,
            "source_sha256": document.source_sha256,
            "ring_size": 6, "style": "regular", "position": [100.0, 100.0],
            "anchor": {"kind": "free"},
        }, source_sha256=document.source_sha256)
        assert request.ring_size == 6
    else:
        raise AssertionError(operation)
    assert state == before
    assert not any(blocked(name) for name in sys.modules)
    print(operation + " without calculation or RDKit")
    """
)


@pytest.mark.parametrize(
    "operation", ["inventory", "compose", "inspect", "patch", "template-source"]
)
def test_generic_inspection_consumers_do_not_import_calculation_or_optional_backends(
    operation,
):
    fixture = Path(__file__).parent / "fixtures" / "document-v7" / "minimal.chemvas"
    result = subprocess.run(
        [sys.executable, "-c", _PURE_INSPECTION, operation, str(fixture)],
        env=source_subprocess_env({"PYTHONDONTWRITEBYTECODE": "1"}),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == operation + " without calculation or RDKit"
