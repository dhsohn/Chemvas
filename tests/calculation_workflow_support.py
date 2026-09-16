"""Shared real-CLI workflows for calculation handoff tests."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from chemvas.core.document_io import write_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    serialize_model_state,
)
from tests.calculation_plan_support import _document_state, _plan

if TYPE_CHECKING:
    from collections.abc import Mapping


def _validate_common_machine(path: Path) -> None:
    validator = os.environ.get("FACTORY_MACHINE_CONTRACT_VALIDATOR")
    if not validator:
        pytest.fail(
            "FACTORY_MACHINE_CONTRACT_VALIDATOR is required for machine.json "
            "conformance assertions"
        )
    subprocess.run([sys.executable, validator, "--machine", str(path)], check=True)


def _write_document_with_plan(path: Path, *, complete_mapping: bool = True) -> None:
    state = _document_state()
    state["calculation_plan"] = _plan(complete_mapping=complete_mapping)
    write_document(path, state, CANVAS_FILE_VERSION)


def _path_ready_state(
    *,
    product_charge: int = 0,
    product_multiplicity: int = 1,
) -> dict[str, object]:
    state = _document_state()
    state["model"] = serialize_model_state(
        MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 1.0, 0.0),
                2: Atom("Me", 4.0, 0.0),
                3: Atom("C", 5.0, 0.0),
                4: Atom("Pt", 2.5, 3.0),
                5: Atom("Cl", 2.5, -3.0),
                6: Atom("Me", 2.0, 0.0),
                7: Atom("C", 6.0, 0.0),
            },
            # Change an explicit C=C bond; both Me abbreviations retain their
            # required single attachment while product atom order is reversed.
            bonds=[
                Bond(0, 1, order=2),
                Bond(1, 6, order=1),
                Bond(2, 3, order=1),
                Bond(3, 7, order=1),
            ],
            atom_annotations=(
                {3: {"formal_charge": product_charge}} if product_charge else {}
            ),
        )
    )
    state["marks"] = [
        {
            "kind": "plus" if product_charge > 0 else "minus",
            "text": "+" if product_charge > 0 else "-",
            "atom_id": 3,
            "dx": None,
            "dy": None,
            "x": 5.0,
            "y": 0.0,
        }
        for _ in range(abs(product_charge))
    ]
    plan = _plan()
    plan["states"][0]["members"][0]["component_atom_ids"] = [0, 1, 6]  # type: ignore[index]
    plan["states"][1]["members"][0]["component_atom_ids"] = [2, 3, 7]  # type: ignore[index]
    plan["states"][0]["members"][1]["inclusion"] = "context_only"  # type: ignore[index]
    plan["states"][1]["members"][1]["inclusion"] = "context_only"  # type: ignore[index]
    plan["states"][1]["charge"] = product_charge  # type: ignore[index]
    plan["states"][1]["multiplicity"] = product_multiplicity  # type: ignore[index]
    plan["steps"][0]["reactant"]["roles"][0]["component_atom_ids"] = [0, 1, 6]  # type: ignore[index]
    plan["steps"][0]["product"]["roles"][0]["component_atom_ids"] = [2, 3, 7]  # type: ignore[index]
    plan["steps"][0]["atom_correspondence"] = [  # type: ignore[index]
        {"reactant_atom_id": 0, "product_atom_id": 7},
        {"reactant_atom_id": 1, "product_atom_id": 3},
        {"reactant_atom_id": 6, "product_atom_id": 2},
    ]
    state["calculation_plan"] = plan
    return state


def _assert_separated_endpoint_geometry(
    artifact: Mapping[str, Any],
    *,
    elements: Mapping[int, str],
    reactant_charge: int,
    product_charge: int,
) -> None:
    """Check pack-step per-component geometry against the canonical atom order.

    Every component row must land on a path atom of the same element and the
    same Chemvas owner, the components of each side must partition the path
    atoms, component charges must add up to the state charge, each embedded XYZ
    must carry a matching digest and byte count, and each reaction-center bond
    change must index the atoms of the changed Chemvas bond. ``elements`` maps
    Chemvas atom ids to generated element symbols.
    """
    geometry = artifact["endpoint_geometry"]
    assert isinstance(geometry, dict)
    atom_order = geometry["ordering"]["atom_order"]
    atom_count = geometry["geometry"]["atom_count"]
    assert [entry["path_index"] for entry in atom_order] == list(range(atom_count))
    assert geometry["geometry"]["intermolecular_arrangement"] == "not_provided"
    assert artifact["geometry_scope"]["interaction_geometry_guarantee"] == (
        "not_provided"
    )
    for side, state_charge in (
        ("reactant", reactant_charge),
        ("product", product_charge),
    ):
        side_geometry = geometry["sides"][side]
        components = side_geometry["components"]
        assert side_geometry["assembly"] == "separated_components"
        assert len(components) == artifact["geometry_scope"][f"{side}_component_count"]
        covered: list[int] = []
        for component in components:
            indices = component["atom_indices"]
            covered.extend(indices)
            content = component["xyz"]["content"]
            encoded = content.encode("utf-8")
            assert component["xyz"]["sha256"] == hashlib.sha256(encoded).hexdigest()
            assert component["xyz"]["bytes"] == len(encoded)
            lines = content.splitlines()
            assert int(lines[0]) == len(indices) == len(lines) - 2
            assert [row.split()[0] for row in lines[2:]] == [
                atom_order[index]["symbol"] for index in indices
            ]
            assert {
                atom_order[index][f"{side}_chemvas_atom_id"] for index in indices
            } == set(component["chemvas_atom_ids"])
            assert component["multiplicity"] is None
            assert component["multiplicity_inference"] == "not_performed"
        assert len(covered) == len(set(covered))
        assert sorted(covered) == list(range(atom_count))
        assert sum(item["formal_charge"] for item in components) == state_charge
    for change in geometry["reaction_center"]["bond_changes"]:
        indices = change["atom_indices"]
        assert [atom_order[index]["symbol"] for index in indices] == [
            elements[atom_id] for atom_id in change["reactant_atom_ids"]
        ]
        assert [atom_order[index]["reactant_chemvas_atom_id"] for index in indices] == (
            change["reactant_atom_ids"]
        )
        assert [atom_order[index]["product_chemvas_atom_id"] for index in indices] == (
            change["product_atom_ids"]
        )


LEGACY_REVIEWED_PRECOMPLEX_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "document-v7"
    / "legacy-reviewed-precomplex.chemvas"
)


def _legacy_reviewed_precomplex_payload() -> dict[str, object]:
    """Return the v7 document whose plan stores a reviewed precomplex pair.

    Chemvas 0.15.0 wrote it through generate-precomplex and select-precomplex.
    Current releases no longer create or use that data but must keep reading and
    preserving it, so the file is a fixed witness and is never regenerated.
    """
    payload = json.loads(LEGACY_REVIEWED_PRECOMPLEX_FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
