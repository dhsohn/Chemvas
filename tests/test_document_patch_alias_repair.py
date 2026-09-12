from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy

import pytest

from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    build_document_payload,
    serialize_model_state,
    serialize_settings,
)
from chemvas.features.document_patch import apply_document_patch, inspect_document_graph


def _state(alias="OH", repair="relabel"):
    model = MoleculeModel(
        atoms={0: Atom("C", 0, 0), 1: Atom(alias, 18, 0)},
        bonds=[Bond(0, 1, order=2, style="double")],
        next_atom_id=2,
    )
    if repair != "lower_order":
        model.atoms[2] = Atom("C", 36, 0)
        model.bonds = [Bond(0, 1), Bond(1, 2)]
        model.next_atom_id = 3
    return {
        "model": serialize_model_state(model),
        "notes": [{"text": "Synthetic drawing to repair", "x": 0, "y": 40}],
        "marks": [],
        "ring_fills": [],
        "arrows": [],
        "ts_brackets": [],
        "shapes": [],
        "orbitals": [],
        "last_smiles_input": None,
        "settings": serialize_settings(
            bond_length_px=18.0,
            arrow_line_width=1.5,
            arrow_head_scale=0.3,
            orbital_phase_enabled=True,
            text_font_size=13,
            text_font_weight=400,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="portrait",
        ),
    }


def _operation(alias="OH", repair="relabel"):
    if repair == "lower_order":
        return {
            "op": "update_bond",
            "a": 0,
            "b": 1,
            "changes": {"order": 1, "style": "single"},
        }
    if repair == "remove_bond":
        return {"op": "remove_bond", "a": 1, "b": 2}
    return {
        "op": "update_atom",
        "atom_id": 1,
        "changes": {"element": {"OH": "O", "NH2": "N", "SH": "S"}[alias]},
    }


def _patch(digest, *operations):
    return {
        "format": "chemvas-graph-patch",
        "version": 1,
        "source_sha256": digest,
        "operations": list(operations),
    }


def _with_plan(state):
    model = state["model"]
    for atom_id, element in ((3, "C"), (4, "O"), (5, "C")):
        model["atoms"][atom_id] = {
            **model["atoms"][0],
            "element": element,
            "x": (atom_id - 3) * 18,
            "y": 60,
        }
    model["bonds"].extend(
        [{**model["bonds"][0], "a": 3, "b": 4}, {**model["bonds"][0], "a": 4, "b": 5}]
    )
    model["next_atom_id"] = 6
    state["calculation_plan"] = {
        "format": "chemvas-calculation-plan",
        "version": 2,
        "states": [
            {
                "id": name,
                "charge": 0,
                "multiplicity": 1,
                "members": [{"component_atom_ids": ids, "inclusion": "included"}],
            }
            for name, ids in (("R", [0, 1, 2]), ("P", [3, 4, 5]))
        ],
        "steps": [
            {
                "id": "S",
                "reactant": {
                    "state_id": "R",
                    "roles": [{"component_atom_ids": [0, 1, 2], "role": "reactant"}],
                    "precomplex": {"kind": "none"},
                },
                "product": {
                    "state_id": "P",
                    "roles": [{"component_atom_ids": [3, 4, 5], "role": "product"}],
                    "precomplex": {"kind": "none"},
                },
                "atom_correspondence": [
                    {"reactant_atom_id": atom_id, "product_atom_id": atom_id + 3}
                    for atom_id in range(3)
                ],
            }
        ],
    }
    return state


def _cli(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "chemvas", *map(str, arguments)],
        capture_output=True,
        text=True,
        timeout=15,
    )


@pytest.mark.parametrize("alias", ["OH", "NH2", "SH"])
@pytest.mark.parametrize("repair", ["relabel", "remove_bond", "lower_order"])
def test_source_alias_error_can_be_repaired_but_inspection_stays_strict(alias, repair):
    state = _state(alias, repair)
    before = deepcopy(state)
    build_document_payload(state, CANVAS_FILE_VERSION)
    with pytest.raises(ValueError, match="exactly one single attachment"):
        inspect_document_graph(state)
    result = apply_document_patch(
        state,
        _patch("a" * 64, _operation(alias, repair)),
        source_sha256="a" * 64,
        document_version=CANVAS_FILE_VERSION,
    )
    assert state == before
    inspection = inspect_document_graph(result.state)
    assert result.before == {
        "atoms": len(state["model"]["atoms"]),
        "bonds": len(state["model"]["bonds"]),
        "components": 1,
    }
    assert result.after == {
        "atoms": inspection["atom_count"],
        "bonds": inspection["bond_count"],
        "components": 2 if repair == "remove_bond" else 1,
    }
    assert result.state["model"]["next_atom_id"] == state["model"]["next_atom_id"]
    assert {k: v for k, v in result.state.items() if k != "model"} == {
        k: v for k, v in state.items() if k != "model"
    }


@pytest.mark.parametrize("alias", ["OH", "NH2", "SH"])
@pytest.mark.parametrize("repair", ["relabel", "remove_bond", "lower_order"])
def test_cli_alias_repair_dry_run_publish_and_reopen_match(tmp_path, alias, repair):
    source = tmp_path / "source.chemvas"
    patch_file = tmp_path / "repair.json"
    output = tmp_path / "repaired.chemvas"
    write_document(source, _state(alias, repair), CANVAS_FILE_VERSION)
    before = source.read_bytes()
    digest = hashlib.sha256(before).hexdigest()
    patch_file.write_text(json.dumps(_patch(digest, _operation(alias, repair))))
    for command in ("inspect", "inspect-document"):
        rejected = _cli(command, source)
        assert rejected.returncode == 2
        assert "exactly one single attachment" in rejected.stderr
    dry = _cli("apply-patch", source, patch_file, "--dry-run")
    assert dry.returncode == 0, dry.stderr
    assert set(tmp_path.iterdir()) == {source, patch_file}
    applied = _cli("apply-patch", source, patch_file, "--output", output)
    assert applied.returncode == 0, applied.stderr
    dry_report, applied_report = json.loads(dry.stdout), json.loads(applied.stdout)
    assert (
        dry_report["candidate_sha256"]
        == applied_report["candidate_sha256"]
        == hashlib.sha256(output.read_bytes()).hexdigest()
    )
    assert dry_report["source_sha256"] == applied_report["source_sha256"] == digest
    assert {k: v for k, v in dry_report.items() if k not in {"dry_run", "written"}} == {
        k: v for k, v in applied_report.items() if k not in {"dry_run", "written"}
    }
    assert read_document(output).payload["version"] == CANVAS_FILE_VERSION
    reopened = _cli("inspect-document", output)
    assert reopened.returncode == 0, reopened.stderr
    assert read_document(output).state["notes"] == read_document(source).state["notes"]
    assert source.read_bytes() == before
    output_before = output.read_bytes()
    refused = _cli("apply-patch", source, patch_file, "--output", output)
    assert refused.returncode == 2 and "already exists" in refused.stderr
    assert output.read_bytes() == output_before and source.read_bytes() == before
    assert set(tmp_path.iterdir()) == {source, patch_file, output}


@pytest.mark.parametrize(
    "case",
    [
        "exact_noop",
        "round_trip",
        "cosmetic_only",
        "partial",
        "new_invalid",
        "charge_conflict",
        "radical_conflict",
        "plan_component_stale",
        "plan_correspondence_mismatch",
        "stale_hash",
        "bad_patch",
        "broken_source",
    ],
)
@pytest.mark.parametrize("dry", [False, True])
def test_alias_repair_cannot_publish_an_invalid_candidate(tmp_path, case, dry):
    source = tmp_path / "source.chemvas"
    patch_file = tmp_path / "repair.json"
    output = tmp_path / "rejected.chemvas"
    state = _state()
    operation = _operation()
    if case == "exact_noop":
        operation["changes"] = {"element": "OH"}
    elif case == "cosmetic_only":
        operation["changes"] = {"color": "#123456"}
    elif case == "partial":
        state["model"]["atoms"][0]["element"] = "SH"
        state["model"]["bonds"][0].update(order=2, style="double")
    elif case == "new_invalid":
        operation["changes"] = {"element": "NH2"}
    elif case in {"charge_conflict", "radical_conflict"}:
        state["model"]["atom_annotations"] = {
            1: {"formal_charge": 1}
            if case == "charge_conflict"
            else {"radical_electrons": 2}
        }
        state["marks"] = [
            {
                "kind": "minus" if case == "charge_conflict" else "radical",
                "text": "-" if case == "charge_conflict" else "•",
                "atom_id": 1,
                "dx": None,
                "dy": None,
                "x": 18,
                "y": -5,
            }
        ]
    elif case.startswith("plan_"):
        _with_plan(state)
        if case == "plan_component_stale":
            operation = _operation(repair="remove_bond")
        else:
            state["model"]["atoms"][4]["element"] = "N"
    write_document(source, state, CANVAS_FILE_VERSION)
    if case == "broken_source":
        payload = json.loads(source.read_bytes())
        payload["state"]["model"]["bonds"][0]["b"] = 999
        source.write_text(json.dumps(payload))
    before = source.read_bytes()
    patch = _patch(hashlib.sha256(before).hexdigest(), operation)
    if case == "round_trip":
        patch["operations"].append(
            {"op": "update_atom", "atom_id": 1, "changes": {"element": "OH"}}
        )
    if case == "stale_hash":
        patch["source_sha256"] = "0" * 64
    elif case == "bad_patch":
        patch["ignore_errors"] = True
    patch_file.write_text(json.dumps(patch))
    result = _cli(
        "apply-patch",
        source,
        patch_file,
        *(["--dry-run"] if dry else ["--output", output]),
    )
    assert result.returncode == 2, result.stdout
    assert not result.stdout and result.stderr
    assert not output.exists()
    assert source.read_bytes() == before
    assert set(tmp_path.iterdir()) == {source, patch_file}


def test_cli_alias_repair_preserves_a_matching_plan(tmp_path):
    source = tmp_path / "source.chemvas"
    patch_file = tmp_path / "repair.json"
    output = tmp_path / "repaired.chemvas"
    state = _with_plan(_state())
    write_document(source, state, CANVAS_FILE_VERSION)
    before = source.read_bytes()
    patch_file.write_text(
        json.dumps(_patch(hashlib.sha256(before).hexdigest(), _operation()))
    )
    applied = _cli("apply-patch", source, patch_file, "--output", output)
    assert applied.returncode == 0, applied.stderr
    assert json.loads(applied.stdout)["calculation_plan"] == {
        "present": True,
        "validation": "passed",
    }
    inspected = _cli("inspect-plan", output)
    assert inspected.returncode == 0, inspected.stderr
    assert read_document(output).state["calculation_plan"] == state["calculation_plan"]
    assert source.read_bytes() == before


@pytest.mark.parametrize("conflict", [False, True])
def test_relabel_repair_preserves_effective_charge_and_rejects_conflicting_marks(
    conflict,
):
    state = _state("OH", "lower_order")
    state["model"]["bonds"][0].update(order=1, style="single")
    state["model"]["atom_annotations"] = {1: {"formal_charge": 1 if conflict else -1}}
    state["marks"] = [
        {
            "kind": "minus",
            "text": "-",
            "atom_id": 1,
            "dx": None,
            "dy": None,
            "x": 18,
            "y": -5,
        }
    ]
    before = deepcopy(state)
    if conflict:
        with pytest.raises(ValueError, match="Conflicting charge/radical annotations"):
            apply_document_patch(
                state,
                _patch("a" * 64, _operation()),
                source_sha256="a" * 64,
                document_version=CANVAS_FILE_VERSION,
            )
    else:
        result = apply_document_patch(
            state,
            _patch("a" * 64, _operation()),
            source_sha256="a" * 64,
            document_version=CANVAS_FILE_VERSION,
        )
        assert (
            inspect_document_graph(result.state)["components"][0]["formal_charge"] == -1
        )
        assert result.state["marks"] == state["marks"]
        assert (
            result.state["model"]["atom_annotations"]
            == state["model"]["atom_annotations"]
        )
    assert state == before
