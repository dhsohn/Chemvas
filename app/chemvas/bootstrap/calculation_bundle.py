from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Mapping
from dataclasses import asdict, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, TypedDict

from chemvas import __version__
from chemvas.core.document_io import (
    atomic_create_bytes,
    create_document,
    read_document,
    read_exact_document,
)
from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    CalculationPlan,
    CalculationState,
    CalculationStep,
    CalculationStepEndpoint,
    calculation_plan_to_state,
)
from chemvas.domain.document.precomplex import precomplex_state_from_json
from chemvas.domain.document.precomplex_profile import (
    CURRENT_PROFILE_ID,
    precomplex_placement_profile,
    radius_provenance_for,
)
from chemvas.features.calculation_bundle import (
    AtomMapEntry,
    CalculationArtifacts,
    CalculationStateSelection,
    ComponentSummary,
    calculate_bond_changes,
    calculation_plan_for_document,
    calculation_plan_report,
    calculation_state_by_id,
    calculation_step_by_id,
    inspect_components,
    path_precheck,
    require_step_ready,
    select_calculation_state,
    validate_calculation_plan,
)
from chemvas.features.precomplex_generation import (
    ContactRequest,
    GeneratedCandidate,
    PlacementRequest,
    component_geometries_from_artifacts,
    generate_precomplex_candidates,
)

_MACHINE_CONTRACT_NAME = "factory/machine-observation"
_MACHINE_CONTRACT_VERSION = 1
_STEP_PAYLOAD_CONTRACT_NAME = "chemistry/elementary-step"
_STEP_PAYLOAD_CONTRACT_VERSION = 1


class _PathAtomOrderEntry(TypedDict):
    path_index: int
    reactant_xyz_index: int
    product_xyz_index: int
    symbol: str
    reactant_chemvas_atom_id: int | None
    product_chemvas_atom_id: int | None
    origin: str


def run(argv: list[str]) -> int:
    parser = _argument_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            payload = _inspect(Path(args.document))
            sys.stdout.write(_json_text(payload))
            return 0
        if args.command == "attach-plan":
            result = _attach_plan(
                Path(args.document),
                plan_path=Path(args.plan),
                output=Path(args.output),
            )
            sys.stdout.write(_json_text(result))
            return 0
        if args.command == "inspect-plan":
            payload = _inspect_plan(Path(args.document))
            sys.stdout.write(_json_text(payload))
            return 0
        if args.command == "inspect-precomplex":
            payload = _inspect_precomplex(Path(args.document), step_id=args.step)
            sys.stdout.write(_json_text(payload))
            return 0
        if args.command == "generate-precomplex":
            result = _generate_precomplex(
                Path(args.document),
                request_path=Path(args.request),
                step_id=args.step,
                output=Path(args.output),
            )
            sys.stdout.write(_json_text(result))
            return 0
        if args.command == "select-precomplex":
            result = _select_precomplex(
                Path(args.document),
                step_id=args.step,
                reactant_candidate_id=args.reactant_candidate,
                product_candidate_id=args.product_candidate,
                reviewer=args.reviewer,
                output=Path(args.output),
            )
            sys.stdout.write(_json_text(result))
            return 0
        if args.command == "pack-step":
            artifact = _pack_step(
                Path(args.document),
                step_id=args.step,
                output=Path(args.output),
            )
            sys.stdout.write(_json_text(artifact))
            return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"chemvas: error: {exc}\n")
    parser.error("a command is required")
    return 2


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chemvas",
        description="Chemvas GUI and headless calculation-plan/bundle tools.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect", help="inspect connected structures as JSON without starting Qt"
    )
    inspect_parser.add_argument("document", help="input .chemvas document")

    attach_parser = subparsers.add_parser(
        "attach-plan",
        help="validate a Calculation Plan JSON file and embed it in a new .chemvas file",
    )
    attach_parser.add_argument("document", help="input .chemvas document")
    attach_parser.add_argument("plan", help="Calculation Plan v2 JSON file")
    attach_parser.add_argument("--output", required=True)

    inspect_plan_parser = subparsers.add_parser(
        "inspect-plan",
        help="inspect embedded calculation states and elementary steps as JSON",
    )
    inspect_plan_parser.add_argument("document", help="input .chemvas document")

    inspect_precomplex_parser = subparsers.add_parser(
        "inspect-precomplex",
        help="inspect exact persisted precomplex candidates and XYZ as JSON",
    )
    inspect_precomplex_parser.add_argument(
        "document", help="candidate .chemvas document"
    )
    inspect_precomplex_parser.add_argument("--step", required=True)

    generate_parser = subparsers.add_parser(
        "generate-precomplex",
        help="generate bounded endpoint precomplex candidates in a new .chemvas file",
    )
    generate_parser.add_argument("document", help="input .chemvas document")
    generate_parser.add_argument("request", help="strict precomplex request JSON file")
    generate_parser.add_argument("--step", required=True)
    generate_parser.add_argument("--output", required=True)

    select_parser = subparsers.add_parser(
        "select-precomplex",
        help="review and select one persisted reactant/product precomplex pair",
    )
    select_parser.add_argument("document", help="candidate .chemvas document")
    select_parser.add_argument("--step", required=True)
    select_parser.add_argument("--reactant-candidate", required=True)
    select_parser.add_argument("--product-candidate", required=True)
    select_parser.add_argument("--reviewer", required=True)
    select_parser.add_argument("--output", required=True)

    pack_step_parser = subparsers.add_parser(
        "pack-step",
        help="create one non-overwriting elementary-step machine.json artifact",
    )
    pack_step_parser.add_argument("document", help="input .chemvas document")
    pack_step_parser.add_argument("--step", required=True)
    pack_step_parser.add_argument("--output", required=True)
    return parser


def _attach_plan(
    source: Path,
    *,
    plan_path: Path,
    output: Path,
) -> dict[str, object]:
    _validate_source(source)
    _validate_new_chemvas_output(source, output)
    if not plan_path.is_file():
        raise ValueError(f"calculation plan does not exist: {plan_path}")
    try:
        plan_payload = json.loads(plan_path.read_bytes(), parse_float=Decimal)
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid Calculation Plan JSON file.") from exc
    _source_bytes, document = read_exact_document(source)
    plan = validate_calculation_plan(document.state, plan_payload)
    state = dict(document.state)
    state["calculation_plan"] = calculation_plan_to_state(plan)
    output_document = create_document(state, CANVAS_FILE_VERSION)
    atomic_create_bytes(
        output,
        _json_text(output_document.payload).encode("utf-8"),
    )
    report = calculation_plan_report(output_document.state)
    return {
        "format": "chemvas-calculation-plan-attachment",
        "version": 1,
        "source": str(source),
        "output": str(output),
        "chemvas_document_version": CANVAS_FILE_VERSION,
        "state_count": len(plan.states),
        "step_count": len(plan.steps),
        "steps": report["steps"],
    }


def _inspect_plan(source: Path) -> dict[str, object]:
    _validate_source(source)
    document = read_document(source)
    report = calculation_plan_report(document.state)
    return {
        **report,
        "source": str(source),
        "chemvas_document_version": int(document.payload["version"]),
    }


def _inspect(source: Path) -> dict[str, object]:
    _validate_source(source)
    document = read_document(source)
    components = inspect_components(document.state)
    return {
        "format": "chemvas-structure-inspection",
        "version": 1,
        "source": str(source),
        "chemvas_document_version": int(document.payload["version"]),
        "component_count": len(components),
        "components": [_component_dict(component) for component in components],
    }


def _inspect_precomplex(source: Path, *, step_id: str) -> dict[str, object]:
    _validate_source(source)
    document = read_document(source)
    plan = calculation_plan_for_document(document.state)
    if plan.version != 2:
        raise ValueError(
            "precomplex inspection requires a Calculation Plan v2 document."
        )
    step = calculation_step_by_id(plan, step_id)
    endpoints: dict[str, object] = {}
    placement_profiles: dict[str, object] = {}
    for side, endpoint in (("reactant", step.reactant), ("product", step.product)):
        state = precomplex_state_from_json(endpoint.precomplex.payload_json)
        endpoints[side] = state
        profile_id = state.get("profile")
        if isinstance(profile_id, str):
            profile = precomplex_placement_profile(profile_id)
            placement_profiles[side] = {
                "id": profile.id,
                "radius_provenance": radius_provenance_for(profile.id),
            }
        else:
            placement_profiles[side] = None
    return {
        "format": "chemvas-precomplex-inspection",
        "version": 1,
        "source": str(source),
        "step_id": step.id,
        "endpoints": endpoints,
        "placement_profiles": placement_profiles,
    }


def _select_precomplex(
    source: Path,
    *,
    step_id: str,
    reactant_candidate_id: str,
    product_candidate_id: str,
    reviewer: str,
    output: Path,
) -> dict[str, object]:
    _validate_source(source)
    _validate_new_chemvas_output(source, output)
    reviewer = reviewer.strip()
    if not reviewer or len(reviewer) > 128:
        raise ValueError("precomplex reviewer must be between 1 and 128 characters.")
    _source_bytes, document = read_exact_document(source)
    plan = calculation_plan_for_document(document.state)
    if plan.version != 2:
        raise ValueError(
            "precomplex selection requires a Calculation Plan v2 document."
        )
    step = calculation_step_by_id(plan, step_id)
    require_step_ready(plan, step)
    plan_state = calculation_plan_to_state(plan)
    raw_steps = plan_state.get("steps")
    if not isinstance(raw_steps, list):
        raise ValueError("Calculation Plan step serialization is invalid.")
    raw_step = next(
        (
            item
            for item in raw_steps
            if isinstance(item, dict) and item.get("id") == step.id
        ),
        None,
    )
    if raw_step is None:
        raise ValueError(
            f"Calculation Plan step {step.id} disappeared during serialization."
        )
    reviewed_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    selected_ids = {
        "reactant": reactant_candidate_id,
        "product": product_candidate_id,
    }
    adapter = RDKitAdapter()
    for side in ("reactant", "product"):
        raw_endpoint = raw_step.get(side)
        if not isinstance(raw_endpoint, dict):
            raise ValueError("Calculation Plan endpoint serialization is invalid.")
        precomplex = raw_endpoint.get("precomplex")
        if (
            not isinstance(precomplex, dict)
            or precomplex.get("kind") != "candidate_ensemble"
        ):
            raise ValueError(f"Step {step.id} has no {side} precomplex candidates.")
        expected_basis = _precomplex_basis_sha256(
            document.state,
            plan,
            step_id=step.id,
            side=side,
        )
        if precomplex.get("basis_sha256") != expected_basis:
            raise ValueError(
                f"Step {step.id} {side} precomplex candidates are stale for this graph or plan."
            )
        endpoint = step.reactant if side == "reactant" else step.product
        calculation_state = calculation_state_by_id(plan, endpoint.state_id)
        calculation_selection = select_calculation_state(
            document.state, calculation_state
        )
        current_artifacts = _state_artifacts(
            adapter,
            calculation_selection,
            state_id=calculation_state.id,
            charge=calculation_state.charge,
            multiplicity=calculation_state.multiplicity,
        )
        _require_reproducible_precomplex(
            state=precomplex,
            calculation_state=calculation_state,
            current=current_artifacts,
            step=step,
            side=side,
        )
        candidates = precomplex.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError(
                f"Step {step.id} has invalid {side} precomplex candidates."
            )
        candidate = next(
            (
                item
                for item in candidates
                if isinstance(item, dict) and item.get("id") == selected_ids[side]
            ),
            None,
        )
        if candidate is None:
            raise ValueError(
                f"Unknown {side} precomplex candidate: {selected_ids[side]}"
            )
        xyz_sha256 = candidate.get("xyz_sha256")
        if not isinstance(xyz_sha256, str):
            raise ValueError(f"Step {step.id} has invalid {side} candidate provenance.")
        precomplex["selection"] = {
            "candidate_id": selected_ids[side],
            "candidate_xyz_sha256": xyz_sha256,
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "acceptance_statement": "accepted_for_path_endpoint_review",
        }
    validated_plan = validate_calculation_plan(document.state, plan_state)
    validated_step = calculation_step_by_id(validated_plan, step.id)
    _verify_precomplex_selection_pair(validated_step)
    state_payload = dict(document.state)
    state_payload["calculation_plan"] = calculation_plan_to_state(validated_plan)
    output_document = create_document(state_payload, CANVAS_FILE_VERSION)
    atomic_create_bytes(output, _json_text(output_document.payload).encode("utf-8"))
    return {
        "format": "chemvas-precomplex-selection",
        "version": 1,
        "source": str(source),
        "output": str(output),
        "step_id": step.id,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "selected": selected_ids,
    }


def _verify_precomplex_selection_pair(step: CalculationStep) -> dict[str, object]:
    identities: list[tuple[object, object, object]] = []
    profiles: list[tuple[str, object]] = []
    for endpoint in (step.reactant, step.product):
        state = precomplex_state_from_json(endpoint.precomplex.payload_json)
        selection = state.get("selection")
        if not isinstance(selection, Mapping):
            raise ValueError("Precomplex review pair is incomplete.")
        identities.append(
            (
                selection.get("reviewer"),
                selection.get("reviewed_at"),
                selection.get("acceptance_statement"),
            )
        )
        profile_id = state.get("profile")
        if not isinstance(profile_id, str):
            raise ValueError("Precomplex review pair has an invalid profile.")
        profile = precomplex_placement_profile(profile_id)
        persisted_provenance = state.get("radius_provenance")
        if persisted_provenance != radius_provenance_for(profile.id):
            raise ValueError(
                "Precomplex review pair has invalid placement profile provenance."
            )
        profiles.append((profile.id, persisted_provenance))
    if identities[0] != identities[1]:
        raise ValueError("Precomplex endpoint reviews do not form one atomic pair.")
    if profiles[0] != profiles[1]:
        raise ValueError(
            "Precomplex endpoint reviews use different placement profiles."
        )
    return {
        "id": profiles[0][0],
        "radius_provenance": radius_provenance_for(profiles[0][0]),
    }


def _generate_precomplex(
    source: Path,
    *,
    request_path: Path,
    step_id: str,
    output: Path,
) -> dict[str, object]:
    _validate_source(source)
    _validate_new_chemvas_output(source, output)
    request = _read_precomplex_request(request_path)
    source_bytes, document = read_exact_document(source)
    plan = calculation_plan_for_document(document.state)
    step = calculation_step_by_id(plan, step_id)
    require_step_ready(plan, step)
    candidate_cap, profile_id, environment, contacts_by_side = (
        _parse_precomplex_request(
            request,
            step_id=step.id,
            source_document_sha256=_sha256(source_bytes),
        )
    )
    adapter = RDKitAdapter()
    endpoint_payloads: dict[str, dict[str, object]] = {}
    candidate_counts: dict[str, int] = {}
    candidate_summaries: dict[str, list[dict[str, str]]] = {}
    for side, endpoint in (("reactant", step.reactant), ("product", step.product)):
        state = calculation_state_by_id(plan, endpoint.state_id)
        selection = select_calculation_state(document.state, state)
        artifacts = _state_artifacts(
            adapter,
            selection,
            state_id=state.id,
            charge=state.charge,
            multiplicity=state.multiplicity,
        )
        included_components = tuple(
            member.component_atom_ids
            for member in state.members
            if member.inclusion == "included"
        )
        components = component_geometries_from_artifacts(
            artifacts,
            included_components,
            profile=profile_id,
        )
        basis_sha256 = _precomplex_basis_sha256(
            document.state,
            plan,
            step_id=step.id,
            side=side,
        )
        candidates = generate_precomplex_candidates(
            PlacementRequest(
                source_sha256=_sha256(source_bytes),
                plan_sha256=basis_sha256,
                step_id=step.id,
                side=side,
                contacts=contacts_by_side[side],
                candidate_cap=candidate_cap,
                profile=profile_id,
            ),
            components,
        )
        endpoint_payloads[side] = _precomplex_endpoint_state(
            side=side,
            source_document_sha256=_sha256(source_bytes),
            basis_sha256=basis_sha256,
            environment=environment,
            contacts=contacts_by_side[side],
            artifacts=artifacts,
            candidates=candidates,
            profile_id=profile_id,
        )
        candidate_counts[side] = len(candidates)
        candidate_summaries[side] = [
            {"id": candidate.id, "xyz_sha256": candidate.xyz_sha256}
            for candidate in candidates
        ]

    plan_state = calculation_plan_to_state(plan)
    plan_state["version"] = 2
    raw_steps = plan_state.get("steps")
    if not isinstance(raw_steps, list):
        raise ValueError("Calculation Plan step serialization is invalid.")
    matched_step = False
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            raise ValueError("Calculation Plan step serialization is invalid.")
        for side in ("reactant", "product"):
            raw_endpoint = raw_step.get(side)
            if not isinstance(raw_endpoint, dict):
                raise ValueError("Calculation Plan endpoint serialization is invalid.")
            raw_endpoint.setdefault("precomplex", {"kind": "none"})
        if raw_step.get("id") == step.id:
            matched_step = True
            for side in ("reactant", "product"):
                raw_endpoint = raw_step.get(side)
                if not isinstance(raw_endpoint, dict):
                    raise ValueError(
                        "Calculation Plan endpoint serialization is invalid."
                    )
                raw_endpoint["precomplex"] = endpoint_payloads[side]
    if not matched_step:
        raise ValueError(
            f"Calculation Plan step {step.id} disappeared during serialization."
        )
    validated_plan = validate_calculation_plan(document.state, plan_state)
    state_payload = dict(document.state)
    state_payload["calculation_plan"] = calculation_plan_to_state(validated_plan)
    output_document = create_document(state_payload, CANVAS_FILE_VERSION)
    atomic_create_bytes(output, _json_text(output_document.payload).encode("utf-8"))
    return {
        "format": "chemvas-precomplex-generation",
        "version": 1,
        "source": str(source),
        "output": str(output),
        "step_id": step.id,
        "chemvas_document_version": CANVAS_FILE_VERSION,
        "profile": profile_id,
        "radius_provenance": radius_provenance_for(profile_id),
        "candidate_counts": candidate_counts,
        "candidates": candidate_summaries,
    }


def _read_precomplex_request(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise ValueError(f"precomplex request does not exist: {path}")
    try:
        payload = json.loads(path.read_bytes(), parse_float=Decimal)
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid precomplex request JSON file.") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("Invalid precomplex request JSON file.")
    return payload


def _parse_precomplex_request(
    request: Mapping[str, object],
    *,
    step_id: str,
    source_document_sha256: str,
) -> tuple[
    int,
    str,
    dict[str, object],
    dict[str, tuple[ContactRequest, ...]],
]:
    base_fields = {
        "format",
        "version",
        "source_document_sha256",
        "step_id",
        "candidate_cap",
        "environment",
        "endpoints",
    }
    version = request.get("version")
    if (
        request.get("format") != "chemvas-precomplex-request"
        or type(version) is not int
        or version != 2
    ):
        raise ValueError("Unsupported precomplex request format or version.")
    if set(request) != base_fields | {"profile"}:
        raise ValueError("Invalid precomplex request fields.")
    profile_value = request.get("profile")
    if not isinstance(profile_value, str):
        raise ValueError("precomplex request profile is required.")
    profile_id = precomplex_placement_profile(profile_value).id
    if profile_id != CURRENT_PROFILE_ID:
        raise ValueError("precomplex request profile is not current.")
    if request.get("source_document_sha256") != source_document_sha256:
        raise ValueError(
            "precomplex request source_document_sha256 does not match the input document."
        )
    if request.get("step_id") != step_id:
        raise ValueError("precomplex request step_id does not match --step.")
    candidate_cap = request.get("candidate_cap")
    profile = precomplex_placement_profile(profile_id)
    if (
        type(candidate_cap) is not int
        or not 1 <= candidate_cap <= profile.max_candidates
    ):
        raise ValueError(
            f"precomplex candidate_cap must be between 1 and {profile.max_candidates}."
        )
    environment = _precomplex_environment(request.get("environment"))
    endpoints = request.get("endpoints")
    if not isinstance(endpoints, Mapping) or set(endpoints) != {
        "reactant",
        "product",
    }:
        raise ValueError("precomplex request must define both endpoints.")
    contacts_by_side: dict[str, tuple[ContactRequest, ...]] = {}
    for side in ("reactant", "product"):
        endpoint = endpoints.get(side)
        if not isinstance(endpoint, Mapping) or set(endpoint) != {"contacts"}:
            raise ValueError(f"Invalid {side} precomplex request endpoint.")
        contacts = endpoint.get("contacts")
        if not isinstance(contacts, list) or len(contacts) != 1:
            raise ValueError(
                f"The placement profile requires one explicit {side} contact."
            )
        contacts_by_side[side] = (
            _contact_request(contacts[0], side=side, step_id=step_id),
        )
    return candidate_cap, profile_id, environment, contacts_by_side


def _precomplex_environment(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("precomplex environment is required.")
    if value.get("kind") == "gas_phase" and set(value) == {"kind"}:
        return {"kind": "gas_phase"}
    if value.get("kind") == "solvent" and set(value) == {"kind", "model", "name"}:
        model = value.get("model")
        name = value.get("name")
        if (
            not isinstance(model, str)
            or not model.strip()
            or len(model) > 128
            or not isinstance(name, str)
            or not name.strip()
            or len(name) > 128
        ):
            raise ValueError("Invalid precomplex solvent environment.")
        return {"kind": "solvent", "model": model, "name": name}
    raise ValueError("Invalid precomplex environment.")


def _contact_request(value: object, *, side: str, step_id: str) -> ContactRequest:
    if not isinstance(value, Mapping) or set(value) != {
        "id",
        "first_atom_id",
        "second_atom_id",
        "target_distance_angstrom",
        "tolerance_angstrom",
    }:
        raise ValueError(f"Invalid {side} contact for step {step_id}.")
    contact_id = value.get("id")
    first = value.get("first_atom_id")
    second = value.get("second_atom_id")
    if (
        not isinstance(contact_id, str)
        or not contact_id.strip()
        or len(contact_id) > 64
        or type(first) is not int
        or type(second) is not int
    ):
        raise ValueError(f"Invalid {side} contact identity for step {step_id}.")
    target = _request_float(value.get("target_distance_angstrom"), "contact target")
    tolerance = _request_float(value.get("tolerance_angstrom"), "contact tolerance")
    if target <= 0.0 or tolerance < 0.0 or tolerance > 1.0:
        raise ValueError(
            f"Invalid {side} contact distance or tolerance for step {step_id}."
        )
    return ContactRequest(
        id=contact_id,
        first_atom_id=first,
        second_atom_id=second,
        target_distance_angstrom=target,
        tolerance_angstrom=tolerance,
    )


def _request_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"Invalid precomplex {label}.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Invalid precomplex {label}.")
    return number


def _precomplex_basis_sha256(
    document_state: Mapping[str, object],
    plan: CalculationPlan,
    *,
    step_id: str,
    side: str,
) -> str:
    plan_state = calculation_plan_to_state(plan)
    plan_state["version"] = 2
    raw_steps = plan_state.get("steps")
    if not isinstance(raw_steps, list):
        raise ValueError("Calculation Plan step serialization is invalid.")
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            raise ValueError("Calculation Plan step serialization is invalid.")
        for endpoint_side in ("reactant", "product"):
            endpoint = raw_step.get(endpoint_side)
            if not isinstance(endpoint, dict):
                raise ValueError("Calculation Plan endpoint serialization is invalid.")
            endpoint["precomplex"] = {"kind": "none"}
    payload = {
        "format": "chemvas-precomplex-basis",
        "version": 1,
        "model": document_state.get("model"),
        "calculation_plan": plan_state,
        "step_id": step_id,
        "side": side,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return _sha256(canonical.encode("ascii"))


def _precomplex_endpoint_state(
    *,
    side: str,
    source_document_sha256: str,
    basis_sha256: str,
    environment: Mapping[str, object],
    contacts: tuple[ContactRequest, ...],
    artifacts: CalculationArtifacts,
    candidates: tuple[GeneratedCandidate, ...],
    profile_id: str,
) -> dict[str, object]:
    profile = precomplex_placement_profile(profile_id)
    if any(candidate.profile != profile.id for candidate in candidates):
        raise ValueError("Precomplex candidates do not match the requested profile.")
    state: dict[str, object] = {
        "kind": "candidate_ensemble",
        "source_document_sha256": source_document_sha256,
        "basis_sha256": basis_sha256,
        "side": side,
        "profile": profile.id,
        "radius_provenance": radius_provenance_for(profile.id),
        "environment": dict(environment),
        "contacts": [asdict(contact) for contact in contacts],
        "source_geometry": {
            "rdkit_version": artifacts.rdkit_version,
            "rdkit_formal_charge": artifacts.rdkit_formal_charge,
            "rdkit_radical_electrons": artifacts.rdkit_radical_electrons,
            "electron_count": artifacts.electron_count,
            "geometry_embedding": artifacts.geometry_embedding,
            "geometry_random_seed": artifacts.geometry_random_seed,
            "geometry_optimization_policy": artifacts.geometry_optimization_policy,
            "geometry_optimization_result": artifacts.geometry_optimization_result,
            "mol_atom_count": artifacts.mol_atom_count,
            "xyz_atom_count": artifacts.xyz_atom_count,
            "atom_map": [asdict(entry) for entry in artifacts.atom_map],
        },
        "candidates": [
            _precomplex_candidate_state(candidate) for candidate in candidates
        ],
        "selection": None,
    }
    return state


def _precomplex_candidate_state(candidate: GeneratedCandidate) -> dict[str, object]:
    validation = candidate.validation
    return {
        "id": candidate.id,
        "geometry_class": candidate.geometry_class,
        "xyz": candidate.xyz,
        "xyz_sha256": candidate.xyz_sha256,
        "transform": {
            "approach_index": candidate.transform.approach_index,
            "rotation_index": candidate.transform.rotation_index,
            "approach_vector": list(candidate.transform.approach_vector),
        },
        "component_conformer_ids": list(candidate.component_conformer_ids),
        "validation": {
            "hard_clash_count": validation.hard_clash_count,
            "soft_overlap_score": validation.soft_overlap_score,
            "contact_error_angstrom": validation.contact_error_angstrom,
            "limiting_pair": (
                None
                if validation.limiting_pair is None
                else list(validation.limiting_pair)
            ),
            "limiting_distance_angstrom": validation.limiting_distance_angstrom,
            "limiting_threshold_angstrom": validation.limiting_threshold_angstrom,
        },
    }


def _pack_step(
    source: Path,
    *,
    step_id: str,
    output: Path,
) -> dict[str, object]:
    _validate_source(source)
    _validate_new_step_output(output)
    source_bytes, document = read_exact_document(source)
    plan = calculation_plan_for_document(document.state)
    step = calculation_step_by_id(plan, step_id)
    require_step_ready(plan, step)
    reactant_state = calculation_state_by_id(plan, step.reactant.state_id)
    product_state = calculation_state_by_id(plan, step.product.state_id)
    precheck = path_precheck(plan, step)
    reactant_selection = select_calculation_state(document.state, reactant_state)
    product_selection = select_calculation_state(document.state, product_state)

    adapter = RDKitAdapter()
    reactant_artifacts = _state_artifacts(
        adapter,
        reactant_selection,
        state_id=reactant_state.id,
        charge=reactant_state.charge,
        multiplicity=reactant_state.multiplicity,
    )
    product_artifacts = _state_artifacts(
        adapter,
        product_selection,
        state_id=product_state.id,
        charge=product_state.charge,
        multiplicity=product_state.multiplicity,
    )
    reviewed_precomplex_pair = (
        not precheck.single_component_endpoints
        and "multicomponent_precomplex_geometry_not_provided"
        not in precheck.blocking_reasons
    )
    interaction_geometry_guarantee = "not_provided"
    placement_profile: dict[str, object] | None = None
    if reviewed_precomplex_pair:
        placement_profile = _verify_precomplex_selection_pair(step)
        reactant_artifacts = _reviewed_precomplex_artifacts(
            document_state=document.state,
            plan=plan,
            step=step,
            endpoint=step.reactant,
            side="reactant",
            current=reactant_artifacts,
        )
        product_artifacts = _reviewed_precomplex_artifacts(
            document_state=document.state,
            plan=plan,
            step=step,
            endpoint=step.product,
            side="product",
            current=product_artifacts,
        )
        interaction_geometry_guarantee = "reviewed_precomplex_pair"
    correspondence = _step_atom_correspondence(
        step,
        reactant_artifacts=reactant_artifacts,
        product_artifacts=product_artifacts,
    )
    bond_changes = {
        "step_id": step.id,
        "entries": list(calculate_bond_changes(document.state, plan, step)),
    }

    endpoint_pair = (
        _path_endpoint_payload(
            reactant_state=reactant_state,
            reactant_artifacts=reactant_artifacts,
            product_artifacts=product_artifacts,
            correspondence=correspondence,
            bond_changes=bond_changes,
            component_count=(2 if reviewed_precomplex_pair else 1),
            precomplex_geometry=(
                "reviewed_precomplex_pair"
                if reviewed_precomplex_pair
                else "single_component_endpoints"
            ),
            placement_profile=placement_profile,
        )
        if precheck.ready_for_path_endpoints
        else None
    )
    payload = {
        "step_id": step.id,
        "source": {
            "document_sha256": _sha256(source_bytes),
            "document_bytes": len(source_bytes),
            "chemvas_document_version": int(document.payload["version"]),
        },
        "reactant": _state_payload(
            state=reactant_state,
            endpoint=step.reactant,
            selection=reactant_selection,
            artifacts=reactant_artifacts,
            interaction_geometry_guarantee=interaction_geometry_guarantee,
        ),
        "product": _state_payload(
            state=product_state,
            endpoint=step.product,
            selection=product_selection,
            artifacts=product_artifacts,
            interaction_geometry_guarantee=interaction_geometry_guarantee,
        ),
        "atom_correspondence": correspondence,
        "bond_changes": bond_changes,
        "mapping_validation": "complete_source_and_generated_geometry_bijection",
        "endpoint_pair": endpoint_pair,
        "geometry_scope": {
            "reactant_component_count": len(reactant_selection.component_indices),
            "product_component_count": len(product_selection.component_indices),
            "interaction_geometry_guarantee": interaction_geometry_guarantee,
            "intended_use": (
                "initial endpoint guesses requiring downstream quantum optimization "
                "and researcher review"
            ),
        },
    }
    operation_digest = _sha256(
        b"chemvas-elementary-step-v1\0" + source_bytes + b"\0" + step.id.encode("utf-8")
    )
    handoff_codes = [f"chemvas/{reason}" for reason in precheck.blocking_reasons]
    observation = {
        "contract": {
            "name": _MACHINE_CONTRACT_NAME,
            "version": _MACHINE_CONTRACT_VERSION,
        },
        "producer": {"name": "chemvas", "version": __version__},
        "operation": {
            "id": f"step-{operation_digest}",
            "kind": "chemistry/elementary-step-export",
        },
        "lifecycle": {"phase": "finished", "outcome": "succeeded", "codes": []},
        "handoff": {
            "status": "ready" if precheck.ready_for_path_endpoints else "blocked",
            "codes": handoff_codes,
        },
        "delivery": {"status": "complete", "codes": []},
        "artifacts": {},
        "lineage": {"trace_id": None, "upstream": []},
        "payload": {
            "contract": {
                "name": _STEP_PAYLOAD_CONTRACT_NAME,
                "version": _STEP_PAYLOAD_CONTRACT_VERSION,
            },
            "data": payload,
        },
    }
    atomic_create_bytes(output, _json_text(observation).encode("utf-8"))
    return observation


def _reviewed_precomplex_artifacts(
    *,
    document_state: Mapping[str, object],
    plan: CalculationPlan,
    step: CalculationStep,
    endpoint: CalculationStepEndpoint,
    side: str,
    current: CalculationArtifacts,
) -> CalculationArtifacts:
    state = precomplex_state_from_json(endpoint.precomplex.payload_json)
    if state.get("kind") != "candidate_ensemble":
        raise ValueError(f"Step {step.id} has no reviewed {side} precomplex.")
    expected_basis = _precomplex_basis_sha256(
        document_state,
        plan,
        step_id=step.id,
        side=side,
    )
    if state.get("basis_sha256") != expected_basis:
        raise ValueError(
            f"Step {step.id} {side} reviewed precomplex is stale for this graph or plan."
        )
    expected_source_geometry = {
        "rdkit_version": current.rdkit_version,
        "rdkit_formal_charge": current.rdkit_formal_charge,
        "rdkit_radical_electrons": current.rdkit_radical_electrons,
        "electron_count": current.electron_count,
        "geometry_embedding": current.geometry_embedding,
        "geometry_random_seed": current.geometry_random_seed,
        "geometry_optimization_policy": current.geometry_optimization_policy,
        "geometry_optimization_result": current.geometry_optimization_result,
        "mol_atom_count": current.mol_atom_count,
        "xyz_atom_count": current.xyz_atom_count,
        "atom_map": [asdict(entry) for entry in current.atom_map],
    }
    if state.get("source_geometry") != expected_source_geometry:
        raise ValueError(
            f"Step {step.id} {side} reviewed precomplex no longer matches the "
            "current RDKit geometry identity or provenance. Regenerate and review it."
        )
    _require_reproducible_precomplex(
        state=state,
        calculation_state=calculation_state_by_id(plan, endpoint.state_id),
        current=current,
        step=step,
        side=side,
    )
    selection = state.get("selection")
    candidates = state.get("candidates")
    if not isinstance(selection, Mapping) or not isinstance(candidates, list):
        raise ValueError(f"Step {step.id} has no reviewed {side} precomplex selection.")
    candidate_id = selection.get("candidate_id")
    candidate = next(
        (
            item
            for item in candidates
            if isinstance(item, Mapping) and item.get("id") == candidate_id
        ),
        None,
    )
    if candidate is None:
        raise ValueError(f"Step {step.id} {side} selected candidate is missing.")
    xyz = candidate.get("xyz")
    xyz_sha256 = candidate.get("xyz_sha256")
    if (
        not isinstance(xyz, str)
        or not isinstance(xyz_sha256, str)
        or selection.get("candidate_xyz_sha256") != xyz_sha256
        or _sha256(xyz.encode("ascii")) != xyz_sha256
    ):
        raise ValueError(
            f"Step {step.id} {side} selected candidate geometry is invalid."
        )
    reviewed = replace(current, xyz_block=xyz)
    _xyz_atom_rows(reviewed, label=f"{side} reviewed precomplex")
    return reviewed


def _require_reproducible_precomplex(
    *,
    state: Mapping[str, object],
    calculation_state: CalculationState,
    current: CalculationArtifacts,
    step: CalculationStep,
    side: str,
) -> None:
    profile_id = state.get("profile")
    if not isinstance(profile_id, str):
        raise ValueError(f"Step {step.id} {side} precomplex profile is invalid.")
    profile = precomplex_placement_profile(profile_id)
    expected_source_geometry = {
        "rdkit_version": current.rdkit_version,
        "rdkit_formal_charge": current.rdkit_formal_charge,
        "rdkit_radical_electrons": current.rdkit_radical_electrons,
        "electron_count": current.electron_count,
        "geometry_embedding": current.geometry_embedding,
        "geometry_random_seed": current.geometry_random_seed,
        "geometry_optimization_policy": current.geometry_optimization_policy,
        "geometry_optimization_result": current.geometry_optimization_result,
        "mol_atom_count": current.mol_atom_count,
        "xyz_atom_count": current.xyz_atom_count,
        "atom_map": [asdict(entry) for entry in current.atom_map],
    }
    if state.get("source_geometry") != expected_source_geometry:
        raise ValueError(
            f"Step {step.id} {side} precomplex no longer matches the current "
            "RDKit geometry identity or provenance. Regenerate and review it."
        )
    raw_candidates = state.get("candidates")
    raw_contacts = state.get("contacts")
    source_document_sha256 = state.get("source_document_sha256")
    basis_sha256 = state.get("basis_sha256")
    if (
        not isinstance(raw_candidates, list)
        or not raw_candidates
        or not isinstance(raw_contacts, list)
        or not isinstance(source_document_sha256, str)
        or not isinstance(basis_sha256, str)
    ):
        raise ValueError(f"Step {step.id} {side} precomplex provenance is incomplete.")
    contacts = tuple(
        _contact_request(contact, side=side, step_id=step.id)
        for contact in raw_contacts
    )
    included_components = tuple(
        member.component_atom_ids
        for member in calculation_state.members
        if member.inclusion == "included"
    )
    components = component_geometries_from_artifacts(
        current,
        included_components,
        profile=profile.id,
    )
    regenerated = generate_precomplex_candidates(
        PlacementRequest(
            source_sha256=source_document_sha256,
            plan_sha256=basis_sha256,
            step_id=step.id,
            side=side,
            contacts=contacts,
            candidate_cap=len(raw_candidates),
            profile=profile.id,
        ),
        components,
    )
    expected_candidates = [
        _precomplex_candidate_state(candidate) for candidate in regenerated
    ]
    if raw_candidates != expected_candidates:
        raise ValueError(
            f"Step {step.id} {side} precomplex candidate ensemble does not reproduce "
            "from its current source geometry and provenance."
        )


def _state_artifacts(
    adapter: RDKitAdapter,
    selection: CalculationStateSelection,
    *,
    state_id: str,
    charge: int,
    multiplicity: int,
) -> CalculationArtifacts:
    if selection.formal_charge != charge:
        raise ValueError(
            f"State {state_id} declares charge {charge}, but its selected model has "
            f"formal charge {selection.formal_charge}."
        )
    artifacts = adapter.model_to_calculation_artifacts(
        selection.model,
        atom_annotations=selection.model.atom_annotations,
    )
    if artifacts is None:
        raise ValueError(
            adapter.last_error or f"RDKit conversion failed for state {state_id}"
        )
    _validate_calculation_artifacts(
        artifacts,
        declared_charge=charge,
        declared_multiplicity=multiplicity,
        modeled_radical_electrons=selection.radical_electrons,
    )
    return artifacts


def _state_payload(
    *,
    state: CalculationState,
    endpoint: CalculationStepEndpoint,
    selection: CalculationStateSelection,
    artifacts: CalculationArtifacts,
    interaction_geometry_guarantee: str,
) -> dict[str, object]:
    member_inclusion = {
        member.component_atom_ids: member.inclusion for member in state.members
    }
    return {
        "state_id": state.id,
        "selection": {
            "component_indices": list(selection.component_indices),
            "chemvas_atom_ids": list(selection.atom_ids),
        },
        "members": [
            {
                "component_atom_ids": list(role.component_atom_ids),
                "role": role.role,
                "inclusion": member_inclusion[role.component_atom_ids],
            }
            for role in endpoint.roles
        ],
        "chemical_state": {
            "declared_charge": state.charge,
            "modeled_formal_charge": selection.formal_charge,
            "rdkit_formal_charge": artifacts.rdkit_formal_charge,
            "charge_validation": "matches_modeled_and_rdkit_formal_charge",
            "declared_multiplicity": state.multiplicity,
            "electron_count": artifacts.electron_count,
            "modeled_radical_electrons": selection.radical_electrons,
            "rdkit_radical_electrons": artifacts.rdkit_radical_electrons,
            "multiplicity_validation": "electron_count_parity_only",
            "spin_state_inference": "not_performed",
        },
        "structure": {
            "rdkit_version": artifacts.rdkit_version,
            "component_count": len(selection.component_indices),
            "atom_map": [asdict(entry) for entry in artifacts.atom_map],
            "geometry_generation": {
                "embedding": artifacts.geometry_embedding,
                "random_seed": artifacts.geometry_random_seed,
                "optimization_policy": artifacts.geometry_optimization_policy,
                "optimization_result": artifacts.geometry_optimization_result,
                "interaction_geometry_guarantee": interaction_geometry_guarantee,
                "intended_use": (
                    "initial geometry requiring downstream quantum optimization "
                    "and researcher review"
                ),
            },
            "atom_counts": {
                "chemvas": len(selection.atom_ids),
                "mol": artifacts.mol_atom_count,
                "xyz": artifacts.xyz_atom_count,
            },
        },
    }


def _path_endpoint_payload(
    *,
    reactant_state: CalculationState,
    reactant_artifacts: CalculationArtifacts,
    product_artifacts: CalculationArtifacts,
    correspondence: Mapping[str, object],
    bond_changes: Mapping[str, object],
    component_count: int,
    precomplex_geometry: str,
    placement_profile: dict[str, object] | None,
) -> dict[str, object]:
    reactant_rows = _xyz_atom_rows(reactant_artifacts, label="reactant")
    product_rows = _xyz_atom_rows(product_artifacts, label="product")
    atom_order = _path_atom_order(
        correspondence,
        reactant_atom_count=len(reactant_rows),
        product_atom_count=len(product_rows),
    )
    aligned_product_rows = tuple(
        product_rows[entry["product_xyz_index"] - 1] for entry in atom_order
    )
    reactant_path = _path_xyz_block(
        reactant_rows,
        comment="Chemvas path reactant; canonical reactant atom identity order",
    )
    product_path = _path_xyz_block(
        aligned_product_rows,
        comment="Chemvas path product; canonical reactant atom identity order",
    )
    reaction_center_indices = _reaction_center_indices(atom_order, bond_changes)
    reactant_bytes = reactant_path.encode("utf-8")
    product_bytes = product_path.encode("utf-8")
    return {
        "electronic_state": {
            "charge": reactant_state.charge,
            "multiplicity": reactant_state.multiplicity,
            "validation": "reactant_product_match",
        },
        "ordering": {
            "canonical_side": "reactant",
            "path_index_base": 0,
            "identity_mapping": "explicit_generated_geometry_bijection",
            "atom_order": atom_order,
        },
        "reaction_center": {
            "atom_indices": reaction_center_indices,
            "index_base": 0,
            "definition": "atoms_incident_to_source_bond_changes",
        },
        "endpoints": {
            "reactant": {
                "format": "xyz",
                "content": reactant_path,
                "sha256": _sha256(reactant_bytes),
                "bytes": len(reactant_bytes),
            },
            "product": {
                "format": "xyz",
                "content": product_path,
                "sha256": _sha256(product_bytes),
                "bytes": len(product_bytes),
            },
        },
        "geometry": {
            "atom_count": len(reactant_rows),
            "component_count": component_count,
            "precomplex_geometry": precomplex_geometry,
            "rigid_alignment": (
                "deterministic_precomplex_placement"
                if precomplex_geometry == "reviewed_precomplex_pair"
                else "not_performed"
            ),
            "endpoint_optimization": "required_downstream",
            **(
                {"placement_profile": placement_profile}
                if placement_profile is not None
                else {}
            ),
            "intended_use": (
                "atom-identity-aligned initial endpoints for downstream path search "
                "and researcher review"
            ),
        },
    }


def _xyz_atom_rows(
    artifacts: CalculationArtifacts,
    *,
    label: str,
) -> tuple[str, ...]:
    lines = artifacts.xyz_block.splitlines()
    if len(lines) != artifacts.xyz_atom_count + 2:
        raise ValueError(f"{label} XYZ rows do not match the generated atom count.")
    try:
        declared_count = int(lines[0].strip())
    except ValueError as exc:
        raise ValueError(f"{label} XYZ has an invalid atom count.") from exc
    if declared_count != artifacts.xyz_atom_count:
        raise ValueError(f"{label} XYZ has an inconsistent atom count.")
    rows = tuple(lines[2:])
    for row, atom_map_entry in zip(rows, artifacts.atom_map, strict=True):
        fields = row.split()
        if len(fields) != 4 or fields[0] != atom_map_entry.symbol:
            raise ValueError(f"{label} XYZ rows do not match the generated atom map.")
    return rows


def _path_atom_order(
    correspondence: Mapping[str, object],
    *,
    reactant_atom_count: int,
    product_atom_count: int,
) -> list[_PathAtomOrderEntry]:
    raw_entries = correspondence.get("geometry_entries")
    if not isinstance(raw_entries, list):
        raise ValueError("Generated geometry correspondence is missing.")
    entries: list[_PathAtomOrderEntry] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, Mapping):
            raise ValueError("Generated geometry correspondence is invalid.")
        reactant_index = raw_entry.get("reactant_xyz_index")
        product_index = raw_entry.get("product_xyz_index")
        if type(reactant_index) is not int or type(product_index) is not int:
            raise ValueError("Generated geometry correspondence indices are invalid.")
        symbol = raw_entry.get("symbol")
        reactant_atom_id = raw_entry.get("reactant_chemvas_atom_id")
        product_atom_id = raw_entry.get("product_chemvas_atom_id")
        origin = raw_entry.get("origin")
        if (
            not isinstance(symbol, str)
            or not isinstance(origin, str)
            or (reactant_atom_id is not None and type(reactant_atom_id) is not int)
            or (product_atom_id is not None and type(product_atom_id) is not int)
        ):
            raise ValueError("Generated geometry correspondence values are invalid.")
        entries.append(
            {
                "path_index": reactant_index - 1,
                "reactant_xyz_index": reactant_index,
                "product_xyz_index": product_index,
                "symbol": symbol,
                "reactant_chemvas_atom_id": reactant_atom_id,
                "product_chemvas_atom_id": product_atom_id,
                "origin": origin,
            }
        )
    entries.sort(key=lambda entry: entry["reactant_xyz_index"])
    if [entry["reactant_xyz_index"] for entry in entries] != list(
        range(1, reactant_atom_count + 1)
    ) or {entry["product_xyz_index"] for entry in entries} != set(
        range(1, product_atom_count + 1)
    ):
        raise ValueError(
            "Generated geometry correspondence is not a complete bijection."
        )
    return entries


def _reaction_center_indices(
    atom_order: list[_PathAtomOrderEntry],
    bond_changes: Mapping[str, object],
) -> list[int]:
    raw_changes = bond_changes.get("entries")
    if not isinstance(raw_changes, list):
        raise ValueError("Bond-change entries are missing.")
    changed_source_atoms: set[int] = set()
    for change in raw_changes:
        if not isinstance(change, Mapping):
            raise ValueError("Bond-change entry is invalid.")
        atom_ids = change.get("reactant_atom_ids")
        if not isinstance(atom_ids, list) or not all(
            type(item) is int for item in atom_ids
        ):
            raise ValueError("Bond-change atom identities are invalid.")
        changed_source_atoms.update(atom_ids)
    return sorted(
        entry["path_index"]
        for entry in atom_order
        if entry["origin"] in {"chemvas_atom", "alias_attachment"}
        and entry["reactant_chemvas_atom_id"] in changed_source_atoms
    )


def _path_xyz_block(rows: tuple[str, ...], *, comment: str) -> str:
    return "\n".join((str(len(rows)), comment, *rows, ""))


def _step_atom_correspondence(
    step: CalculationStep,
    *,
    reactant_artifacts: CalculationArtifacts,
    product_artifacts: CalculationArtifacts,
) -> dict[str, object]:
    reactant_groups = _artifact_atom_groups(reactant_artifacts)
    product_groups = _artifact_atom_groups(product_artifacts)
    source_entries: list[dict[str, int]] = []
    geometry_entries: list[dict[str, object]] = []
    for entry in sorted(
        step.atom_correspondence,
        key=lambda item: item.reactant_atom_id,
    ):
        reactant_group = reactant_groups.get(entry.reactant_atom_id, ())
        product_group = product_groups.get(entry.product_atom_id, ())
        reactant_symbols = [item.symbol for item in reactant_group]
        product_symbols = [item.symbol for item in product_group]
        if not reactant_group or reactant_symbols != product_symbols:
            raise ValueError(
                f"Step {step.id} cannot produce a complete geometry atom mapping for "
                f"Chemvas atoms {entry.reactant_atom_id} -> {entry.product_atom_id}. "
                "Draw transferred hydrogens explicitly and keep abbreviation expansion "
                "consistent on both endpoints."
            )
        source_entries.append(asdict(entry))
        geometry_entries.extend(
            {
                "reactant_xyz_index": reactant_item.xyz_index,
                "product_xyz_index": product_item.xyz_index,
                "symbol": reactant_item.symbol,
                "reactant_chemvas_atom_id": entry.reactant_atom_id,
                "product_chemvas_atom_id": entry.product_atom_id,
                "origin": reactant_item.origin,
            }
            for reactant_item, product_item in zip(
                reactant_group, product_group, strict=True
            )
        )
    reactant_xyz = {entry["reactant_xyz_index"] for entry in geometry_entries}
    product_xyz = {entry["product_xyz_index"] for entry in geometry_entries}
    if reactant_xyz != set(range(1, reactant_artifacts.xyz_atom_count + 1)) or (
        product_xyz != set(range(1, product_artifacts.xyz_atom_count + 1))
    ):
        raise ValueError(
            f"Step {step.id} generated geometry atoms that are not covered by the "
            "validated atom correspondence."
        )
    return {
        "format": "chemvas-step-atom-correspondence",
        "version": 1,
        "step_id": step.id,
        "source_entries": source_entries,
        "geometry_entries": geometry_entries,
        "source_mapping": "complete_bijection",
        "geometry_mapping": "complete_bijection",
    }


def _artifact_atom_groups(
    artifacts: CalculationArtifacts,
) -> dict[int, tuple[AtomMapEntry, ...]]:
    groups: dict[int, list[AtomMapEntry]] = {}
    for entry in artifacts.atom_map:
        owner = (
            entry.chemvas_atom_id
            if entry.chemvas_atom_id is not None
            else entry.parent_chemvas_atom_id
        )
        if owner is None:
            raise ValueError(
                "A generated calculation atom has no Chemvas provenance owner."
            )
        groups.setdefault(owner, []).append(entry)
    return {owner: tuple(entries) for owner, entries in groups.items()}


def _component_dict(component: ComponentSummary) -> dict[str, object]:
    return {
        "index": component.index,
        "atom_ids": list(component.atom_ids),
        "atom_count": len(component.atom_ids),
        "bond_count": component.bond_count,
        "formula_labels": dict(component.formula_labels),
        "formal_charge": component.formal_charge,
        "radical_electrons": component.radical_electrons,
        "bounds": list(component.bounds),
    }


def _validate_source(source: Path) -> None:
    if source.suffix.lower() != ".chemvas":
        raise ValueError("input must use the .chemvas filename extension")
    if not source.is_file():
        raise ValueError(f"input document does not exist: {source}")


def _validate_new_step_output(output: Path) -> None:
    if output.name != "machine.json":
        raise ValueError("pack-step output filename must be machine.json")
    if output.exists() or output.is_symlink():
        raise ValueError(f"output path already exists: {output}")
    if not output.parent.is_dir():
        raise ValueError(f"output parent directory does not exist: {output.parent}")


def _validate_new_chemvas_output(source: Path, output: Path) -> None:
    if output.suffix.lower() != ".chemvas":
        raise ValueError("output must use the .chemvas filename extension")
    if output.absolute() == source.absolute():
        raise ValueError(
            "attach-plan writes a new document; output must differ from input"
        )
    if output.exists() or output.is_symlink():
        raise ValueError(f"output path already exists: {output}")
    if not output.parent.is_dir():
        raise ValueError(f"output parent directory does not exist: {output.parent}")


def _validate_calculation_artifacts(
    artifacts: CalculationArtifacts,
    *,
    declared_charge: int,
    declared_multiplicity: int,
    modeled_radical_electrons: int,
) -> None:
    if artifacts.rdkit_formal_charge != declared_charge:
        raise ValueError(
            "RDKit formal charge does not match the declared charge; "
            "calculation artifacts were not written"
        )
    if artifacts.rdkit_radical_electrons != modeled_radical_electrons:
        raise ValueError(
            "RDKit radical electron count does not match the Chemvas marks; "
            "calculation artifacts were not written"
        )
    if artifacts.electron_count < 1:
        raise ValueError("RDKit produced a nonpositive electron count")
    if declared_multiplicity > artifacts.electron_count + 1:
        raise ValueError("declared multiplicity exceeds the electron-count limit")
    if declared_multiplicity % 2 == artifacts.electron_count % 2:
        raise ValueError(
            "declared multiplicity has the wrong parity for the RDKit electron count"
        )
    if len(artifacts.atom_map) != artifacts.xyz_atom_count:
        raise ValueError("RDKit atom map does not match the XYZ atom count")
    if [entry.xyz_index for entry in artifacts.atom_map] != list(
        range(1, artifacts.xyz_atom_count + 1)
    ):
        raise ValueError("RDKit atom map has non-sequential XYZ indices")
    mol_indices = [
        entry.mol_index for entry in artifacts.atom_map if entry.mol_index is not None
    ]
    if mol_indices != list(range(1, artifacts.mol_atom_count + 1)):
        raise ValueError("RDKit atom map does not match the MOL atom count")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


__all__ = ["run"]
