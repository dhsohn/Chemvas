from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict
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
    CalculationState,
    CalculationStep,
    CalculationStepEndpoint,
    calculation_plan_to_state,
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
    select_component,
    validate_calculation_plan,
)

_SPECIES_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_BUNDLE_FORMAT = "chemvas-calculation-bundle"
_BUNDLE_VERSION = 1
_STEP_ARTIFACT_FORMAT = "chemvas-elementary-step"
_STEP_ARTIFACT_VERSION = 1


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
        if args.command == "pack":
            manifest = _pack(
                Path(args.document),
                output=Path(args.output),
                component_index=args.component,
                species_id=args.species_id,
                charge=args.charge,
                multiplicity=args.multiplicity,
            )
            sys.stdout.write(_json_text(manifest))
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

    pack_parser = subparsers.add_parser(
        "pack", help="create a non-overwriting Calculation Bundle v1 directory"
    )
    pack_parser.add_argument("document", help="input .chemvas document")
    pack_parser.add_argument("--component", type=int, required=True)
    pack_parser.add_argument("--species-id", required=True)
    pack_parser.add_argument("--charge", type=int, required=True)
    pack_parser.add_argument("--multiplicity", type=int, required=True)
    pack_parser.add_argument("--output", required=True)

    attach_parser = subparsers.add_parser(
        "attach-plan",
        help="validate a Calculation Plan JSON file and embed it in a new .chemvas file",
    )
    attach_parser.add_argument("document", help="input .chemvas document")
    attach_parser.add_argument("plan", help="Calculation Plan v1 JSON file")
    attach_parser.add_argument("--output", required=True)

    inspect_plan_parser = subparsers.add_parser(
        "inspect-plan",
        help="inspect embedded calculation states and elementary steps as JSON",
    )
    inspect_plan_parser.add_argument("document", help="input .chemvas document")

    pack_step_parser = subparsers.add_parser(
        "pack-step",
        help="create one non-overwriting elementary-step JSON artifact",
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


def _pack(
    source: Path,
    *,
    output: Path,
    component_index: int,
    species_id: str,
    charge: int,
    multiplicity: int,
) -> dict[str, object]:
    _validate_source(source)
    _validate_pack_arguments(
        output=output,
        species_id=species_id,
        multiplicity=multiplicity,
    )
    source_bytes, document = read_exact_document(source)
    selection = select_component(document.state, component_index)
    if charge != selection.summary.formal_charge:
        raise ValueError(
            f"declared charge {charge} does not match the selected structure's "
            f"modeled formal charge {selection.summary.formal_charge}"
        )

    adapter = RDKitAdapter()
    artifacts = adapter.model_to_calculation_artifacts(
        selection.model,
        atom_annotations=selection.model.atom_annotations,
    )
    if artifacts is None:
        raise ValueError(adapter.last_error or "RDKit calculation conversion failed")
    _validate_calculation_artifacts(
        artifacts,
        declared_charge=charge,
        declared_multiplicity=multiplicity,
        modeled_radical_electrons=selection.summary.radical_electrons,
    )

    atom_map_payload = {
        "format": "chemvas-atom-map",
        "version": 1,
        "entries": [asdict(entry) for entry in artifacts.atom_map],
    }
    file_bytes = {
        "source.chemvas": source_bytes,
        "structure.mol": artifacts.mol_block.encode("utf-8"),
        "geometry.xyz": artifacts.xyz_block.encode("utf-8"),
        "atom_map.json": _json_text(atom_map_payload).encode("utf-8"),
    }
    manifest = _manifest(
        document_version=int(document.payload["version"]),
        species_id=species_id,
        charge=charge,
        multiplicity=multiplicity,
        component=selection.summary,
        artifacts=artifacts,
        file_bytes=file_bytes,
    )
    file_bytes["manifest.json"] = _json_text(manifest).encode("utf-8")
    _atomic_create_directory(output, file_bytes)
    return manifest


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
    correspondence = _step_atom_correspondence(
        step,
        reactant_artifacts=reactant_artifacts,
        product_artifacts=product_artifacts,
    )
    bond_changes = {
        "format": "chemvas-bond-changes",
        "version": 1,
        "step_id": step.id,
        "entries": list(calculate_bond_changes(document.state, plan, step)),
    }

    path_readiness = {
        **asdict(precheck),
        "generated_atom_mapping_complete": True,
    }
    endpoint_pair = (
        _path_endpoint_payload(
            reactant_state=reactant_state,
            reactant_artifacts=reactant_artifacts,
            product_artifacts=product_artifacts,
            correspondence=correspondence,
            bond_changes=bond_changes,
        )
        if precheck.ready_for_path_endpoints
        else None
    )
    artifact = {
        "format": _STEP_ARTIFACT_FORMAT,
        "version": _STEP_ARTIFACT_VERSION,
        "generator": {"name": "Chemvas", "version": __version__},
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
        ),
        "product": _state_payload(
            state=product_state,
            endpoint=step.product,
            selection=product_selection,
            artifacts=product_artifacts,
        ),
        "atom_correspondence": correspondence,
        "bond_changes": bond_changes,
        "mapping_validation": "complete_source_and_generated_geometry_bijection",
        "path_readiness": path_readiness,
        "endpoint_pair": endpoint_pair,
        "geometry_scope": {
            "reactant_component_count": len(reactant_selection.component_indices),
            "product_component_count": len(product_selection.component_indices),
            "interaction_geometry_guarantee": "not_provided",
            "intended_use": (
                "initial endpoint guesses requiring downstream quantum optimization "
                "and researcher review"
            ),
        },
    }
    atomic_create_bytes(output, _json_text(artifact).encode("utf-8"))
    return artifact


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
                "interaction_geometry_guarantee": "not_provided",
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
            "component_count": 1,
            "precomplex_geometry": "single_component_endpoints",
            "rigid_alignment": "not_performed",
            "endpoint_optimization": "required_downstream",
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


def _manifest(
    *,
    document_version: int,
    species_id: str,
    charge: int,
    multiplicity: int,
    component: ComponentSummary,
    artifacts: CalculationArtifacts,
    file_bytes: dict[str, bytes],
) -> dict[str, object]:
    return {
        "format": _BUNDLE_FORMAT,
        "version": _BUNDLE_VERSION,
        "generator": {"name": "Chemvas", "version": __version__},
        "species_id": species_id,
        "source": {
            "file": "source.chemvas",
            "chemvas_document_version": document_version,
            "component_index": component.index,
            "chemvas_atom_ids": list(component.atom_ids),
        },
        "chemical_state": {
            "declared_charge": charge,
            "modeled_formal_charge": component.formal_charge,
            "rdkit_formal_charge": artifacts.rdkit_formal_charge,
            "charge_validation": "matches_modeled_and_rdkit_formal_charge",
            "declared_multiplicity": multiplicity,
            "electron_count": artifacts.electron_count,
            "modeled_radical_electrons": component.radical_electrons,
            "rdkit_radical_electrons": artifacts.rdkit_radical_electrons,
            "multiplicity_validation": "electron_count_parity_only",
            "spin_state_inference": "not_performed",
        },
        "structure": {
            "mol_file": "structure.mol",
            "xyz_file": "geometry.xyz",
            "atom_map_file": "atom_map.json",
            "rdkit_version": artifacts.rdkit_version,
            "geometry_generation": {
                "embedding": artifacts.geometry_embedding,
                "random_seed": artifacts.geometry_random_seed,
                "optimization_policy": artifacts.geometry_optimization_policy,
                "optimization_result": artifacts.geometry_optimization_result,
                "intended_use": "initial geometry requiring downstream quantum optimization",
            },
            "atom_counts": {
                "chemvas": len(component.atom_ids),
                "mol": artifacts.mol_atom_count,
                "xyz": artifacts.xyz_atom_count,
            },
        },
        "artifacts": {
            name: {"sha256": _sha256(content), "bytes": len(content)}
            for name, content in sorted(file_bytes.items())
        },
    }


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


def _validate_pack_arguments(
    *, output: Path, species_id: str, multiplicity: int
) -> None:
    if _SPECIES_ID_PATTERN.fullmatch(species_id) is None:
        raise ValueError(
            "species id must be 1-128 ASCII letters, digits, '.', '_' or '-', "
            "and must start with a letter or digit"
        )
    if multiplicity < 1:
        raise ValueError("multiplicity must be a positive integer")
    if output.exists() or output.is_symlink():
        raise ValueError(f"output path already exists: {output}")
    if not output.parent.is_dir():
        raise ValueError(f"output parent directory does not exist: {output.parent}")


def _validate_new_step_output(output: Path) -> None:
    if output.suffix.lower() != ".json":
        raise ValueError("pack-step output must use the .json filename extension")
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


def _atomic_create_directory(output: Path, files: dict[str, bytes]) -> None:
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent)
    )
    try:
        for name, content in files.items():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        _fsync_directory(staging)
        if output.exists() or output.is_symlink():
            raise ValueError(f"output path already exists: {output}")
        os.replace(staging, output)
        _fsync_directory(output.parent)
    except BaseException:
        if staging.exists():
            with contextlib.suppress(OSError):
                shutil.rmtree(staging)
        raise


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        try:
            os.fsync(fd)
        except OSError:
            pass
    finally:
        os.close(fd)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


__all__ = ["run"]
