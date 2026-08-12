from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from .precomplex_profile import (
    LEGACY_PROFILE_ID,
    precomplex_placement_profile,
    radius_provenance_for,
)

MAX_ATOMS = 2000
MAX_XYZ_BYTES = 512_000
NO_PRECOMPLEX_JSON = '{"kind":"none"}'
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_CANDIDATE_ID_RE = re.compile(r"pc-[0-9a-f]{64}\Z")
_CONFORMER_ID_RE = re.compile(r"conf-[0-9a-f]{64}\Z")


def canonicalize_precomplex_state(
    value: object,
    *,
    side: str,
    included_components: tuple[tuple[int, ...], ...],
) -> tuple[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("Invalid endpoint precomplex state.")
    kind = value.get("kind")
    if kind == "none":
        if set(value) != {"kind"}:
            raise ValueError("Invalid empty endpoint precomplex state.")
        return "none", NO_PRECOMPLEX_JSON
    if kind != "candidate_ensemble":
        raise ValueError("Invalid endpoint precomplex candidate ensemble.")
    profile_id = value.get("profile")
    if not isinstance(profile_id, str):
        raise ValueError("Endpoint precomplex profile is invalid.")
    profile = precomplex_placement_profile(profile_id)
    expected_fields = {
        "kind",
        "source_document_sha256",
        "basis_sha256",
        "side",
        "profile",
        "environment",
        "contacts",
        "source_geometry",
        "candidates",
        "selection",
    }
    if profile.id != LEGACY_PROFILE_ID:
        expected_fields.add("radius_provenance")
    if set(value) != expected_fields:
        raise ValueError("Invalid endpoint precomplex candidate ensemble.")
    if value.get("side") != side:
        raise ValueError("Endpoint precomplex side or profile does not match.")
    if profile.id != LEGACY_PROFILE_ID and value.get(
        "radius_provenance"
    ) != radius_provenance_for(profile.id):
        raise ValueError(
            "Endpoint precomplex radius provenance does not match profile."
        )
    source_document_sha256 = _sha256(
        value.get("source_document_sha256"), "source_document_sha256"
    )
    basis_sha256 = _sha256(value.get("basis_sha256"), "basis_sha256")
    _validate_environment(value.get("environment"))
    contacts = _validate_contacts(value.get("contacts"), included_components)
    atom_symbols = _validate_source_geometry(
        value.get("source_geometry"), included_components
    )
    candidates = value.get("candidates")
    if (
        not isinstance(candidates, list)
        or not 1 <= len(candidates) <= profile.max_candidates
    ):
        raise ValueError("Endpoint precomplex candidates exceed the bounded profile.")
    candidate_hash_by_id: dict[str, str] = {}
    for candidate in candidates:
        candidate_id, xyz_sha256 = _validate_candidate(
            candidate,
            atom_symbols,
            source_document_sha256=source_document_sha256,
            basis_sha256=basis_sha256,
            step_side=side,
            contacts=contacts,
            included_components=included_components,
            profile_id=profile.id,
        )
        if candidate_id in candidate_hash_by_id:
            raise ValueError("Endpoint precomplex candidate ids must be unique.")
        candidate_hash_by_id[candidate_id] = xyz_sha256
    selection = value.get("selection")
    if selection is not None:
        _validate_selection(selection, candidate_hash_by_id)
    canonical = json.dumps(
        _normalize_json_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "candidate_ensemble", canonical


def precomplex_state_from_json(payload_json: str) -> dict[str, object]:
    value = json.loads(payload_json)
    if not isinstance(value, dict):
        raise ValueError("Invalid canonical endpoint precomplex state.")
    return value


def _validate_environment(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("Endpoint precomplex environment is required.")
    kind = value.get("kind")
    if kind == "gas_phase":
        if set(value) != {"kind"}:
            raise ValueError("Invalid gas-phase precomplex environment.")
        return
    if kind == "solvent" and set(value) == {"kind", "model", "name"}:
        _short_string(value.get("model"), "solvent model")
        _short_string(value.get("name"), "solvent name")
        return
    raise ValueError("Invalid endpoint precomplex environment.")


def _validate_contacts(
    value: object,
    included_components: tuple[tuple[int, ...], ...],
) -> tuple[dict[str, object], ...]:
    if len(included_components) != 2:
        raise ValueError(
            "The placement profile requires exactly two included components."
        )
    if not isinstance(value, list) or len(value) != 1:
        raise ValueError("The placement profile requires one explicit contact.")
    contact = value[0]
    if not isinstance(contact, Mapping) or set(contact) != {
        "id",
        "first_atom_id",
        "second_atom_id",
        "target_distance_angstrom",
        "tolerance_angstrom",
    }:
        raise ValueError("Invalid endpoint precomplex contact.")
    _short_string(contact.get("id"), "contact id")
    first = _plain_int(contact.get("first_atom_id"), "first contact atom")
    second = _plain_int(contact.get("second_atom_id"), "second contact atom")
    owners = [
        index
        for index, component in enumerate(included_components)
        if first in component or second in component
    ]
    first_owners = [
        index
        for index, component in enumerate(included_components)
        if first in component
    ]
    second_owners = [
        index
        for index, component in enumerate(included_components)
        if second in component
    ]
    if (
        len(first_owners) != 1
        or len(second_owners) != 1
        or first_owners == second_owners
    ):
        raise ValueError("Endpoint precomplex contact must join included components.")
    if len(set(owners)) != 2:
        raise ValueError("Endpoint precomplex contact graph is incomplete.")
    target = _finite_number(contact.get("target_distance_angstrom"), "contact target")
    tolerance = _finite_number(contact.get("tolerance_angstrom"), "contact tolerance")
    if target <= 0.0 or tolerance < 0.0 or tolerance > 1.0:
        raise ValueError(
            "Endpoint precomplex contact distance is outside profile bounds."
        )
    return (
        {
            "id": contact.get("id"),
            "first_atom_id": first,
            "second_atom_id": second,
            "target_distance_angstrom": target,
            "tolerance_angstrom": tolerance,
        },
    )


def _validate_source_geometry(
    value: object,
    included_components: tuple[tuple[int, ...], ...],
) -> tuple[str, ...]:
    expected = {
        "rdkit_version",
        "rdkit_formal_charge",
        "rdkit_radical_electrons",
        "electron_count",
        "geometry_embedding",
        "geometry_random_seed",
        "geometry_optimization_policy",
        "geometry_optimization_result",
        "mol_atom_count",
        "xyz_atom_count",
        "atom_map",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("Invalid endpoint precomplex source geometry.")
    for key in (
        "rdkit_version",
        "geometry_embedding",
        "geometry_optimization_policy",
        "geometry_optimization_result",
    ):
        _short_string(value.get(key), key)
    result = value.get("geometry_optimization_result")
    if not isinstance(result, str) or not result.endswith("_converged"):
        raise ValueError("Endpoint precomplex source geometry did not converge.")
    for key in (
        "rdkit_formal_charge",
        "rdkit_radical_electrons",
        "electron_count",
        "geometry_random_seed",
        "mol_atom_count",
        "xyz_atom_count",
    ):
        _plain_int(value.get(key), key)
    xyz_count = value.get("xyz_atom_count")
    mol_count = value.get("mol_atom_count")
    if (
        not isinstance(xyz_count, int)
        or not isinstance(mol_count, int)
        or not 1 <= mol_count <= xyz_count <= MAX_ATOMS
    ):
        raise ValueError("Endpoint precomplex source geometry atom counts are invalid.")
    atom_map = value.get("atom_map")
    if not isinstance(atom_map, list) or len(atom_map) != xyz_count:
        raise ValueError("Endpoint precomplex source atom map count is invalid.")
    included_ids = {
        atom_id for component in included_components for atom_id in component
    }
    symbols: list[str] = []
    expected_keys = {
        "xyz_index",
        "mol_index",
        "symbol",
        "origin",
        "chemvas_atom_id",
        "parent_xyz_index",
        "parent_chemvas_atom_id",
    }
    for expected_index, entry in enumerate(atom_map, start=1):
        if not isinstance(entry, Mapping) or set(entry) != expected_keys:
            raise ValueError("Invalid endpoint precomplex atom map entry.")
        if entry.get("xyz_index") != expected_index:
            raise ValueError("Endpoint precomplex atom map is not contiguous.")
        symbol = entry.get("symbol")
        origin = entry.get("origin")
        if not isinstance(symbol, str) or not symbol or len(symbol) > 3:
            raise ValueError("Invalid endpoint precomplex atom symbol.")
        _short_string(origin, "atom origin")
        chemvas_id = _optional_plain_int(
            entry.get("chemvas_atom_id"), "Chemvas atom id"
        )
        parent_id = _optional_plain_int(
            entry.get("parent_chemvas_atom_id"), "parent Chemvas atom id"
        )
        owner = chemvas_id if chemvas_id is not None else parent_id
        if owner not in included_ids:
            raise ValueError("Endpoint precomplex atom ownership is incomplete.")
        mol_index = _optional_plain_int(entry.get("mol_index"), "mol index")
        parent_xyz = _optional_plain_int(
            entry.get("parent_xyz_index"), "parent xyz index"
        )
        if mol_index is not None and not 1 <= mol_index <= mol_count:
            raise ValueError("Endpoint precomplex mol index is invalid.")
        if parent_xyz is not None and not 1 <= parent_xyz <= xyz_count:
            raise ValueError("Endpoint precomplex parent xyz index is invalid.")
        symbols.append(symbol)
    return tuple(symbols)


def _validate_candidate(
    value: object,
    atom_symbols: tuple[str, ...],
    *,
    source_document_sha256: str,
    basis_sha256: str,
    step_side: str,
    contacts: tuple[dict[str, object], ...],
    included_components: tuple[tuple[int, ...], ...],
    profile_id: str,
) -> tuple[str, str]:
    profile = precomplex_placement_profile(profile_id)
    if not isinstance(value, Mapping) or set(value) != {
        "id",
        "geometry_class",
        "xyz",
        "xyz_sha256",
        "transform",
        "component_conformer_ids",
        "validation",
    }:
        raise ValueError("Invalid endpoint precomplex candidate.")
    candidate_id = value.get("id")
    if (
        not isinstance(candidate_id, str)
        or _CANDIDATE_ID_RE.fullmatch(candidate_id) is None
    ):
        raise ValueError("Invalid endpoint precomplex candidate id.")
    if value.get("geometry_class") != "generated_candidate_ensemble":
        raise ValueError("Invalid endpoint precomplex geometry class.")
    xyz = value.get("xyz")
    if (
        not isinstance(xyz, str)
        or not xyz.endswith("\n")
        or len(xyz.encode("utf-8")) > MAX_XYZ_BYTES
    ):
        raise ValueError("Invalid endpoint precomplex XYZ payload.")
    try:
        xyz_bytes = xyz.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("Endpoint precomplex XYZ must be ASCII.") from exc
    xyz_sha256 = _sha256(value.get("xyz_sha256"), "candidate xyz_sha256")
    if hashlib.sha256(xyz_bytes).hexdigest() != xyz_sha256:
        raise ValueError("Endpoint precomplex candidate XYZ hash mismatch.")
    _validate_xyz(xyz, atom_symbols)
    transform = value.get("transform")
    if not isinstance(transform, Mapping) or set(transform) != {
        "approach_index",
        "rotation_index",
        "approach_vector",
    }:
        raise ValueError("Invalid endpoint precomplex transform.")
    approach_index = _plain_int(transform.get("approach_index"), "approach index")
    rotation_index = _plain_int(transform.get("rotation_index"), "rotation index")
    if (
        not 0 <= approach_index < profile.approach_sample_count
        or not 0 <= rotation_index < profile.rotation_sample_count
    ):
        raise ValueError("Endpoint precomplex transform is outside profile bounds.")
    vector = transform.get("approach_vector")
    if not isinstance(vector, list) or len(vector) != 3:
        raise ValueError("Invalid endpoint precomplex approach vector.")
    coordinates = [_finite_number(item, "approach vector") for item in vector]
    norm = math.sqrt(sum(item * item for item in coordinates))
    if abs(norm - 1.0) > 1e-9:
        raise ValueError("Endpoint precomplex approach vector is not normalized.")
    conformers = value.get("component_conformer_ids")
    if not isinstance(conformers, list) or len(conformers) != 2:
        raise ValueError("Invalid endpoint precomplex conformer provenance.")
    for conformer in conformers:
        if (
            not isinstance(conformer, str)
            or _CONFORMER_ID_RE.fullmatch(conformer) is None
        ):
            raise ValueError("Invalid endpoint precomplex conformer id.")
    _validate_metrics(value.get("validation"))
    identity = {
        "profile": profile.id,
        "source_sha256": source_document_sha256,
        "plan_sha256": basis_sha256,
        "step_id": _xyz_step_id(xyz, profile_id=profile.id),
        "side": step_side,
        "contacts": list(contacts),
        "component_atom_ids": [list(component) for component in included_components],
        "component_conformer_ids": conformers,
        "approach_index": approach_index,
        "rotation_index": rotation_index,
        "xyz_sha256": xyz_sha256,
    }
    canonical_identity = json.dumps(
        identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    expected_id = "pc-" + hashlib.sha256(canonical_identity.encode("ascii")).hexdigest()
    if candidate_id != expected_id:
        raise ValueError(
            "Endpoint precomplex candidate id does not match its provenance."
        )
    return candidate_id, xyz_sha256


def _xyz_step_id(xyz: str, *, profile_id: str) -> str:
    comment = xyz.splitlines()[1].split()
    if len(comment) != 4 or comment[:2] != ["Chemvas", profile_id]:
        raise ValueError("Endpoint precomplex XYZ comment provenance is invalid.")
    return comment[2]


def _validate_xyz(xyz: str, atom_symbols: tuple[str, ...]) -> None:
    lines = xyz.splitlines()
    if len(lines) != len(atom_symbols) + 2:
        raise ValueError("Endpoint precomplex XYZ atom count is invalid.")
    try:
        declared = int(lines[0].strip())
    except ValueError as exc:
        raise ValueError("Endpoint precomplex XYZ count is invalid.") from exc
    if declared != len(atom_symbols):
        raise ValueError("Endpoint precomplex XYZ count does not match the atom map.")
    for expected_symbol, row in zip(atom_symbols, lines[2:], strict=True):
        fields = row.split()
        if len(fields) != 4 or fields[0] != expected_symbol:
            raise ValueError(
                "Endpoint precomplex XYZ symbols do not match the atom map."
            )
        for coordinate in fields[1:]:
            _finite_number_from_string(coordinate, "XYZ coordinate")


def _validate_metrics(value: object) -> None:
    expected = {
        "hard_clash_count",
        "soft_overlap_score",
        "contact_error_angstrom",
        "limiting_pair",
        "limiting_distance_angstrom",
        "limiting_threshold_angstrom",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("Invalid endpoint precomplex validation metrics.")
    if value.get("hard_clash_count") != 0:
        raise ValueError("A hard-clashing precomplex candidate cannot be persisted.")
    for key in ("soft_overlap_score", "contact_error_angstrom"):
        if _finite_number(value.get(key), key) < 0.0:
            raise ValueError("Endpoint precomplex validation metric is negative.")
    pair = value.get("limiting_pair")
    distance = value.get("limiting_distance_angstrom")
    threshold = value.get("limiting_threshold_angstrom")
    if pair is None:
        if distance is not None or threshold is not None:
            raise ValueError(
                "Endpoint precomplex limiting-pair metrics are incomplete."
            )
    else:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("Invalid endpoint precomplex limiting pair.")
        _plain_int(pair[0], "limiting atom index")
        _plain_int(pair[1], "limiting atom index")
        _finite_number(distance, "limiting distance")
        _finite_number(threshold, "limiting threshold")


def _validate_selection(value: object, candidates: Mapping[str, str]) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "candidate_id",
        "candidate_xyz_sha256",
        "reviewer",
        "reviewed_at",
        "acceptance_statement",
    }:
        raise ValueError("Invalid endpoint precomplex selection.")
    candidate_id = value.get("candidate_id")
    xyz_sha256 = value.get("candidate_xyz_sha256")
    if not isinstance(candidate_id, str) or candidates.get(candidate_id) != xyz_sha256:
        raise ValueError(
            "Endpoint precomplex selection does not bind a candidate geometry."
        )
    _sha256(xyz_sha256, "selected candidate xyz_sha256")
    _short_string(value.get("reviewer"), "reviewer")
    reviewed_at = _short_string(value.get("reviewed_at"), "review timestamp")
    try:
        datetime.strptime(reviewed_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError("Invalid endpoint precomplex review timestamp.") from exc
    if value.get("acceptance_statement") != "accepted_for_path_endpoint_review":
        raise ValueError(
            "Endpoint precomplex selection lacks the acceptance statement."
        )


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"Invalid endpoint precomplex {label}.")
    return value


def _short_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError(f"Invalid endpoint precomplex {label}.")
    return value


def _plain_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Invalid endpoint precomplex {label}.")
    return value


def _optional_plain_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _plain_int(value, label)


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"Invalid endpoint precomplex {label}.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Invalid endpoint precomplex {label}.")
    return number


def _finite_number_from_string(value: str, label: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(f"Invalid endpoint precomplex {label}.") from exc
    if not math.isfinite(number):
        raise ValueError(f"Invalid endpoint precomplex {label}.")
    return number


def _normalize_json_value(value: object) -> object:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, Mapping):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    return value


__all__ = [
    "NO_PRECOMPLEX_JSON",
    "canonicalize_precomplex_state",
    "precomplex_state_from_json",
]
