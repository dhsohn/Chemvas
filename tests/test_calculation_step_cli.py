from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

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
from chemvas.features.calculation_bundle import AtomMapEntry, CalculationArtifacts

from tests.test_calculation_plan import _document_state, _plan


def _validate_common_machine(path: Path) -> None:
    validator = os.environ.get("FACTORY_MACHINE_CONTRACT_VALIDATOR")
    if not validator:
        pytest.fail(
            "FACTORY_MACHINE_CONTRACT_VALIDATOR is required for machine.json "
            "conformance assertions"
        )
    subprocess.run([sys.executable, validator, "--machine", str(path)], check=True)


class _StateFakeAdapter:
    last_error: str | None = None

    def model_to_calculation_artifacts(self, model, atom_annotations=None):
        formal_charge = sum(
            values.get("formal_charge", 0)
            for values in (atom_annotations or {}).values()
        )
        atom_ids = sorted(model.atoms)
        entries = tuple(
            AtomMapEntry(
                xyz_index=index,
                mol_index=index,
                symbol=(
                    "C"
                    if model.atoms[atom_id].element == "Me"
                    else model.atoms[atom_id].element
                ),
                origin=(
                    "alias_attachment"
                    if model.atoms[atom_id].element == "Me"
                    else "chemvas_atom"
                ),
                chemvas_atom_id=atom_id,
            )
            for index, atom_id in enumerate(atom_ids, start=1)
        )
        xyz_lines = [str(len(entries)), "Chemvas geometry v1"]
        xyz_lines.extend(
            f"{entry.symbol} {entry.xyz_index}.0 0.0 0.0" for entry in entries
        )
        return CalculationArtifacts(
            mol_block=f"fake mol for {atom_ids}\n",
            xyz_block="\n".join(xyz_lines) + "\n",
            atom_map=entries,
            rdkit_version="test-rdkit",
            rdkit_formal_charge=formal_charge,
            rdkit_radical_electrons=0,
            electron_count=100 - formal_charge,
            geometry_embedding="ETKDGv3",
            geometry_random_seed=0xC0FFEE,
            geometry_optimization_policy="test",
            geometry_optimization_result="test_converged",
            mol_atom_count=len(entries),
            xyz_atom_count=len(entries),
        )


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
                1: Atom("Me", 1.0, 0.0),
                2: Atom("Me", 4.0, 0.0),
                3: Atom("C", 5.0, 0.0),
                4: Atom("Pt", 2.5, 3.0),
                5: Atom("Cl", 2.5, -3.0),
            },
            bonds=[Bond(0, 1, order=2), Bond(2, 3, order=1)],
            atom_annotations=(
                {2: {"formal_charge": product_charge}} if product_charge else {}
            ),
        )
    )
    state["marks"] = [
        {
            "kind": "plus" if product_charge > 0 else "minus",
            "text": "+" if product_charge > 0 else "-",
            "atom_id": 2,
            "dx": None,
            "dy": None,
            "x": 4.0,
            "y": 0.0,
        }
        for _ in range(abs(product_charge))
    ]
    plan = _plan()
    plan["states"][0]["members"][1]["inclusion"] = "context_only"  # type: ignore[index]
    plan["states"][1]["members"][1]["inclusion"] = "context_only"  # type: ignore[index]
    plan["states"][1]["charge"] = product_charge  # type: ignore[index]
    plan["states"][1]["multiplicity"] = product_multiplicity  # type: ignore[index]
    plan["steps"][0]["atom_correspondence"] = [  # type: ignore[index]
        {"reactant_atom_id": 0, "product_atom_id": 3},
        {"reactant_atom_id": 1, "product_atom_id": 2},
    ]
    state["calculation_plan"] = plan
    return state


def test_attach_and_inspect_plan_create_current_document_without_overwrite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "scheme.chemvas"
    write_document(source, _document_state(), CANVAS_FILE_VERSION)
    original = source.read_bytes()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
    output = tmp_path / "mechanism.chemvas"

    assert (
        cli.run(
            [
                "attach-plan",
                str(source),
                str(plan_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    attachment = json.loads(capsys.readouterr().out)
    document = read_document(output)

    assert source.read_bytes() == original
    assert attachment["state_count"] == 2
    assert attachment["step_count"] == 1
    assert document.payload["version"] == CANVAS_FILE_VERSION
    assert document.state["calculation_plan"]["steps"][0]["id"] == "S01"

    assert cli.run(["inspect-plan", str(output)]) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["steps"][0]["readiness"]["ready_for_step_pack"] is True

    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "attach-plan",
                str(source),
                str(plan_path),
                "--output",
                str(output),
            ]
        )
    assert error.value.code == 2


def test_attach_plan_rejects_duplicate_json_keys_without_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "scheme.chemvas"
    write_document(source, _document_state(), CANVAS_FILE_VERSION)
    source_bytes = source.read_bytes()
    plan_text = json.dumps(_plan(), separators=(",", ":"))
    version_field = '"version":2'
    assert version_field in plan_text
    plan_path = tmp_path / "duplicate-plan.json"
    plan_path.write_text(
        plan_text.replace(version_field, '"version":999,"version":2', 1),
        encoding="utf-8",
    )
    output = tmp_path / "must-not-exist.chemvas"

    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "attach-plan",
                str(source),
                str(plan_path),
                "--output",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert "Invalid Calculation Plan JSON file" in capsys.readouterr().err
    assert source.read_bytes() == source_bytes
    assert not output.exists()


def test_pack_step_writes_one_blocked_artifact_with_mapping_and_bond_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "mechanism.chemvas"
    _write_document_with_plan(source)
    output = tmp_path / "machine.json"
    monkeypatch.setattr(cli, "RDKitAdapter", _StateFakeAdapter)

    assert (
        cli.run(
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
    observation = json.loads(capsys.readouterr().out)
    artifact = observation["payload"]["data"]

    assert observation == json.loads(output.read_text(encoding="utf-8"))
    _validate_common_machine(output)
    assert output.is_file()
    assert observation["contract"] == {
        "name": "factory/machine-observation",
        "version": 1,
    }
    assert observation["producer"]["name"] == "chemvas"
    assert observation["operation"]["kind"] == "chemistry/elementary-step-export"
    assert observation["lifecycle"] == {
        "phase": "finished",
        "outcome": "succeeded",
        "codes": [],
    }
    assert observation["handoff"] == {
        "status": "blocked",
        "codes": ["chemvas/multicomponent_precomplex_geometry_not_provided"],
    }
    assert observation["delivery"] == {"status": "complete", "codes": []}
    assert observation["artifacts"] == {}
    assert observation["payload"]["contract"] == {
        "name": "chemistry/elementary-step",
        "version": 1,
    }
    assert (
        artifact["source"]["document_sha256"]
        == hashlib.sha256(source.read_bytes()).hexdigest()
    )
    assert artifact["geometry_scope"]["reactant_component_count"] == 2
    assert artifact["geometry_scope"]["interaction_geometry_guarantee"] == (
        "not_provided"
    )
    assert artifact["endpoint_pair"] is None
    correspondence = artifact["atom_correspondence"]
    assert correspondence["source_mapping"] == "complete_bijection"
    assert correspondence["geometry_mapping"] == "complete_bijection"
    assert len(correspondence["geometry_entries"]) == 3
    bond_changes = artifact["bond_changes"]
    assert bond_changes["entries"] == [
        {
            "kind": "order_changed",
            "reactant_atom_ids": [0, 1],
            "product_atom_ids": [2, 3],
            "reactant_order": 2,
            "product_order": 1,
        }
    ]
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "machine.json",
        "mechanism.chemvas",
    ]


def test_pack_step_writes_identity_ordered_path_endpoints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "path-ready.chemvas"
    write_document(source, _path_ready_state(), CANVAS_FILE_VERSION)
    output = tmp_path / "machine.json"
    monkeypatch.setattr(cli, "RDKitAdapter", _StateFakeAdapter)

    assert (
        cli.run(
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
    observation = json.loads(capsys.readouterr().out)
    artifact = observation["payload"]["data"]
    endpoint_pair = artifact["endpoint_pair"]
    reactant = endpoint_pair["endpoints"]["reactant"]
    product = endpoint_pair["endpoints"]["product"]
    reactant_rows = reactant["content"].splitlines()[2:]
    product_rows = product["content"].splitlines()[2:]

    assert observation == json.loads(output.read_text(encoding="utf-8"))
    _validate_common_machine(output)
    assert observation["handoff"] == {"status": "ready", "codes": []}
    assert [row.split()[0] for row in reactant_rows] == ["C", "C"]
    assert [row.split()[0] for row in product_rows] == ["C", "C"]
    assert [float(row.split()[1]) for row in product_rows] == [2.0, 1.0]
    assert [
        entry["product_xyz_index"] for entry in endpoint_pair["ordering"]["atom_order"]
    ] == [2, 1]
    assert [entry["origin"] for entry in endpoint_pair["ordering"]["atom_order"]] == [
        "chemvas_atom",
        "alias_attachment",
    ]
    assert endpoint_pair["reaction_center"]["atom_indices"] == [0, 1]
    for embedded in (reactant, product):
        content = embedded["content"].encode("utf-8")
        assert embedded["sha256"] == hashlib.sha256(content).hexdigest()
        assert embedded["bytes"] == len(content)


def test_pack_step_writes_blocked_artifact_when_endpoint_electronic_state_differs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "spin-change.chemvas"
    write_document(
        source,
        _path_ready_state(product_charge=1, product_multiplicity=2),
        CANVAS_FILE_VERSION,
    )
    output = tmp_path / "machine.json"
    monkeypatch.setattr(cli, "RDKitAdapter", _StateFakeAdapter)

    assert (
        cli.run(
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
    observation = json.loads(capsys.readouterr().out)
    artifact = observation["payload"]["data"]

    assert observation["handoff"] == {
        "status": "blocked",
        "codes": [
            "chemvas/endpoint_charge_mismatch",
            "chemvas/endpoint_multiplicity_mismatch",
        ],
    }
    assert artifact["endpoint_pair"] is None
    assert output.is_file()


def test_pack_step_rejects_incomplete_mapping_before_rdkit_or_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "draft.chemvas"
    _write_document_with_plan(source, complete_mapping=False)
    output = tmp_path / "machine.json"

    class _ShouldNotConstruct:
        def __init__(self) -> None:
            raise AssertionError("RDKit must not run for an incomplete plan")

    monkeypatch.setattr(cli, "RDKitAdapter", _ShouldNotConstruct)
    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "pack-step",
                str(source),
                "--step",
                "S01",
                "--output",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert not output.exists()


def test_pack_step_rejects_generated_hydrogen_mismatch_without_partial_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "mechanism.chemvas"
    _write_document_with_plan(source)
    output = tmp_path / "machine.json"

    class _HydrogenMismatchAdapter(_StateFakeAdapter):
        def model_to_calculation_artifacts(self, model, atom_annotations=None):
            artifacts = super().model_to_calculation_artifacts(
                model, atom_annotations=atom_annotations
            )
            if 0 not in model.atoms:
                return artifacts
            entries = artifacts.atom_map + (
                AtomMapEntry(
                    xyz_index=artifacts.xyz_atom_count + 1,
                    mol_index=None,
                    symbol="H",
                    origin="implicit_hydrogen",
                    chemvas_atom_id=None,
                    parent_xyz_index=1,
                    parent_chemvas_atom_id=0,
                ),
            )
            xyz_lines = artifacts.xyz_block.splitlines()
            xyz_lines[0] = str(artifacts.xyz_atom_count + 1)
            xyz_lines.append("H 0.0 0.0 1.0")
            return CalculationArtifacts(
                mol_block=artifacts.mol_block,
                xyz_block="\n".join(xyz_lines) + "\n",
                atom_map=entries,
                rdkit_version=artifacts.rdkit_version,
                rdkit_formal_charge=artifacts.rdkit_formal_charge,
                rdkit_radical_electrons=artifacts.rdkit_radical_electrons,
                electron_count=artifacts.electron_count,
                geometry_embedding=artifacts.geometry_embedding,
                geometry_random_seed=artifacts.geometry_random_seed,
                geometry_optimization_policy=artifacts.geometry_optimization_policy,
                geometry_optimization_result=artifacts.geometry_optimization_result,
                mol_atom_count=artifacts.mol_atom_count,
                xyz_atom_count=artifacts.xyz_atom_count + 1,
            )

    monkeypatch.setattr(cli, "RDKitAdapter", _HydrogenMismatchAdapter)
    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "pack-step",
                str(source),
                "--step",
                "S01",
                "--output",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert not output.exists()
