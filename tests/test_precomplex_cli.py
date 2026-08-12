from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from chemvas.bootstrap import calculation_bundle as cli
from chemvas.core.document_io import read_document
from chemvas.domain.document import PRECOMPLEX_CANVAS_FILE_VERSION
from chemvas.domain.document.precomplex_profile import (
    CURRENT_PROFILE_ID,
    LEGACY_PROFILE_ID,
    radius_provenance_for,
)

from tests.test_calculation_step_cli import _StateFakeAdapter, _write_document_with_plan


@pytest.mark.parametrize(
    ("request_version", "profile_id"),
    [(1, LEGACY_PROFILE_ID), (2, CURRENT_PROFILE_ID)],
)
def test_generate_precomplex_creates_non_overwriting_plan_v2_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    request_version: int,
    profile_id: str,
) -> None:
    source = tmp_path / "mechanism.chemvas"
    _write_document_with_plan(source)
    source_bytes = source.read_bytes()
    request_path = tmp_path / "precomplex-request.json"
    request_payload: dict[str, object] = {
        "format": "chemvas-precomplex-request",
        "version": request_version,
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
    if request_version == 2:
        request_payload["profile"] = profile_id
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
    assert document.payload["version"] == PRECOMPLEX_CANVAS_FILE_VERSION
    assert plan["version"] == 2
    assert report["format"] == "chemvas-precomplex-generation"
    assert report["step_id"] == "S01"
    assert report["profile"] == profile_id
    assert report["radius_provenance"] == radius_provenance_for(profile_id)
    assert report["candidate_counts"] == {"reactant": 4, "product": 4}
    for side in ("reactant", "product"):
        precomplex = step[side]["precomplex"]
        assert precomplex["kind"] == "candidate_ensemble"
        assert precomplex["profile"] == profile_id
        if profile_id == CURRENT_PROFILE_ID:
            assert precomplex["radius_provenance"] == radius_provenance_for(profile_id)
        else:
            assert "radius_provenance" not in precomplex
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
    assert preview["endpoints"]["reactant"]["profile"] == profile_id
    assert preview["placement_profiles"] == {
        "reactant": {
            "id": profile_id,
            "radius_provenance": radius_provenance_for(profile_id),
        },
        "product": {
            "id": profile_id,
            "radius_provenance": radius_provenance_for(profile_id),
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
        "id": profile_id,
        "radius_provenance": radius_provenance_for(profile_id),
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
    profile_id: str = LEGACY_PROFILE_ID,
) -> tuple[Path, Path, dict[str, object]]:
    source = tmp_path / "source.chemvas"
    _write_document_with_plan(source)
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    request = tmp_path / "request.json"
    request_payload: dict[str, object] = {
        "format": "chemvas-precomplex-request",
        "version": 1 if profile_id == LEGACY_PROFILE_ID else 2,
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
    if profile_id != LEGACY_PROFILE_ID:
        request_payload["profile"] = profile_id
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
        assert precomplex["profile"] == profile_id
        if profile_id == LEGACY_PROFILE_ID:
            assert "radius_provenance" not in precomplex
    return source, output, raw


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
        (2, LEGACY_PROFILE_ID, "request v2 requires profile"),
        (True, None, "Unsupported precomplex request format or version"),
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
    if profile is not None:
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


def test_profile_two_radius_provenance_tamper_is_rejected_on_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _source, _candidates, raw = _generate_candidate_fixture(
        tmp_path,
        monkeypatch,
        capsys,
        profile_id=CURRENT_PROFILE_ID,
    )
    precomplex = raw["state"]["calculation_plan"]["steps"][0]["product"]["precomplex"]
    assert precomplex["radius_provenance"] == radius_provenance_for(CURRENT_PROFILE_ID)
    precomplex["radius_provenance"]["van_der_waals"]["doi"] = "10.0000/tampered"
    tampered = tmp_path / "tampered-radius-provenance.chemvas"
    tampered.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid Chemvas file"):
        read_document(tampered)


def test_selection_rejects_mixed_placement_profiles_without_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _source, legacy_candidates, legacy_raw = _generate_candidate_fixture(
        tmp_path,
        monkeypatch,
        capsys,
    )
    v2_dir = tmp_path / "v2"
    v2_dir.mkdir()
    _v2_source, _v2_candidates, current_raw = _generate_candidate_fixture(
        v2_dir,
        monkeypatch,
        capsys,
        profile_id=CURRENT_PROFILE_ID,
    )
    legacy_step = legacy_raw["state"]["calculation_plan"]["steps"][0]
    current_step = current_raw["state"]["calculation_plan"]["steps"][0]
    legacy_step["product"]["precomplex"] = current_step["product"]["precomplex"]
    mixed = tmp_path / "mixed-profile-candidates.chemvas"
    mixed.write_text(json.dumps(legacy_raw), encoding="utf-8")
    read_document(mixed)
    reviewed = tmp_path / "mixed-profile-reviewed.chemvas"

    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "select-precomplex",
                str(mixed),
                "--step",
                "S01",
                "--reactant-candidate",
                legacy_step["reactant"]["precomplex"]["candidates"][0]["id"],
                "--product-candidate",
                current_step["product"]["precomplex"]["candidates"][0]["id"],
                "--reviewer",
                "test-reviewer",
                "--output",
                str(reviewed),
            ]
        )

    assert error.value.code == 2
    assert "different placement profiles" in capsys.readouterr().err
    assert not reviewed.exists()
    assert legacy_candidates.exists()
