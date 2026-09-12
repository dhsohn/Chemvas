"""Precomplex diagnostics distinguish corrective actions without changing chemistry."""

import json
from dataclasses import replace

import pytest

from chemvas.bootstrap import calculation_bundle as cli
from chemvas.features.calculation_bundle import (
    calculation_plan_for_document,
    validate_reviewed_precomplex_pair,
)
from chemvas.features.precomplex_generation import (
    ValidationMetrics,
    generate_precomplex_candidates,
)
from tests.test_calculation_step_cli import _validate_common_machine
from tests.test_precomplex_cli import (
    _generate_candidate_fixture,
    _review_candidate_fixture,
)
from tests.test_precomplex_generation import _iron_cobalt_fixture


def test_failed_placement_reports_existing_metrics_deterministically():
    components, request = _iron_cobalt_fixture()
    request = replace(
        request, contacts=(replace(request.contacts[0], target_distance_angstrom=0.5),)
    )
    messages = []
    for _ in range(2):
        with pytest.raises(ValueError) as error:
            generate_precomplex_candidates(request, components)
        messages.append(str(error.value))
    assert messages[0] == messages[1]
    message = messages[0]
    assert message.startswith("chemvas/precomplex_no_candidates_survived:")
    assert "72 placements" in message
    assert "first rejected placement" in message
    assert "approach 0, rotation 0" in message
    assert "path indices (0, 1)" in message
    assert "distance 0.5 A" in message
    assert "threshold 2.193 A" in message
    assert "contact error 0 A" in message
    assert "tolerance 0.05 A" in message
    assert "Chemvas atoms (0, 2)" in message
    assert len(message) < 1000


def test_public_generate_error_leaves_source_and_destination_unmodified(
    tmp_path, monkeypatch, capsys
):
    source, _candidates, _raw = _generate_candidate_fixture(
        tmp_path, monkeypatch, capsys
    )
    request_path = tmp_path / "request.json"
    request = json.loads(request_path.read_text())
    for endpoint in request["endpoints"].values():
        endpoint["contacts"][0]["target_distance_angstrom"] = 0.1
    request_path.write_text(json.dumps(request), encoding="utf-8")
    before = source.read_bytes()
    output = tmp_path / "failed.chemvas"
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
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "precomplex_no_candidates_survived" in captured.err
    assert "path indices" in captured.err and "threshold" in captured.err
    assert not output.exists()
    assert source.read_bytes() == before


def test_contact_only_rejection_does_not_invent_a_limiting_atom_pair(monkeypatch):
    from chemvas.features.precomplex_generation import service

    components, request = _iron_cobalt_fixture()
    observed = ValidationMetrics(
        hard_clash_count=1,
        soft_overlap_score=0.0,
        contact_error_angstrom=0.2,
        limiting_pair=None,
        limiting_distance_angstrom=None,
        limiting_threshold_angstrom=None,
    )
    calls = []

    def measured(*args, **kwargs):
        calls.append(True)
        return observed

    monkeypatch.setattr(service, "_validate_placement", measured)
    with pytest.raises(ValueError) as error:
        generate_precomplex_candidates(request, components)
    assert len(calls) == 72
    assert "contact error 0.2 A (tolerance 0.05 A)" in str(error.value)
    assert "no limiting atom pair" in str(error.value)
    assert "path indices" not in str(error.value)


@pytest.mark.parametrize("reactant", ["missing", "unreviewed", "reviewed"])
@pytest.mark.parametrize("product", ["missing", "unreviewed", "reviewed"])
def test_inspect_and_pack_distinguish_missing_and_unreviewed_without_new_fields(
    tmp_path, monkeypatch, capsys, reactant, product
):
    original, raw = _review_candidate_fixture(tmp_path, monkeypatch, capsys)
    original_bytes = original.read_bytes()
    step = raw["state"]["calculation_plan"]["steps"][0]
    for side, state in (("reactant", reactant), ("product", product)):
        if state == "missing":
            step[side]["precomplex"] = {"kind": "none"}
        elif state == "unreviewed":
            step[side]["precomplex"]["selection"] = None
    source = tmp_path / "inspect-and-pack.chemvas"
    source.write_text(json.dumps(raw), encoding="utf-8")
    source_bytes = source.read_bytes()
    if "missing" in (reactant, product):
        reasons = ["multicomponent_precomplex_geometry_not_provided"]
    elif "unreviewed" in (reactant, product):
        reasons = ["multicomponent_precomplex_review_required"]
    else:
        reasons = []
    plan = calculation_plan_for_document(raw["state"])
    if reasons:
        with pytest.raises(ValueError) as error:
            validate_reviewed_precomplex_pair(raw["state"], plan, plan.steps[0])
        if "missing" in (reactant, product):
            assert "Run generate-precomplex" in str(error.value)
        else:
            assert "Run inspect-precomplex, then select-precomplex" in str(error.value)
    assert cli.run(["inspect-plan", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["version"] == 1
    precheck = report["steps"][0]["path_precheck"]
    assert set(precheck) == {
        "reactant_charge",
        "product_charge",
        "charge_matches",
        "reactant_multiplicity",
        "product_multiplicity",
        "multiplicity_matches",
        "reactant_component_count",
        "product_component_count",
        "single_component_endpoints",
        "source_mapping_complete",
        "ready_for_path_endpoints",
        "blocking_reasons",
    }
    assert precheck["blocking_reasons"] == reasons
    assert precheck["ready_for_path_endpoints"] == (not reasons)
    output = tmp_path / "machine.json"
    assert (
        cli.run(["pack-step", str(source), "--step", "S01", "--output", str(output)])
        == 0
    )
    observation = json.loads(capsys.readouterr().out)
    assert observation["contract"] == {
        "name": "factory/machine-observation",
        "version": 1,
    }
    assert observation["handoff"] == {
        "status": "blocked" if reasons else "ready",
        "codes": [f"chemvas/{reason}" for reason in reasons],
    }
    assert (observation["payload"]["data"]["endpoint_pair"] is None) == bool(reasons)
    _validate_common_machine(output)
    assert source.read_bytes() == source_bytes
    assert original.read_bytes() == original_bytes
