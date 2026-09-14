"""Shared real-CLI workflows for calculation and reviewed-precomplex tests."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from chemvas.bootstrap import calculation_bundle as cli
from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    serialize_model_state,
)
from chemvas.domain.document.precomplex_profile import (
    CURRENT_PROFILE_ID,
    radius_provenance_for,
)
from tests.calculation_artifact_support import _StateFakeAdapter
from tests.calculation_plan_support import _document_state, _plan

if TYPE_CHECKING:
    from pathlib import Path


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


def _generate_candidate_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    source_bond_style: str | None = None,
) -> tuple[Path, Path, dict[str, object]]:
    source = tmp_path / "source.chemvas"
    _write_document_with_plan(source)
    if source_bond_style is not None:
        source_payload = json.loads(source.read_text(encoding="utf-8"))
        source_payload["state"]["model"]["bonds"][1]["style"] = source_bond_style
        source.write_text(json.dumps(source_payload), encoding="utf-8")
        read_document(source)
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    request = tmp_path / "request.json"
    request_payload: dict[str, object] = {
        "format": "chemvas-precomplex-request",
        "version": 2,
        "profile": CURRENT_PROFILE_ID,
        "source_document_sha256": source_sha256,
        "step_id": "S01",
        "candidate_cap": 2,
        "environment": {"kind": "gas_phase"},
        "endpoints": {
            "reactant": {
                "contacts": [
                    {
                        "id": "r-contact",
                        "first_atom_id": 0,
                        "second_atom_id": 4,
                        "target_distance_angstrom": 3.0,
                        "tolerance_angstrom": 0.1,
                    }
                ]
            },
            "product": {
                "contacts": [
                    {
                        "id": "p-contact",
                        "first_atom_id": 3,
                        "second_atom_id": 4,
                        "target_distance_angstrom": 3.0,
                        "tolerance_angstrom": 0.1,
                    }
                ]
            },
        },
    }
    request.write_text(
        json.dumps(request_payload),
        encoding="utf-8",
    )
    output = tmp_path / "candidates.chemvas"
    monkeypatch.setattr(cli, "RDKitAdapter", _StateFakeAdapter)
    assert (
        cli.run(
            [
                "generate-precomplex",
                str(source),
                str(request),
                "--step",
                "S01",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    capsys.readouterr()
    raw = json.loads(output.read_text(encoding="utf-8"))
    for side in ("reactant", "product"):
        precomplex = raw["state"]["calculation_plan"]["steps"][0][side]["precomplex"]
        assert precomplex["profile"] == CURRENT_PROFILE_ID
        assert precomplex["radius_provenance"] == radius_provenance_for(
            CURRENT_PROFILE_ID
        )
    return source, output, raw


def _review_candidate_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    source_bond_style: str | None = None,
) -> tuple[Path, dict[str, object]]:
    _source, candidates, raw = _generate_candidate_fixture(
        tmp_path,
        monkeypatch,
        capsys,
        source_bond_style=source_bond_style,
    )
    step = raw["state"]["calculation_plan"]["steps"][0]
    reviewed = tmp_path / "reviewed.chemvas"
    assert (
        cli.run(
            [
                "select-precomplex",
                str(candidates),
                "--step",
                "S01",
                "--reactant-candidate",
                step["reactant"]["precomplex"]["candidates"][0]["id"],
                "--product-candidate",
                step["product"]["precomplex"]["candidates"][0]["id"],
                "--reviewer",
                "test-reviewer",
                "--output",
                str(reviewed),
            ]
        )
        == 0
    )
    capsys.readouterr()
    payload = json.loads(reviewed.read_text(encoding="utf-8"))
    state = payload["state"]
    assert isinstance(state, dict)
    return reviewed, payload
