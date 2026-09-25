from __future__ import annotations

import hashlib
import json
from copy import deepcopy
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
from chemvas.features.calculation_bundle import AtomMapEntry, CalculationArtifacts
from tests.calculation_artifact_support import _StateFakeAdapter
from tests.calculation_plan_support import _document_state, _plan
from tests.calculation_workflow_support import (
    LEGACY_REVIEWED_PRECOMPLEX_FIXTURE,
    _assert_separated_endpoint_geometry,
    _legacy_reviewed_precomplex_payload,
    _path_ready_state,
    _validate_common_machine,
    _write_document_with_plan,
)

if TYPE_CHECKING:
    from pathlib import Path


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


# Generated element symbols of the synthetic drawing in calculation_plan_support.
_ELEMENTS = {0: "C", 1: "O", 2: "C", 3: "O", 4: "Pt", 5: "Cl"}


def _run_pack_step(source: Path, output: Path) -> None:
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


def _charge_separated_state() -> dict[str, object]:
    """Two charged components on each side whose charges cancel per state."""
    state = _document_state()
    state["calculation_plan"] = _plan()
    charges = {1: -1, 3: -1, 4: 1}
    atoms = {
        0: Atom("C", 0.0, 0.0),
        1: Atom("O", 1.0, 0.0),
        2: Atom("C", 4.0, 0.0),
        3: Atom("O", 5.0, 0.0),
        4: Atom("Pt", 2.5, 3.0),
        5: Atom("Cl", 2.5, -3.0),
    }
    state["model"] = serialize_model_state(
        MoleculeModel(
            atoms=atoms,
            bonds=[Bond(0, 1, order=2), Bond(2, 3, order=1)],
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


def test_pack_step_hands_off_a_two_component_step_as_separated_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "ion-pair.chemvas"
    write_document(source, _charge_separated_state(), CANVAS_FILE_VERSION)
    output = tmp_path / "machine.json"
    monkeypatch.setattr(cli, "RDKitAdapter", _StateFakeAdapter)

    _run_pack_step(source, output)
    observation = json.loads(capsys.readouterr().out)
    artifact = observation["payload"]["data"]

    assert observation == json.loads(output.read_text(encoding="utf-8"))
    _validate_common_machine(output)
    assert observation["handoff"] == {"status": "ready", "codes": []}
    assert observation["payload"]["contract"] == {
        "name": "chemistry/elementary-step",
        "version": 2,
    }
    assert "endpoint_pair" not in artifact
    assert artifact["geometry_scope"]["reactant_component_count"] == 2
    assert artifact["geometry_scope"]["product_component_count"] == 2
    _assert_separated_endpoint_geometry(
        artifact, elements=_ELEMENTS, reactant_charge=0, product_charge=0
    )
    sides = artifact["endpoint_geometry"]["sides"]
    assert [
        (item["chemvas_atom_ids"], item["role"], item["formal_charge"])
        for item in sides["reactant"]["components"]
    ] == [([0, 1], "reactant", -1), ([4], "catalyst", 1)]
    assert [
        (item["chemvas_atom_ids"], item["role"], item["formal_charge"])
        for item in sides["product"]["components"]
    ] == [([2, 3], "product", -1), ([4], "catalyst", 1)]
    assert artifact["endpoint_geometry"]["reaction_center"]["bond_changes"] == [
        {
            "kind": "order_changed",
            "reactant_atom_ids": [0, 1],
            "product_atom_ids": [2, 3],
            "reactant_order": 2,
            "product_order": 1,
            "atom_indices": [0, 1],
        }
    ]
    digest = hashlib.sha256(
        b"chemvas-elementary-step-v2\0" + source.read_bytes() + b"\0S01"
    ).hexdigest()
    assert observation["operation"]["id"] == f"step-{digest}"


def test_pack_step_output_ignores_legacy_reviewed_precomplex_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    legacy_payload = _legacy_reviewed_precomplex_payload()
    legacy = tmp_path / "legacy" / "mechanism.chemvas"
    legacy.parent.mkdir()
    legacy.write_bytes(LEGACY_REVIEWED_PRECOMPLEX_FIXTURE.read_bytes())
    cleared_state = deepcopy(legacy_payload["state"])
    assert isinstance(cleared_state, dict)
    for side in ("reactant", "product"):
        endpoint = cleared_state["calculation_plan"]["steps"][0][side]
        assert endpoint["precomplex"]["kind"] == "candidate_ensemble"
        endpoint["precomplex"] = {"kind": "none"}
    cleared = tmp_path / "cleared" / "mechanism.chemvas"
    cleared.parent.mkdir()
    write_document(cleared, cleared_state, CANVAS_FILE_VERSION)
    monkeypatch.setattr(cli, "RDKitAdapter", _StateFakeAdapter)

    observations = []
    for source in (legacy, cleared):
        output = source.parent / "machine.json"
        _run_pack_step(source, output)
        observations.append(json.loads(capsys.readouterr().out))
        _validate_common_machine(output)
    legacy_observation, cleared_observation = observations

    assert legacy_observation["handoff"] == {"status": "ready", "codes": []}
    assert cleared_observation["handoff"] == legacy_observation["handoff"]
    legacy_data = dict(legacy_observation["payload"]["data"])
    cleared_data = dict(cleared_observation["payload"]["data"])
    assert legacy_data.pop("source") != cleared_data.pop("source")
    assert legacy_data == cleared_data
    assert legacy_data["endpoint_geometry"]["reaction_center"]["bond_changes"]
    _assert_separated_endpoint_geometry(
        legacy_data, elements=_ELEMENTS, reactant_charge=0, product_charge=0
    )


@pytest.mark.parametrize(
    "command", ["generate-precomplex", "inspect-precomplex", "select-precomplex"]
)
def test_removed_precomplex_commands_are_rejected_by_the_parser(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    source = tmp_path / "mechanism.chemvas"
    _write_document_with_plan(source)
    original = source.read_bytes()

    with pytest.raises(SystemExit) as error:
        cli.run([command, str(source)])

    assert error.value.code == 2
    assert f"invalid choice: '{command}'" in capsys.readouterr().err
    assert source.read_bytes() == original
    assert sorted(path.name for path in tmp_path.iterdir()) == ["mechanism.chemvas"]


def test_pack_step_writes_mapping_and_bond_changes_for_a_multicomponent_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "mechanism.chemvas"
    _write_document_with_plan(source)
    output = tmp_path / "machine.json"
    monkeypatch.setattr(cli, "RDKitAdapter", _StateFakeAdapter)

    _run_pack_step(source, output)
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
    assert observation["handoff"] == {"status": "ready", "codes": []}
    assert observation["delivery"] == {"status": "complete", "codes": []}
    assert observation["artifacts"] == {}
    assert observation["payload"]["contract"] == {
        "name": "chemistry/elementary-step",
        "version": 2,
    }
    assert (
        artifact["source"]["document_sha256"]
        == hashlib.sha256(source.read_bytes()).hexdigest()
    )
    assert artifact["geometry_scope"]["reactant_component_count"] == 2
    assert artifact["geometry_scope"]["interaction_geometry_guarantee"] == (
        "not_provided"
    )
    _assert_separated_endpoint_geometry(
        artifact, elements=_ELEMENTS, reactant_charge=0, product_charge=0
    )
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
    endpoint_geometry = artifact["endpoint_geometry"]
    (reactant,) = endpoint_geometry["sides"]["reactant"]["components"]
    (product,) = endpoint_geometry["sides"]["product"]["components"]
    reactant_rows = reactant["xyz"]["content"].splitlines()[2:]
    product_rows = product["xyz"]["content"].splitlines()[2:]

    assert observation == json.loads(output.read_text(encoding="utf-8"))
    _validate_common_machine(output)
    assert observation["handoff"] == {"status": "ready", "codes": []}
    assert observation["payload"]["contract"]["version"] == 2
    for side in ("reactant", "product"):
        assert endpoint_geometry["sides"][side]["assembly"] == "single_component"
    assert [row.split()[0] for row in reactant_rows] == ["C", "C", "C"]
    assert [row.split()[0] for row in product_rows] == ["C", "C", "C"]
    # Component rows keep their own generated order; atom_indices place them
    # on the canonical reactant-ordered path atoms.
    assert reactant["chemvas_atom_ids"] == [0, 1, 6]
    assert reactant["atom_indices"] == [0, 1, 2]
    assert product["chemvas_atom_ids"] == [2, 3, 7]
    assert product["atom_indices"] == [2, 1, 0]
    assert [
        entry["product_xyz_index"]
        for entry in endpoint_geometry["ordering"]["atom_order"]
    ] == [3, 2, 1]
    assert [
        entry["origin"] for entry in endpoint_geometry["ordering"]["atom_order"]
    ] == [
        "chemvas_atom",
        "chemvas_atom",
        "alias_attachment",
    ]
    assert endpoint_geometry["reaction_center"]["atom_indices"] == [0, 1]
    assert [
        change["atom_indices"]
        for change in endpoint_geometry["reaction_center"]["bond_changes"]
    ] == [[0, 1]]
    assert endpoint_geometry["geometry"]["atom_count"] == 3
    for embedded in (reactant["xyz"], product["xyz"]):
        content = embedded["content"].encode("utf-8")
        assert embedded["sha256"] == hashlib.sha256(content).hexdigest()
        assert embedded["bytes"] == len(content)


def test_pack_step_rejects_double_bond_alias_before_rdkit_or_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = _path_ready_state()
    state["model"]["bonds"][1]["order"] = 2  # type: ignore[index]
    source = tmp_path / "invalid-alias.chemvas"
    write_document(source, state, CANVAS_FILE_VERSION)
    source_bytes = source.read_bytes()
    output = tmp_path / "machine.json"

    class _ShouldNotConstruct:
        def __init__(self) -> None:
            raise AssertionError("RDKit must not run for a double-bond Me alias")

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
    captured = capsys.readouterr()
    assert "Alias label 'Me' on atom 6 requires a single attachment bond" in (
        captured.err
    )
    assert captured.out == ""
    assert source.read_bytes() == source_bytes
    assert not output.exists()


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

    _validate_common_machine(output)
    assert observation["handoff"] == {
        "status": "blocked",
        "codes": [
            "chemvas/endpoint_charge_mismatch",
            "chemvas/endpoint_multiplicity_mismatch",
        ],
    }
    assert observation["payload"]["contract"] == {
        "name": "chemistry/elementary-step",
        "version": 2,
    }
    assert "endpoint_pair" not in artifact
    assert artifact["endpoint_geometry"] is None
    assert artifact["geometry_scope"]["interaction_geometry_guarantee"] == (
        "not_provided"
    )
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


def test_attach_plan_enforces_output_byte_limit_before_publication(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "source.chemvas"
    write_document(source, _document_state(), CANVAS_FILE_VERSION)
    original = source.read_bytes()
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(_plan()), encoding="utf-8")
    reference = tmp_path / "reference.chemvas"
    args = ["attach-plan", str(source), str(plan), "--output"]
    assert cli.run([*args, str(reference)]) == 0
    expected = reference.read_bytes()
    capsys.readouterr()
    output = tmp_path / "candidate.chemvas"
    monkeypatch.setattr(cli, "MAX_DOCUMENT_BYTES", len(expected) - 1)
    with pytest.raises(SystemExit) as exc:
        cli.run([*args, str(output)])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "byte limit" in captured.err
    assert not captured.out
    assert not output.exists()
    assert source.read_bytes() == original
    monkeypatch.setattr(cli, "MAX_DOCUMENT_BYTES", len(expected))
    assert cli.run([*args, str(output)]) == 0
    assert output.read_bytes() == expected


def test_attach_plan_rejects_oversized_input_before_decoding(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "source.chemvas"
    write_document(source, _document_state(), CANVAS_FILE_VERSION)
    original = source.read_bytes()
    plan = tmp_path / "plan.json"
    plan.write_bytes(b" " * 65)
    output = tmp_path / "candidate.chemvas"
    monkeypatch.setattr(cli, "MAX_DOCUMENT_BYTES", 64)
    with pytest.raises(SystemExit) as exc:
        cli.run(["attach-plan", str(source), str(plan), "--output", str(output)])
    assert exc.value.code == 2
    assert "calculation plan exceeds the 64-byte limit" in capsys.readouterr().err
    assert not output.exists()
    assert source.read_bytes() == original
