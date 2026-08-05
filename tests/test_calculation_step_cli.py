from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from chemvas.bootstrap import calculation_bundle as cli
from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.calculation_bundle import AtomMapEntry, CalculationArtifacts

from tests.test_calculation_plan import _document_state, _plan


class _StateFakeAdapter:
    last_error: str | None = None

    def model_to_calculation_artifacts(self, model, atom_annotations=None):
        atom_ids = sorted(model.atoms)
        entries = tuple(
            AtomMapEntry(
                xyz_index=index,
                mol_index=index,
                symbol=model.atoms[atom_id].element,
                origin="chemvas_atom",
                chemvas_atom_id=atom_id,
            )
            for index, atom_id in enumerate(atom_ids, start=1)
        )
        xyz_lines = [str(len(entries)), "Chemvas Calculation Bundle v1"]
        xyz_lines.extend(
            f"{entry.symbol} {entry.xyz_index}.0 0.0 0.0" for entry in entries
        )
        return CalculationArtifacts(
            mol_block=f"fake mol for {atom_ids}\n",
            xyz_block="\n".join(xyz_lines) + "\n",
            atom_map=entries,
            rdkit_version="test-rdkit",
            rdkit_formal_charge=0,
            rdkit_radical_electrons=0,
            electron_count=100,
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


def test_attach_and_inspect_plan_create_new_v5_document_without_overwrite(
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


def test_pack_step_creates_paired_state_bundles_mapping_and_bond_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "mechanism.chemvas"
    _write_document_with_plan(source)
    output = tmp_path / "S01"
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
    manifest = json.loads(capsys.readouterr().out)

    assert manifest["format"] == "chemvas-elementary-step-bundle"
    assert manifest["geometry_scope"]["reactant_component_count"] == 2
    assert manifest["geometry_scope"]["interaction_geometry_guarantee"] == (
        "not_provided"
    )
    assert (output / "reactant.bundle" / "geometry.xyz").is_file()
    assert (output / "product.bundle" / "geometry.xyz").is_file()
    correspondence = json.loads((output / "atom_correspondence.json").read_text())
    assert correspondence["source_mapping"] == "complete_bijection"
    assert correspondence["geometry_mapping"] == "complete_bijection"
    assert len(correspondence["geometry_entries"]) == 3
    bond_changes = json.loads((output / "bond_changes.json").read_text())
    assert bond_changes["entries"] == [
        {
            "kind": "order_changed",
            "reactant_atom_ids": [0, 1],
            "product_atom_ids": [2, 3],
            "reactant_order": 2,
            "product_order": 1,
        }
    ]
    for name, metadata in manifest["artifacts"].items():
        content = (output / name).read_bytes()
        assert metadata["sha256"] == hashlib.sha256(content).hexdigest()
        assert metadata["bytes"] == len(content)


def test_pack_step_rejects_incomplete_mapping_before_rdkit_or_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "draft.chemvas"
    _write_document_with_plan(source, complete_mapping=False)
    output = tmp_path / "S01"

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
    output = tmp_path / "S01"

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
