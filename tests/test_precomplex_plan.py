from __future__ import annotations

import hashlib
import json

import pytest
from chemvas.core.document_io import create_document
from chemvas.domain.document import (
    CALCULATION_PLAN_CANVAS_FILE_VERSION,
    PRECOMPLEX_CANVAS_FILE_VERSION,
    calculation_plan_to_state,
)
from chemvas.features.calculation_bundle import (
    plan_with_replaced_step,
    validate_calculation_plan,
)

from tests.test_calculation_plan import _document_state, _plan


def test_calculation_plan_v2_round_trips_explicit_empty_precomplex_endpoints() -> None:
    document_state = _document_state()
    plan_state = _plan()
    plan_state["version"] = 2
    for step in plan_state["steps"]:
        step["reactant"]["precomplex"] = {"kind": "none"}
        step["product"]["precomplex"] = {"kind": "none"}

    parsed = validate_calculation_plan(document_state, plan_state)

    assert parsed.version == 2
    assert parsed.steps[0].reactant.precomplex.kind == "none"
    assert parsed.steps[0].product.precomplex.kind == "none"
    assert calculation_plan_to_state(parsed) == plan_state


def test_plan_v2_requires_precomplex_document_version() -> None:
    document_state = _document_state()
    plan_state = _plan()
    plan_state["version"] = 2
    for step in plan_state["steps"]:
        step["reactant"]["precomplex"] = {"kind": "none"}
        step["product"]["precomplex"] = {"kind": "none"}
    document_state["calculation_plan"] = plan_state

    document = create_document(document_state, PRECOMPLEX_CANVAS_FILE_VERSION)

    assert document.payload["version"] == PRECOMPLEX_CANVAS_FILE_VERSION
    with pytest.raises(ValueError, match="Failed to save"):
        create_document(document_state, CALCULATION_PLAN_CANVAS_FILE_VERSION)


def test_plan_v2_round_trips_bounded_candidate_ensemble() -> None:
    plan_state = _plan()
    plan_state["version"] = 2
    xyz = (
        "2\nChemvas chemvas-rigid-precomplex-placement/1 S01 reactant\n"
        "C 0.00000000 0.00000000 0.00000000\n"
        "O 3.00000000 0.00000000 0.00000000\n"
    )
    candidate = {
        "id": "pc-" + "a" * 64,
        "geometry_class": "generated_candidate_ensemble",
        "xyz": xyz,
        "xyz_sha256": hashlib.sha256(xyz.encode("ascii")).hexdigest(),
        "transform": {
            "approach_index": 0,
            "rotation_index": 0,
            "approach_vector": [1.0, 0.0, 0.0],
        },
        "component_conformer_ids": ["conf-" + "c" * 64, "conf-" + "d" * 64],
        "validation": {
            "hard_clash_count": 0,
            "soft_overlap_score": 0.0,
            "contact_error_angstrom": 0.0,
            "limiting_pair": None,
            "limiting_distance_angstrom": None,
            "limiting_threshold_angstrom": None,
        },
    }
    precomplex = {
        "kind": "candidate_ensemble",
        "source_document_sha256": "a" * 64,
        "basis_sha256": "b" * 64,
        "side": "reactant",
        "profile": "chemvas-rigid-precomplex-placement/1",
        "environment": {"kind": "gas_phase"},
        "contacts": [
            {
                "id": "contact-1",
                "first_atom_id": 0,
                "second_atom_id": 4,
                "target_distance_angstrom": 3.0,
                "tolerance_angstrom": 0.1,
            }
        ],
        "source_geometry": {
            "rdkit_version": "test-rdkit",
            "rdkit_formal_charge": 0,
            "rdkit_radical_electrons": 0,
            "electron_count": 12,
            "geometry_embedding": "ETKDGv3",
            "geometry_random_seed": 7,
            "geometry_optimization_policy": "MMFF94s",
            "geometry_optimization_result": "MMFF_converged",
            "mol_atom_count": 2,
            "xyz_atom_count": 2,
            "atom_map": [
                {
                    "xyz_index": 1,
                    "mol_index": 1,
                    "symbol": "C",
                    "origin": "chemvas_atom",
                    "chemvas_atom_id": 0,
                    "parent_xyz_index": None,
                    "parent_chemvas_atom_id": None,
                },
                {
                    "xyz_index": 2,
                    "mol_index": 2,
                    "symbol": "O",
                    "origin": "chemvas_atom",
                    "chemvas_atom_id": 4,
                    "parent_xyz_index": None,
                    "parent_chemvas_atom_id": None,
                },
            ],
        },
        "candidates": [candidate],
        "selection": None,
    }
    identity = {
        "profile": precomplex["profile"],
        "source_sha256": precomplex["source_document_sha256"],
        "plan_sha256": precomplex["basis_sha256"],
        "step_id": "S01",
        "side": "reactant",
        "contacts": precomplex["contacts"],
        "component_atom_ids": [[0, 1], [4]],
        "component_conformer_ids": candidate["component_conformer_ids"],
        "approach_index": 0,
        "rotation_index": 0,
        "xyz_sha256": candidate["xyz_sha256"],
    }
    candidate["id"] = (
        "pc-"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("ascii")
        ).hexdigest()
    )
    plan_state["steps"][0]["reactant"]["precomplex"] = precomplex
    plan_state["steps"][0]["product"]["precomplex"] = {"kind": "none"}

    parsed = validate_calculation_plan(_document_state(), plan_state)

    assert parsed.steps[0].reactant.precomplex.kind == "candidate_ensemble"
    assert calculation_plan_to_state(parsed) == plan_state

    replaced = plan_with_replaced_step(
        _document_state(),
        current_plan_state=calculation_plan_to_state(parsed),
        reactant_state=next(state for state in parsed.states if state.id == "R01"),
        product_state=next(state for state in parsed.states if state.id == "P01"),
        step=parsed.steps[0],
    )
    assert replaced.version == 2
    assert calculation_plan_to_state(replaced) == plan_state
