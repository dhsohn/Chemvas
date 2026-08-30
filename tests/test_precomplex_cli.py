from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from chemvas.bootstrap import calculation_bundle as cli
from chemvas.bootstrap import document_patch as patch_cli
from chemvas.core.document_io import read_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.domain.document.precomplex_profile import (
    CURRENT_PROFILE_ID,
    radius_provenance_for,
)
from tests.test_calculation_step_cli import _StateFakeAdapter, _write_document_with_plan


def test_generate_precomplex_creates_non_overwriting_plan_v2_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "mechanism.chemvas"
    _write_document_with_plan(source)
    source_bytes = source.read_bytes()
    request_path = tmp_path / "precomplex-request.json"
    request_payload: dict[str, object] = {
        "format": "chemvas-precomplex-request",
        "version": 2,
        "profile": CURRENT_PROFILE_ID,
        "source_document_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "step_id": "S01",
        "candidate_cap": 4,
        "environment": {"kind": "gas_phase"},
        "endpoints": {
            "reactant": {
                "contacts": [
                    {
                        "id": "reactant-contact",
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
                        "id": "product-contact",
                        "first_atom_id": 3,
                        "second_atom_id": 4,
                        "target_distance_angstrom": 3.0,
                        "tolerance_angstrom": 0.1,
                    }
                ]
            },
        },
    }
    request_path.write_text(
        json.dumps(request_payload),
        encoding="utf-8",
    )
    output = tmp_path / "mechanism-precomplex.chemvas"
    monkeypatch.setattr(cli, "RDKitAdapter", _StateFakeAdapter)

    assert (
        cli.run(
            [
                "generate-precomplex",
                str(source),
                str(request_path),
                "--step",
                "S01",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    report = json.loads(capsys.readouterr().out)
    document = read_document(output)
    plan = document.state["calculation_plan"]
    step = plan["steps"][0]
    assert source.read_bytes() == source_bytes
    assert document.payload["version"] == CANVAS_FILE_VERSION
    assert plan["version"] == 2
    assert report["format"] == "chemvas-precomplex-generation"
    assert report["step_id"] == "S01"
    assert report["profile"] == CURRENT_PROFILE_ID
    assert report["radius_provenance"] == radius_provenance_for(CURRENT_PROFILE_ID)
    assert report["candidate_counts"] == {"reactant": 4, "product": 4}
    for side in ("reactant", "product"):
        precomplex = step[side]["precomplex"]
        assert precomplex["kind"] == "candidate_ensemble"
        assert precomplex["profile"] == CURRENT_PROFILE_ID
        assert precomplex["radius_provenance"] == radius_provenance_for(
            CURRENT_PROFILE_ID
        )
        assert len(precomplex["candidates"]) == 4
        assert precomplex["selection"] is None
        assert all(
            item["geometry_class"] == "generated_candidate_ensemble"
            for item in precomplex["candidates"]
        )

    assert (
        cli.run(
            [
                "inspect-precomplex",
                str(output),
                "--step",
                "S01",
            ]
        )
        == 0
    )
    preview = json.loads(capsys.readouterr().out)
    assert preview["format"] == "chemvas-precomplex-inspection"
    assert preview["endpoints"]["reactant"]["profile"] == CURRENT_PROFILE_ID
    assert preview["placement_profiles"] == {
        "reactant": {
            "id": CURRENT_PROFILE_ID,
            "radius_provenance": radius_provenance_for(CURRENT_PROFILE_ID),
        },
        "product": {
            "id": CURRENT_PROFILE_ID,
            "radius_provenance": radius_provenance_for(CURRENT_PROFILE_ID),
        },
    }
    assert (
        preview["endpoints"]["reactant"]["candidates"][0]["xyz"]
        == (step["reactant"]["precomplex"]["candidates"][0]["xyz"])
    )
    assert (
        preview["endpoints"]["product"]["candidates"][0]["xyz"]
        == (step["product"]["precomplex"]["candidates"][0]["xyz"])
    )

    candidate_document_bytes = output.read_bytes()
    reactant_candidate = step["reactant"]["precomplex"]["candidates"][0]
    product_candidate = step["product"]["precomplex"]["candidates"][0]
    selected_output = tmp_path / "mechanism-precomplex-reviewed.chemvas"
    assert (
        cli.run(
            [
                "select-precomplex",
                str(output),
                "--step",
                "S01",
                "--reactant-candidate",
                reactant_candidate["id"],
                "--product-candidate",
                product_candidate["id"],
                "--reviewer",
                "test-reviewer",
                "--output",
                str(selected_output),
            ]
        )
        == 0
    )
    selection_report = json.loads(capsys.readouterr().out)
    reviewed = read_document(selected_output)
    reviewed_step = reviewed.state["calculation_plan"]["steps"][0]
    assert output.read_bytes() == candidate_document_bytes
    assert selection_report["format"] == "chemvas-precomplex-selection"
    assert selection_report["selected"] == {
        "reactant": reactant_candidate["id"],
        "product": product_candidate["id"],
    }
    for side, candidate in (
        ("reactant", reactant_candidate),
        ("product", product_candidate),
    ):
        selection = reviewed_step[side]["precomplex"]["selection"]
        assert selection["candidate_id"] == candidate["id"]
        assert selection["candidate_xyz_sha256"] == candidate["xyz_sha256"]
        assert selection["reviewer"] == "test-reviewer"
        assert selection["reviewed_at"].endswith("Z")
        assert selection["acceptance_statement"] == (
            "accepted_for_path_endpoint_review"
        )

    machine = tmp_path / "machine.json"
    assert (
        cli.run(
            [
                "pack-step",
                str(selected_output),
                "--step",
                "S01",
                "--output",
                str(machine),
            ]
        )
        == 0
    )
    observation = json.loads(capsys.readouterr().out)
    payload = observation["payload"]["data"]
    endpoint_pair = payload["endpoint_pair"]
    assert observation["handoff"] == {"status": "ready", "codes": []}
    assert endpoint_pair is not None
    assert endpoint_pair["geometry"]["component_count"] == 2
    assert endpoint_pair["geometry"]["precomplex_geometry"] == (
        "reviewed_precomplex_pair"
    )
    assert endpoint_pair["geometry"]["rigid_alignment"] == (
        "deterministic_precomplex_placement"
    )
    assert endpoint_pair["geometry"]["placement_profile"] == {
        "id": CURRENT_PROFILE_ID,
        "radius_provenance": radius_provenance_for(CURRENT_PROFILE_ID),
    }
    assert payload["geometry_scope"]["interaction_geometry_guarantee"] == (
        "reviewed_precomplex_pair"
    )
    assert (
        endpoint_pair["endpoints"]["reactant"]["content"].splitlines()[2:]
        == (reactant_candidate["xyz"].splitlines()[2:])
    )
    assert (
        endpoint_pair["endpoints"]["product"]["content"].splitlines()[2:]
        == (product_candidate["xyz"].splitlines()[2:])
    )

    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "generate-precomplex",
                str(source),
                str(request_path),
                "--step",
                "S01",
                "--output",
                str(output),
            ]
        )
    assert error.value.code == 2


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
    return reviewed, json.loads(reviewed.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("changed_sides", "error_text"),
    [
        (("product",), "stale for this graph or plan"),
        (("reactant", "product"), "stale for this graph or plan"),
    ],
)
def test_selection_rejects_generation_environment_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    changed_sides: tuple[str, ...],
    error_text: str,
) -> None:
    _source, _candidates, raw = _generate_candidate_fixture(
        tmp_path, monkeypatch, capsys
    )
    step = raw["state"]["calculation_plan"]["steps"][0]
    for side in changed_sides:
        step[side]["precomplex"]["environment"] = {
            "kind": "solvent",
            "model": "PCM",
            "name": "water",
        }
    mismatched = tmp_path / "mismatched-environment.chemvas"
    mismatched.write_text(json.dumps(raw), encoding="utf-8")
    read_document(mismatched)
    output = tmp_path / "reviewed.chemvas"

    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "select-precomplex",
                str(mismatched),
                "--step",
                "S01",
                "--reactant-candidate",
                step["reactant"]["precomplex"]["candidates"][0]["id"],
                "--product-candidate",
                step["product"]["precomplex"]["candidates"][0]["id"],
                "--reviewer",
                "test-reviewer",
                "--output",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert error_text in capsys.readouterr().err
    assert not output.exists()


def test_electronic_mark_change_makes_reviewed_precomplex_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reviewed, payload = _review_candidate_fixture(tmp_path, monkeypatch, capsys)
    payload["state"]["marks"].append(
        {
            "kind": "radical",
            "text": None,
            "atom_id": 0,
            "dx": None,
            "dy": None,
            "x": 0.0,
            "y": 0.0,
        }
    )
    stale = tmp_path / "mark-stale.chemvas"
    stale.write_text(json.dumps(payload), encoding="utf-8")
    read_document(stale)

    assert cli.run(["inspect-plan", str(stale)]) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["steps"][0]["path_precheck"]["blocking_reasons"] == [
        "multicomponent_precomplex_review_pair_stale"
    ]

    output = tmp_path / "machine.json"
    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "pack-step",
                str(stale),
                "--step",
                "S01",
                "--output",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert "reviewed precomplex is stale" in capsys.readouterr().err
    assert not output.exists()


@pytest.mark.parametrize("selection_state", ["none", "partial"])
def test_pack_step_stays_blocked_without_a_complete_reviewed_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    selection_state: str,
) -> None:
    _source, candidates, raw = _generate_candidate_fixture(
        tmp_path, monkeypatch, capsys
    )
    pack_source = candidates
    if selection_state == "partial":
        step = raw["state"]["calculation_plan"]["steps"][0]
        reactant_id = step["reactant"]["precomplex"]["candidates"][0]["id"]
        product_id = step["product"]["precomplex"]["candidates"][0]["id"]
        reviewed = tmp_path / "reviewed.chemvas"
        assert (
            cli.run(
                [
                    "select-precomplex",
                    str(candidates),
                    "--step",
                    "S01",
                    "--reactant-candidate",
                    reactant_id,
                    "--product-candidate",
                    product_id,
                    "--reviewer",
                    "test-reviewer",
                    "--output",
                    str(reviewed),
                ]
            )
            == 0
        )
        capsys.readouterr()
        partial = json.loads(reviewed.read_text(encoding="utf-8"))
        partial["state"]["calculation_plan"]["steps"][0]["product"]["precomplex"][
            "selection"
        ] = None
        pack_source = tmp_path / "partial.chemvas"
        pack_source.write_text(json.dumps(partial), encoding="utf-8")

    machine_dir = tmp_path / selection_state
    machine_dir.mkdir()
    assert (
        cli.run(
            [
                "pack-step",
                str(pack_source),
                "--step",
                "S01",
                "--output",
                str(machine_dir / "machine.json"),
            ]
        )
        == 0
    )
    observation = json.loads(capsys.readouterr().out)
    assert observation["handoff"] == {
        "status": "blocked",
        "codes": ["chemvas/multicomponent_precomplex_geometry_not_provided"],
    }
    assert observation["payload"]["data"]["endpoint_pair"] is None


def test_candidate_xyz_tamper_is_rejected_on_document_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _source, _candidates, raw = _generate_candidate_fixture(
        tmp_path, monkeypatch, capsys
    )
    candidate = raw["state"]["calculation_plan"]["steps"][0]["reactant"]["precomplex"][
        "candidates"
    ][0]
    candidate["xyz"] += " "
    tampered = tmp_path / "tampered.chemvas"
    tampered.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid Chemvas file"):
        read_document(tampered)


def test_selection_rejects_stale_graph_basis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _source, _candidates, raw = _generate_candidate_fixture(
        tmp_path, monkeypatch, capsys
    )
    step = raw["state"]["calculation_plan"]["steps"][0]
    raw["state"]["model"]["atoms"]["0"]["x"] += 0.5
    stale = tmp_path / "stale.chemvas"
    stale.write_text(json.dumps(raw), encoding="utf-8")
    selected = tmp_path / "selected.chemvas"

    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "select-precomplex",
                str(stale),
                "--step",
                "S01",
                "--reactant-candidate",
                step["reactant"]["precomplex"]["candidates"][0]["id"],
                "--product-candidate",
                step["product"]["precomplex"]["candidates"][0]["id"],
                "--reviewer",
                "test-reviewer",
                "--output",
                str(selected),
            ]
        )
    assert error.value.code == 2
    assert "stale for this graph or plan" in capsys.readouterr().err
    assert not selected.exists()


def test_pack_rejects_reviewed_geometry_after_rdkit_provenance_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _source, candidates, raw = _generate_candidate_fixture(
        tmp_path, monkeypatch, capsys
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

    class _DriftAdapter(_StateFakeAdapter):
        def model_to_calculation_artifacts(self, model, atom_annotations=None):
            artifacts = super().model_to_calculation_artifacts(
                model, atom_annotations=atom_annotations
            )
            return replace(artifacts, rdkit_version="different-rdkit")

    monkeypatch.setattr(cli, "RDKitAdapter", _DriftAdapter)
    machine = tmp_path / "machine.json"
    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "pack-step",
                str(reviewed),
                "--step",
                "S01",
                "--output",
                str(machine),
            ]
        )
    assert error.value.code == 2
    assert "no longer matches" in capsys.readouterr().err
    assert not machine.exists()


def _rebind_candidate_id(
    precomplex: dict[str, object],
    candidate: dict[str, object],
    component_atom_ids: list[list[int]],
) -> str:
    transform = candidate["transform"]
    assert isinstance(transform, dict)
    payload = {
        "profile": precomplex["profile"],
        "source_sha256": precomplex["source_document_sha256"],
        "plan_sha256": precomplex["basis_sha256"],
        "step_id": "S01",
        "side": precomplex["side"],
        "contacts": precomplex["contacts"],
        "component_atom_ids": component_atom_ids,
        "component_conformer_ids": candidate["component_conformer_ids"],
        "approach_index": transform["approach_index"],
        "rotation_index": transform["rotation_index"],
        "xyz_sha256": candidate["xyz_sha256"],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "pc-" + hashlib.sha256(canonical.encode("ascii")).hexdigest()


def test_reviewed_pair_rejects_different_source_document_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _reviewed, payload = _review_candidate_fixture(tmp_path, monkeypatch, capsys)
    precomplex = payload["state"]["calculation_plan"]["steps"][0]["product"][
        "precomplex"
    ]
    selection = precomplex["selection"]
    selected_id = selection["candidate_id"]
    precomplex["source_document_sha256"] = "0" * 64
    rebound_selected_id = None
    for candidate in precomplex["candidates"]:
        previous_id = candidate["id"]
        candidate["id"] = _rebind_candidate_id(precomplex, candidate, [[2, 3], [4]])
        if previous_id == selected_id:
            rebound_selected_id = candidate["id"]
    assert rebound_selected_id is not None
    selection["candidate_id"] = rebound_selected_id
    forged = tmp_path / "different-source-provenance.chemvas"
    forged.write_text(json.dumps(payload), encoding="utf-8")
    read_document(forged)

    assert cli.run(["inspect-plan", str(forged)]) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["steps"][0]["path_precheck"]["blocking_reasons"] == [
        "multicomponent_precomplex_review_pair_invalid"
    ]

    output = tmp_path / "machine.json"
    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "pack-step",
                str(forged),
                "--step",
                "S01",
                "--output",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert "different generation provenance" in capsys.readouterr().err
    assert not output.exists()


def test_selection_rejects_self_consistent_forged_candidate_geometry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _source, _candidates, raw = _generate_candidate_fixture(
        tmp_path, monkeypatch, capsys
    )
    step = raw["state"]["calculation_plan"]["steps"][0]
    precomplex = step["reactant"]["precomplex"]
    candidate = precomplex["candidates"][0]
    lines = candidate["xyz"].splitlines()
    candidate["xyz"] = "\n".join(
        [*lines[:2], *(f"{row.split()[0]} 0.0 0.0 0.0" for row in lines[2:]), ""]
    )
    candidate["xyz_sha256"] = hashlib.sha256(
        candidate["xyz"].encode("ascii")
    ).hexdigest()
    candidate["validation"] = {
        "hard_clash_count": 0,
        "soft_overlap_score": 0.0,
        "contact_error_angstrom": 0.0,
        "limiting_pair": None,
        "limiting_distance_angstrom": None,
        "limiting_threshold_angstrom": None,
    }
    candidate["id"] = _rebind_candidate_id(precomplex, candidate, [[0, 1], [4]])
    forged = tmp_path / "forged-candidates.chemvas"
    forged.write_text(json.dumps(raw), encoding="utf-8")
    read_document(forged)

    reviewed = tmp_path / "reviewed.chemvas"
    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "select-precomplex",
                str(forged),
                "--step",
                "S01",
                "--reactant-candidate",
                candidate["id"],
                "--product-candidate",
                step["product"]["precomplex"]["candidates"][0]["id"],
                "--reviewer",
                "test-reviewer",
                "--output",
                str(reviewed),
            ]
        )
    assert error.value.code == 2
    assert "does not reproduce" in capsys.readouterr().err
    assert not reviewed.exists()


@pytest.mark.parametrize("field", ["reviewer", "reviewed_at"])
def test_pack_rejects_mismatched_pair_review_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    field: str,
) -> None:
    _source, candidates, raw = _generate_candidate_fixture(
        tmp_path, monkeypatch, capsys
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
    tampered = json.loads(reviewed.read_text(encoding="utf-8"))
    reviewed_step = tampered["state"]["calculation_plan"]["steps"][0]
    replacement = "other-reviewer" if field == "reviewer" else "2026-08-10T00:00:00Z"
    reviewed_step["product"]["precomplex"]["selection"][field] = replacement
    forged = tmp_path / f"tampered-{field}.chemvas"
    forged.write_text(json.dumps(tampered), encoding="utf-8")
    read_document(forged)

    assert cli.run(["inspect-plan", str(forged)]) == 0
    inspection = json.loads(capsys.readouterr().out)
    precheck = inspection["steps"][0]["path_precheck"]
    assert precheck["ready_for_path_endpoints"] is False
    assert precheck["blocking_reasons"] == [
        "multicomponent_precomplex_review_pair_invalid"
    ]

    machine = tmp_path / field / "machine.json"
    machine.parent.mkdir()
    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "pack-step",
                str(forged),
                "--step",
                "S01",
                "--output",
                str(machine),
            ]
        )
    assert error.value.code == 2
    assert "do not form one atomic pair" in capsys.readouterr().err
    assert not machine.exists()


def test_inspect_plan_blocks_stale_review_and_graph_patch_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _source, candidates, raw = _generate_candidate_fixture(
        tmp_path, monkeypatch, capsys
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

    stale_payload = json.loads(reviewed.read_text(encoding="utf-8"))
    stale_payload["state"]["model"]["atoms"]["0"]["x"] += 0.25
    stale = tmp_path / "stale.chemvas"
    stale.write_text(json.dumps(stale_payload), encoding="utf-8")
    read_document(stale)

    assert cli.run(["inspect-plan", str(stale)]) == 0
    inspection = json.loads(capsys.readouterr().out)
    precheck = inspection["steps"][0]["path_precheck"]
    assert precheck["ready_for_path_endpoints"] is False
    assert precheck["blocking_reasons"] == [
        "multicomponent_precomplex_review_pair_stale"
    ]

    reviewed_payload = json.loads(reviewed.read_text(encoding="utf-8"))
    atom = reviewed_payload["state"]["model"]["atoms"]["0"]
    patch = tmp_path / "move.json"
    patch.write_text(
        json.dumps(
            {
                "format": "chemvas-graph-patch",
                "version": 1,
                "source_sha256": hashlib.sha256(reviewed.read_bytes()).hexdigest(),
                "operations": [
                    {
                        "op": "move_atom",
                        "atom_id": 0,
                        "x": atom["x"] + 0.25,
                        "y": atom["y"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "patched.chemvas"

    with pytest.raises(SystemExit) as error:
        patch_cli.run(
            [
                "apply-patch",
                str(reviewed),
                str(patch),
                "--output",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert "reviewed precomplex is stale" in capsys.readouterr().err
    assert not output.exists()


def test_graph_patch_allows_cosmetic_color_change_on_a_reviewed_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reviewed, _payload = _review_candidate_fixture(tmp_path, monkeypatch, capsys)
    patch = tmp_path / "color.json"
    patch.write_text(
        json.dumps(
            {
                "format": "chemvas-graph-patch",
                "version": 1,
                "source_sha256": hashlib.sha256(reviewed.read_bytes()).hexdigest(),
                "operations": [
                    {
                        "op": "update_atom",
                        "atom_id": 0,
                        "changes": {"color": "#ff0000"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert patch_cli.run(["apply-patch", str(reviewed), str(patch), "--dry-run"]) == 0
    dry_run = json.loads(capsys.readouterr().out)
    assert dry_run["written"] is False

    output = tmp_path / "color-patched.chemvas"
    assert (
        patch_cli.run(
            [
                "apply-patch",
                str(reviewed),
                str(patch),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert read_document(output).state["model"]["atoms"]["0"]["color"] == "#ff0000"

    assert cli.run(["inspect-plan", str(output)]) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["steps"][0]["path_precheck"]["ready_for_path_endpoints"] is True


def test_graph_patch_preserves_review_after_readding_the_same_bond(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reviewed, _payload = _review_candidate_fixture(tmp_path, monkeypatch, capsys)
    patch = tmp_path / "readd-bond.json"
    patch.write_text(
        json.dumps(
            {
                "format": "chemvas-graph-patch",
                "version": 1,
                "source_sha256": hashlib.sha256(reviewed.read_bytes()).hexdigest(),
                "operations": [
                    {"op": "remove_bond", "a": 0, "b": 1},
                    {
                        "op": "add_bond",
                        "a": 1,
                        "b": 0,
                        "order": 2,
                        "style": "single",
                        "color": "#000000",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "readded-bond.chemvas"

    assert (
        patch_cli.run(
            [
                "apply-patch",
                str(reviewed),
                str(patch),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert cli.run(["inspect-plan", str(output)]) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["steps"][0]["path_precheck"]["ready_for_path_endpoints"] is True


def test_graph_patch_rejects_reversing_a_reviewed_wedge_bond(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reviewed, _payload = _review_candidate_fixture(
        tmp_path,
        monkeypatch,
        capsys,
        source_bond_style="wedge",
    )
    patch = tmp_path / "reverse-wedge.json"
    patch.write_text(
        json.dumps(
            {
                "format": "chemvas-graph-patch",
                "version": 1,
                "source_sha256": hashlib.sha256(reviewed.read_bytes()).hexdigest(),
                "operations": [
                    {"op": "remove_bond", "a": 2, "b": 3},
                    {
                        "op": "add_bond",
                        "a": 3,
                        "b": 2,
                        "order": 1,
                        "style": "wedge",
                        "color": "#000000",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "reversed-wedge.chemvas"

    with pytest.raises(SystemExit) as error:
        patch_cli.run(
            [
                "apply-patch",
                str(reviewed),
                str(patch),
                "--output",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert "reviewed precomplex is stale" in capsys.readouterr().err
    assert not output.exists()


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        (
            "source_document_sha256",
            "0" * 64,
            "source_document_sha256 does not match",
        ),
        ("step_id", "S99", "step_id does not match"),
    ],
)
def test_generation_requires_request_binding_to_exact_source_and_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    field: str,
    replacement: str,
    message: str,
) -> None:
    source, _candidates, _raw = _generate_candidate_fixture(
        tmp_path, monkeypatch, capsys
    )
    request_path = tmp_path / "request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request[field] = replacement
    request_path.write_text(json.dumps(request), encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "generate-precomplex",
                str(source),
                str(request_path),
                "--step",
                "S01",
                "--output",
                str(tmp_path / f"mismatch-{field}.chemvas"),
            ]
        )
    assert error.value.code == 2
    assert message in capsys.readouterr().err


@pytest.mark.parametrize(
    ("version", "profile", "message"),
    [
        (2, None, "Invalid precomplex request fields"),
        (2, "unknown/1", "Unsupported precomplex placement profile"),
        (
            2,
            "chemvas-rigid-precomplex-placement/" + "1",
            "Unsupported precomplex placement profile",
        ),
        (1, CURRENT_PROFILE_ID, "Unsupported precomplex request format or version"),
        (True, CURRENT_PROFILE_ID, "Unsupported precomplex request format or version"),
    ],
)
def test_generation_rejects_invalid_profile_request_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    version: object,
    profile: str | None,
    message: str,
) -> None:
    source, _candidates, _raw = _generate_candidate_fixture(
        tmp_path, monkeypatch, capsys
    )
    request_path = tmp_path / "request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["version"] = version
    if profile is None:
        request.pop("profile")
    else:
        request["profile"] = profile
    request_path.write_text(json.dumps(request), encoding="utf-8")
    output = tmp_path / "invalid-profile-request.chemvas"

    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "generate-precomplex",
                str(source),
                str(request_path),
                "--step",
                "S01",
                "--output",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert message in capsys.readouterr().err
    assert not output.exists()


def test_generation_rejects_duplicate_request_json_keys_without_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "mechanism.chemvas"
    _write_document_with_plan(source)
    request_path = tmp_path / "duplicate-request.json"
    request_path.write_text(
        '{"format":"wrong","format":"chemvas-precomplex-request","version":2}',
        encoding="utf-8",
    )
    output = tmp_path / "must-not-exist.chemvas"

    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "generate-precomplex",
                str(source),
                str(request_path),
                "--step",
                "S01",
                "--output",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert "Invalid precomplex request JSON file" in capsys.readouterr().err
    assert not output.exists()


def test_removed_request_v1_has_no_parser_branch() -> None:
    source = Path(cli.__file__).read_text(encoding="utf-8")

    assert "version not in {1, 2}" not in source
    assert "if version == 1" not in source


def test_current_radius_provenance_tamper_is_rejected_on_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _source, _candidates, raw = _generate_candidate_fixture(
        tmp_path, monkeypatch, capsys
    )
    precomplex = raw["state"]["calculation_plan"]["steps"][0]["product"]["precomplex"]
    assert precomplex["radius_provenance"] == radius_provenance_for(CURRENT_PROFILE_ID)
    precomplex["radius_provenance"]["van_der_waals"]["doi"] = "10.0000/tampered"
    tampered = tmp_path / "tampered-radius-provenance.chemvas"
    tampered.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid Chemvas file"):
        read_document(tampered)


def test_removed_profile_candidate_ensemble_is_rejected_on_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _source, _candidates, raw = _generate_candidate_fixture(
        tmp_path, monkeypatch, capsys
    )
    precomplex = raw["state"]["calculation_plan"]["steps"][0]["reactant"]["precomplex"]
    precomplex["profile"] = "chemvas-rigid-precomplex-placement/" + "1"
    removed = tmp_path / "removed-profile-candidates.chemvas"
    removed.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid Chemvas file"):
        read_document(removed)


def test_generation_refuses_a_request_number_it_cannot_parse(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "mechanism.chemvas"
    _write_document_with_plan(source)
    request_path = tmp_path / "unparsable-request.json"
    request_path.write_text(
        '{"format":"chemvas-precomplex-request","version":2,'
        '"scale":1e99999999999999999999}',
        encoding="utf-8",
    )
    output = tmp_path / "must-not-exist.chemvas"

    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "generate-precomplex",
                str(source),
                str(request_path),
                "--step",
                "S01",
                "--output",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert "Invalid precomplex request JSON file" in capsys.readouterr().err
    assert not output.exists()
