"""Build the shared CLI/desktop elementary-step handoff from a document snapshot."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict
from typing import TYPE_CHECKING, TypedDict

from chemvas import __version__
from chemvas.core.document_io import ChemvasDocument, atomic_create_bytes
from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.features.calculation_bundle import (
    AtomMapEntry,
    CalculationArtifacts,
    CalculationStateSelection,
    CalculationStepPreparation,
    calculation_state_by_id,
    prepare_calculation_step,
    step_atom_correspondence,
    validate_calculation_artifacts,
)

if TYPE_CHECKING:
    from pathlib import Path

    from chemvas.domain.document import CalculationState, CalculationStepEndpoint


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


_MACHINE_CONTRACT_NAME = "factory/machine-observation"
_MACHINE_CONTRACT_VERSION = 1
_STEP_PAYLOAD_CONTRACT_NAME = "chemistry/elementary-step"
_STEP_PAYLOAD_CONTRACT_VERSION = 2


class _PathAtomOrderEntry(TypedDict):
    path_index: int
    reactant_xyz_index: int
    product_xyz_index: int
    symbol: str
    reactant_chemvas_atom_id: int | None
    product_chemvas_atom_id: int | None
    origin: str


def build_calculation_handoff(
    document: ChemvasDocument,
    source_bytes: bytes,
    *,
    step_id: str,
    adapter_factory: Callable[[], RDKitAdapter] = RDKitAdapter,
) -> dict[str, object]:
    """Validate both endpoints and build their complete, reproducible atom map."""
    prepared = prepare_calculation_step(document.state, step_id)
    plan, step, precheck = prepared.plan, prepared.step, prepared.precheck
    reactant_state = calculation_state_by_id(plan, step.reactant.state_id)
    product_state = calculation_state_by_id(plan, step.product.state_id)
    reactant_selection = prepared.reactant_selection
    product_selection = prepared.product_selection

    adapter = adapter_factory()
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
    correspondence = step_atom_correspondence(
        step,
        reactant_artifacts=reactant_artifacts,
        product_artifacts=product_artifacts,
    )
    bond_changes = {
        "step_id": step.id,
        "entries": list(prepared.bond_changes()),
    }

    endpoint_geometry = (
        _endpoint_geometry_payload(
            adapter,
            prepared=prepared,
            reactant_state=reactant_state,
            reactant_artifacts=reactant_artifacts,
            product_artifacts=product_artifacts,
            correspondence=correspondence,
            bond_changes=bond_changes,
        )
        if precheck.ready_for_path_endpoints
        else None
    )
    payload = {
        "step_id": step.id,
        "source": {
            "document_sha256": document.source_sha256 or sha256_hex(source_bytes),
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
        "endpoint_geometry": endpoint_geometry,
        "geometry_scope": {
            "reactant_component_count": len(reactant_selection.component_indices),
            "product_component_count": len(product_selection.component_indices),
            "interaction_geometry_guarantee": "not_provided",
            "intended_use": (
                "initial component geometries requiring downstream placement, "
                "quantum optimization and researcher review"
            ),
        },
    }
    operation_digest = sha256_hex(
        b"chemvas-elementary-step-v2\0" + source_bytes + b"\0" + step.id.encode("utf-8")
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
    return observation


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
            f"State {state_id}: " + (adapter.last_error or "RDKit conversion failed.")
        )
    validate_calculation_artifacts(
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
                    "atom identity and electron bookkeeping from an internal "
                    "whole-state conversion whose coordinates are not published"
                ),
            },
            "atom_counts": {
                "chemvas": len(selection.atom_ids),
                "mol": artifacts.mol_atom_count,
                "xyz": artifacts.xyz_atom_count,
            },
        },
    }


def _endpoint_geometry_payload(
    adapter: RDKitAdapter,
    *,
    prepared: CalculationStepPreparation,
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
    step = prepared.step
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
            "atom_indices": _reaction_center_indices(atom_order, bond_changes),
            "index_base": 0,
            "definition": "atoms_incident_to_source_bond_changes",
            "bond_changes": _indexed_bond_changes(atom_order, bond_changes),
        },
        "sides": {
            "reactant": _side_geometry(
                adapter,
                side="reactant",
                endpoint=step.reactant,
                selections=prepared.reactant_component_selections,
                side_artifacts=reactant_artifacts,
                path_index_by_xyz={
                    entry["reactant_xyz_index"]: entry["path_index"]
                    for entry in atom_order
                },
            ),
            "product": _side_geometry(
                adapter,
                side="product",
                endpoint=step.product,
                selections=prepared.product_component_selections,
                side_artifacts=product_artifacts,
                path_index_by_xyz={
                    entry["product_xyz_index"]: entry["path_index"]
                    for entry in atom_order
                },
            ),
        },
        "geometry": {
            "atom_count": len(reactant_rows),
            "intermolecular_arrangement": "not_provided",
            "endpoint_optimization": "required_downstream",
            "intended_use": (
                "separately embedded component geometries with atom identities for "
                "downstream placement, path search and researcher review"
            ),
        },
    }


def _side_geometry(
    adapter: RDKitAdapter,
    *,
    side: str,
    endpoint: CalculationStepEndpoint,
    selections: tuple[CalculationStateSelection, ...],
    side_artifacts: CalculationArtifacts,
    path_index_by_xyz: Mapping[int, int],
) -> dict[str, object]:
    """Embed each component alone and index its atoms in the canonical order.

    A generated atom is matched to the whole-state artifacts by its owning
    Chemvas atom and its position among that owner's generated atoms, the same
    grouping the step atom correspondence uses.
    """
    side_groups = _atom_map_groups(side_artifacts.atom_map)
    roles = {
        tuple(sorted(role.component_atom_ids)): role.role for role in endpoint.roles
    }
    components: list[dict[str, object]] = []
    covered: list[int] = []
    for selection in selections:
        (component_index,) = selection.component_indices
        label = f"{side} component {component_index}"
        role = roles.get(tuple(sorted(selection.atom_ids)))
        if role is None:
            raise ValueError(f"The {label} has no endpoint role.")
        artifacts = adapter.model_to_calculation_artifacts(
            selection.model,
            atom_annotations=selection.model.atom_annotations,
        )
        if artifacts is None:
            raise ValueError(
                f"The {label}: " + (adapter.last_error or "RDKit conversion failed.")
            )
        if artifacts.rdkit_formal_charge != selection.formal_charge:
            raise ValueError(
                f"RDKit formal charge for the {label} does not match its modeled "
                "formal charge."
            )
        if artifacts.rdkit_radical_electrons != selection.radical_electrons:
            raise ValueError(
                f"RDKit radical electron count for the {label} does not match its "
                "Chemvas marks."
            )
        rows = _xyz_atom_rows(artifacts, label=label)
        component_groups = _atom_map_groups(artifacts.atom_map)
        atom_indices: list[int] = []
        for entry in artifacts.atom_map:
            owner = _atom_map_owner(entry)
            group = component_groups[owner]
            side_group = side_groups.get(owner, ())
            rank = group.index(entry)
            if len(side_group) != len(group) or side_group[rank].symbol != entry.symbol:
                raise ValueError(
                    f"Generated atoms of the {label} do not match the whole-state "
                    "geometry atoms."
                )
            atom_indices.append(path_index_by_xyz[side_group[rank].xyz_index])
        covered.extend(atom_indices)
        xyz = _path_xyz_block(
            rows,
            comment=f"Chemvas {side} component {component_index}; rows follow atom_indices",
        )
        xyz_bytes = xyz.encode("utf-8")
        components.append(
            {
                "component_index": component_index,
                "role": role,
                "chemvas_atom_ids": list(selection.atom_ids),
                "atom_indices": atom_indices,
                "formal_charge": selection.formal_charge,
                "radical_electrons": selection.radical_electrons,
                "electron_count": artifacts.electron_count,
                "multiplicity": None,
                "multiplicity_inference": "not_performed",
                "geometry_generation": {
                    "embedding": artifacts.geometry_embedding,
                    "random_seed": artifacts.geometry_random_seed,
                    "optimization_policy": artifacts.geometry_optimization_policy,
                    "optimization_result": artifacts.geometry_optimization_result,
                },
                "xyz": {
                    "format": "xyz",
                    "content": xyz,
                    "sha256": sha256_hex(xyz_bytes),
                    "bytes": len(xyz_bytes),
                },
            }
        )
    if sorted(covered) != list(range(len(path_index_by_xyz))):
        raise ValueError(
            f"The {side} component geometries do not cover every generated atom once."
        )
    return {
        "assembly": (
            "single_component" if len(components) == 1 else "separated_components"
        ),
        "components": components,
    }


def _atom_map_owner(entry: AtomMapEntry) -> int:
    owner = (
        entry.chemvas_atom_id
        if entry.chemvas_atom_id is not None
        else entry.parent_chemvas_atom_id
    )
    if owner is None:
        raise ValueError(
            "A generated calculation atom has no Chemvas provenance owner."
        )
    return owner


def _atom_map_groups(
    atom_map: tuple[AtomMapEntry, ...],
) -> dict[int, tuple[AtomMapEntry, ...]]:
    groups: dict[int, list[AtomMapEntry]] = {}
    for entry in atom_map:
        groups.setdefault(_atom_map_owner(entry), []).append(entry)
    return {owner: tuple(entries) for owner, entries in groups.items()}


def _indexed_bond_changes(
    atom_order: list[_PathAtomOrderEntry],
    bond_changes: Mapping[str, object],
) -> list[dict[str, object]]:
    raw_changes = bond_changes.get("entries")
    if not isinstance(raw_changes, list):
        raise ValueError("Bond-change entries are missing.")
    path_index_by_atom: dict[int, list[int]] = {}
    for entry in atom_order:
        atom_id = entry["reactant_chemvas_atom_id"]
        if (
            entry["origin"] in {"chemvas_atom", "alias_attachment"}
            and atom_id is not None
        ):
            path_index_by_atom.setdefault(atom_id, []).append(entry["path_index"])
    indexed: list[dict[str, object]] = []
    for change in raw_changes:
        if not isinstance(change, Mapping):
            raise ValueError("Bond-change entry is invalid.")
        atom_ids = change.get("reactant_atom_ids")
        if not isinstance(atom_ids, list) or not all(
            type(item) is int for item in atom_ids
        ):
            raise ValueError("Bond-change atom identities are invalid.")
        atom_indices: list[int] = []
        for atom_id in atom_ids:
            candidates = path_index_by_atom.get(atom_id, [])
            if len(candidates) != 1:
                raise ValueError(
                    f"Bond-change atom {atom_id} has no unique generated geometry atom."
                )
            atom_indices.append(candidates[0])
        indexed.append({**change, "atom_indices": atom_indices})
    return indexed


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


def write_calculation_handoff(output: Path, observation: Mapping[str, object]) -> None:
    """Publish the validated artifact without replacing any existing file."""
    if output.name != "machine.json":
        raise ValueError("Calculation handoff filename must be machine.json")
    text = json.dumps(observation, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_create_bytes(output, text.encode("utf-8", errors="backslashreplace"))
