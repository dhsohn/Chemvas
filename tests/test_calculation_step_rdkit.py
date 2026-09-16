from __future__ import annotations

import importlib.util
import json
from typing import TYPE_CHECKING

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
from tests.calculation_plan_support import _document_state
from tests.calculation_workflow_support import (
    _assert_separated_endpoint_geometry,
    _validate_common_machine,
)

if TYPE_CHECKING:
    from pathlib import Path

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
        "version": 2,
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
                    "precomplex": {"kind": "none"},
                },
                "product": {
                    "state_id": "P01",
                    "roles": [
                        {"component_atom_ids": [2, 3], "role": "product"},
                        {"component_atom_ids": [4], "role": "catalyst"},
                        {"component_atom_ids": [5], "role": "spectator"},
                    ],
                    "precomplex": {"kind": "none"},
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


def _bond_change_state() -> dict[str, object]:
    """Ethene opens to a CH2(+)-CH2(-) zwitterion next to a water molecule.

    Charges on the product carbons keep two implicit hydrogens on each mapped
    carbon, so the generated atoms stay a bijection across the order change.
    """
    state = _balanced_state()
    charges = {2: 1, 3: -1}
    atoms = {
        0: Atom("C", 0.0, 0.0),
        1: Atom("C", 1.0, 0.0),
        2: Atom("C", 4.0, 0.0),
        3: Atom("C", 5.0, 0.0),
        4: Atom("O", 2.5, 3.0),
        5: Atom("He", 2.5, -3.0),
    }
    state["model"] = serialize_model_state(
        MoleculeModel(
            atoms=atoms,
            bonds=[Bond(0, 1, order=2), Bond(2, 3)],
            atom_annotations={
                atom_id: {"formal_charge": charge}
                for atom_id, charge in charges.items()
            },
        )
    )
    state["marks"] = [
        {
            "kind": "plus" if charge > 0 else "minus",
            "text": "+" if charge > 0 else "-",
            "atom_id": atom_id,
            "dx": None,
            "dy": None,
            "x": atoms[atom_id].x,
            "y": atoms[atom_id].y,
        }
        for atom_id, charge in charges.items()
    ]
    return state


def _pack(source: Path, output: Path) -> dict[str, object]:
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
    observation = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(observation, dict)
    return observation


def test_real_rdkit_packs_balanced_multicomponent_step(tmp_path: Path) -> None:
    source = tmp_path / "balanced.chemvas"
    output = tmp_path / "machine.json"
    write_document(source, _balanced_state(), CANVAS_FILE_VERSION)

    observation = _pack(source, output)

    _validate_common_machine(output)
    artifact = observation["payload"]["data"]
    correspondence = artifact["atom_correspondence"]
    assert correspondence["geometry_mapping"] == "complete_bijection"
    assert len(correspondence["geometry_entries"]) == 11
    assert artifact["reactant"]["structure"]["component_count"] == 2
    assert artifact["reactant"]["structure"]["atom_counts"]["xyz"] == 11
    assert artifact["product"]["structure"]["atom_counts"]["xyz"] == 11
    assert observation["handoff"] == {"status": "ready", "codes": []}
    assert observation["payload"]["contract"]["version"] == 2
    assert artifact["endpoint_geometry"]["geometry"]["atom_count"] == 11
    assert artifact["endpoint_geometry"]["reaction_center"]["bond_changes"] == []
    _assert_separated_endpoint_geometry(
        artifact,
        elements={0: "C", 1: "C", 2: "C", 3: "C", 4: "O"},
        reactant_charge=0,
        product_charge=0,
    )


def test_real_rdkit_embeds_each_component_of_a_bond_change_step(
    tmp_path: Path,
) -> None:
    source = tmp_path / "zwitterion.chemvas"
    output = tmp_path / "machine.json"
    write_document(source, _bond_change_state(), CANVAS_FILE_VERSION)

    observation = _pack(source, output)

    _validate_common_machine(output)
    artifact = observation["payload"]["data"]
    geometry = artifact["endpoint_geometry"]
    assert observation["handoff"] == {"status": "ready", "codes": []}
    # C2H4 + H2O on both sides.
    assert geometry["geometry"]["atom_count"] == 9
    assert [
        (change["reactant_atom_ids"], change["product_atom_ids"], change["kind"])
        for change in geometry["reaction_center"]["bond_changes"]
    ] == [([0, 1], [2, 3], "order_changed")]
    _assert_separated_endpoint_geometry(
        artifact,
        elements={0: "C", 1: "C", 2: "C", 3: "C", 4: "O"},
        reactant_charge=0,
        product_charge=0,
    )
    for side, ethylene_atoms in (("reactant", [0, 1]), ("product", [2, 3])):
        components = geometry["sides"][side]["components"]
        assert [item["chemvas_atom_ids"] for item in components] == [
            ethylene_atoms,
            [4],
        ]
        assert [len(item["atom_indices"]) for item in components] == [6, 3]
        state_generation = artifact[side]["structure"]["geometry_generation"]
        for component in components:
            generation = component["geometry_generation"]
            assert generation["embedding"] == state_generation["embedding"]
            assert generation["random_seed"] == state_generation["random_seed"]


def test_real_rdkit_writes_single_component_path_endpoints(tmp_path: Path) -> None:
    source = tmp_path / "single-component.chemvas"
    output = tmp_path / "machine.json"
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

    observation = json.loads(output.read_text(encoding="utf-8"))
    artifact = observation["payload"]["data"]
    assert observation["handoff"] == {"status": "ready", "codes": []}
    endpoint_geometry = artifact["endpoint_geometry"]
    atom_order = endpoint_geometry["ordering"]["atom_order"]
    for side in ("reactant", "product"):
        side_geometry = endpoint_geometry["sides"][side]
        assert side_geometry["assembly"] == "single_component"
        (component,) = side_geometry["components"]
        symbols = [
            row.split()[0] for row in component["xyz"]["content"].splitlines()[2:]
        ]
        assert sorted(component["atom_indices"]) == list(range(8))
        assert symbols == [
            atom_order[index]["symbol"] for index in component["atom_indices"]
        ]
    assert endpoint_geometry["geometry"]["atom_count"] == 8
    assert len(atom_order) == 8
