from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from chemvas.bootstrap.calculation_bundle import run
from chemvas.core.document_io import write_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    serialize_model_state,
)

from tests.test_calculation_plan import _document_state

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("rdkit") is None,
    reason="optional RDKit dependency is not installed",
)


def _balanced_state() -> dict[str, object]:
    state = _document_state()
    model = MoleculeModel(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("C", 1.0, 0.0),
            2: Atom("C", 4.0, 0.0),
            3: Atom("C", 5.0, 0.0),
            4: Atom("O", 2.5, 3.0),
            5: Atom("He", 2.5, -3.0),
        },
        bonds=[Bond(0, 1), Bond(2, 3)],
    )
    state["model"] = serialize_model_state(model)
    state["calculation_plan"] = {
        "format": "chemvas-calculation-plan",
        "version": 1,
        "states": [
            {
                "id": "R01",
                "charge": 0,
                "multiplicity": 1,
                "members": [
                    {"component_atom_ids": [0, 1], "inclusion": "included"},
                    {"component_atom_ids": [4], "inclusion": "included"},
                    {"component_atom_ids": [5], "inclusion": "context_only"},
                ],
            },
            {
                "id": "P01",
                "charge": 0,
                "multiplicity": 1,
                "members": [
                    {"component_atom_ids": [2, 3], "inclusion": "included"},
                    {"component_atom_ids": [4], "inclusion": "included"},
                    {"component_atom_ids": [5], "inclusion": "context_only"},
                ],
            },
        ],
        "steps": [
            {
                "id": "S01",
                "reactant": {
                    "state_id": "R01",
                    "roles": [
                        {"component_atom_ids": [0, 1], "role": "reactant"},
                        {"component_atom_ids": [4], "role": "catalyst"},
                        {"component_atom_ids": [5], "role": "spectator"},
                    ],
                },
                "product": {
                    "state_id": "P01",
                    "roles": [
                        {"component_atom_ids": [2, 3], "role": "product"},
                        {"component_atom_ids": [4], "role": "catalyst"},
                        {"component_atom_ids": [5], "role": "spectator"},
                    ],
                },
                "atom_correspondence": [
                    {"reactant_atom_id": 0, "product_atom_id": 2},
                    {"reactant_atom_id": 1, "product_atom_id": 3},
                    {"reactant_atom_id": 4, "product_atom_id": 4},
                ],
            }
        ],
    }
    return state


def _single_component_state() -> dict[str, object]:
    state = _balanced_state()
    plan = state["calculation_plan"]
    plan["states"][0]["members"][1]["inclusion"] = "context_only"  # type: ignore[index]
    plan["states"][1]["members"][1]["inclusion"] = "context_only"  # type: ignore[index]
    plan["steps"][0]["atom_correspondence"].pop()  # type: ignore[index]
    return state


def test_real_rdkit_packs_balanced_multicomponent_step(tmp_path: Path) -> None:
    source = tmp_path / "balanced.chemvas"
    output = tmp_path / "S01.json"
    write_document(source, _balanced_state(), CANVAS_FILE_VERSION)

    assert (
        run(
            [
                "pack-step",
                str(source),
                "--step",
                "S01",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    artifact = json.loads(output.read_text(encoding="utf-8"))
    correspondence = artifact["atom_correspondence"]
    assert correspondence["geometry_mapping"] == "complete_bijection"
    assert len(correspondence["geometry_entries"]) == 11
    assert artifact["reactant"]["structure"]["component_count"] == 2
    assert artifact["reactant"]["structure"]["atom_counts"]["xyz"] == 11
    assert artifact["product"]["structure"]["atom_counts"]["xyz"] == 11
    assert artifact["path_readiness"]["ready_for_path_endpoints"] is False
    assert artifact["endpoint_pair"] is None


def test_real_rdkit_writes_single_component_path_endpoints(tmp_path: Path) -> None:
    source = tmp_path / "single-component.chemvas"
    output = tmp_path / "S01.json"
    write_document(source, _single_component_state(), CANVAS_FILE_VERSION)

    assert (
        run(
            [
                "pack-step",
                str(source),
                "--step",
                "S01",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    artifact = json.loads(output.read_text(encoding="utf-8"))
    endpoint_pair = artifact["endpoint_pair"]
    reactant_symbols = [
        row.split()[0]
        for row in endpoint_pair["endpoints"]["reactant"]["content"].splitlines()[2:]
    ]
    product_symbols = [
        row.split()[0]
        for row in endpoint_pair["endpoints"]["product"]["content"].splitlines()[2:]
    ]
    assert reactant_symbols == product_symbols
    assert endpoint_pair["geometry"]["atom_count"] == 8
    assert len(endpoint_pair["ordering"]["atom_order"]) == 8
