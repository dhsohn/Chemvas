from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast

from chemvas.domain.document import (
    VALID_BOND_ORDERS,
    VALID_BOND_STYLES,
    Atom,
    Bond,
    MoleculeModel,
    build_document_payload,
    deserialize_model_state,
    is_document_number,
    is_hex_color,
    serialize_model_state,
)
from chemvas.features.calculation_bundle import (
    inspect_components,
    select_component,
    validate_calculation_plan,
)

DOCUMENT_PATCH_FORMAT = "chemvas-graph-patch"
DOCUMENT_PATCH_VERSION = 1
MAX_PATCH_OPERATIONS = 256

_PATCH_KEYS = frozenset(("format", "version", "source_sha256", "operations"))
_ATOM_FIELDS = frozenset(("element", "x", "y", "color", "explicit_label"))
_ATOM_UPDATE_FIELDS = frozenset(("element", "color", "explicit_label"))
_BOND_UPDATE_FIELDS = frozenset(("order", "style", "color"))
_SUPPORTED_OPERATIONS = (
    "add_atom",
    "update_atom",
    "move_atom",
    "add_bond",
    "update_bond",
    "remove_bond",
)


@dataclass(frozen=True)
class DocumentPatchResult:
    state: dict[str, Any]
    operations: tuple[dict[str, object], ...]
    before: dict[str, int]
    after: dict[str, int]
    calculation_plan_present: bool


def inspect_document_graph(state: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministic, complete graph inventory for an agent."""
    model = _document_model(state)
    components = inspect_components(state)
    annotations: dict[int, dict[str, int]] = {}
    for component in components:
        selection = select_component(state, component.index)
        annotations.update(selection.model.atom_annotations)
    attached_marks: dict[int, list[str]] = {}
    for raw_mark in cast("list[object]", state.get("marks", [])):
        if not isinstance(raw_mark, Mapping):
            continue
        atom_id = _state_atom_id(raw_mark.get("atom_id"))
        kind = raw_mark.get("kind")
        if atom_id is not None and isinstance(kind, str):
            attached_marks.setdefault(atom_id, []).append(kind)

    atoms = [
        {
            "id": atom_id,
            "element": atom.element,
            "x": atom.x,
            "y": atom.y,
            "color": atom.color,
            "explicit_label": atom.explicit_label,
            "annotation": dict(sorted(annotations.get(atom_id, {}).items())),
            "attached_mark_kinds": sorted(attached_marks.get(atom_id, [])),
        }
        for atom_id, atom in sorted(model.atoms.items())
    ]
    bonds = [
        {
            "a": bond.a,
            "b": bond.b,
            "order": bond.order,
            "style": bond.style,
            "color": bond.color,
        }
        for bond in sorted(
            (item for item in model.bonds if item is not None),
            key=lambda item: (_pair(item.a, item.b), item.a, item.b),
        )
    ]
    return {
        "format": "chemvas-document-inspection",
        "version": 1,
        "next_atom_id": model.next_atom_id,
        "atom_count": len(atoms),
        "bond_count": len(bonds),
        "atoms": atoms,
        "bonds": bonds,
        "components": [
            {
                "index": component.index,
                "atom_ids": list(component.atom_ids),
                "formal_charge": component.formal_charge,
                "radical_electrons": component.radical_electrons,
            }
            for component in components
        ],
        "dependencies": {
            "ring_fill_count": len(cast("list[object]", state.get("ring_fills", []))),
            "attached_mark_count": sum(len(items) for items in attached_marks.values()),
            "group_count": len(cast("list[object]", state.get("groups", []))),
            "perspective_present": state.get("perspective") is not None,
            "calculation_plan_present": state.get("calculation_plan") is not None,
        },
        "patch_contract": {
            "format": DOCUMENT_PATCH_FORMAT,
            "version": DOCUMENT_PATCH_VERSION,
            "supported_operations": list(_SUPPORTED_OPERATIONS),
            "atom_ids_are_stable": True,
            "bond_locator": "unordered_atom_endpoint_pair",
            "automatic_chemical_inference": False,
        },
    }


def apply_document_patch(
    state: Mapping[str, object],
    patch: object,
    *,
    source_sha256: str,
    document_version: int,
) -> DocumentPatchResult:
    """Apply a strict graph patch to a private copy and validate all invariants."""
    operations = _validated_patch_operations(patch, source_sha256=source_sha256)
    candidate = cast("dict[str, Any]", deepcopy(dict(state)))
    model = _document_model(candidate)
    # Resolve the dual mark/model representation before mutating anything so an
    # already-conflicting source cannot be laundered through a graph patch.
    inspect_components(candidate)
    before = _counts(candidate, model)
    evidence: list[dict[str, object]] = []
    for index, operation in enumerate(operations):
        try:
            item = _apply_operation(candidate, model, operation)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"operation {index} failed: {exc}") from exc
        evidence.append({"index": index, **item})

    candidate["model"] = serialize_model_state(model)
    try:
        build_document_payload(candidate, document_version)
        if candidate.get("calculation_plan") is not None:
            validate_calculation_plan(candidate, candidate["calculation_plan"])
    except ValueError as exc:
        raise ValueError(
            "patched document would violate a document or Calculation Plan invariant"
        ) from exc
    after = _counts(candidate, model)
    return DocumentPatchResult(
        state=candidate,
        operations=tuple(evidence),
        before=before,
        after=after,
        calculation_plan_present=candidate.get("calculation_plan") is not None,
    )


def _validated_patch_operations(
    patch: object, *, source_sha256: str
) -> list[Mapping[str, object]]:
    if not isinstance(patch, Mapping) or set(patch) != _PATCH_KEYS:
        raise ValueError(
            "patch must contain exactly format, version, source_sha256, operations"
        )
    if patch.get("format") != DOCUMENT_PATCH_FORMAT:
        raise ValueError(f"patch format must be {DOCUMENT_PATCH_FORMAT!r}")
    if type(patch.get("version")) is not int or patch.get("version") != 1:
        raise ValueError("patch version must be 1")
    patch_hash = patch.get("source_sha256")
    if (
        not isinstance(patch_hash, str)
        or len(patch_hash) != 64
        or any(char not in "0123456789abcdef" for char in patch_hash)
    ):
        raise ValueError("source_sha256 must be 64 lowercase hexadecimal characters")
    if patch_hash != source_sha256:
        raise ValueError("source_sha256 does not match the exact input document bytes")
    raw_operations = patch.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("operations must be a non-empty JSON array")
    if len(raw_operations) > MAX_PATCH_OPERATIONS:
        raise ValueError(
            f"operations may contain at most {MAX_PATCH_OPERATIONS} entries"
        )
    operations: list[Mapping[str, object]] = []
    for index, operation in enumerate(raw_operations):
        if not isinstance(operation, Mapping):
            raise ValueError(f"operation {index} must be a JSON object")
        op = operation.get("op")
        if not isinstance(op, str) or op not in _SUPPORTED_OPERATIONS:
            raise ValueError(f"operation {index} has an unsupported op")
        operations.append(operation)
    return operations


def _apply_operation(
    state: dict[str, Any], model: MoleculeModel, operation: Mapping[str, object]
) -> dict[str, object]:
    op = cast("str", operation["op"])
    if op == "add_atom":
        return _add_atom(model, operation)
    if op == "update_atom":
        return _update_atom(model, operation)
    if op == "move_atom":
        return _move_atom(state, model, operation)
    if op == "add_bond":
        return _add_bond(model, operation)
    if op == "update_bond":
        return _update_bond(model, operation)
    return _remove_bond(model, operation)


def _add_atom(
    model: MoleculeModel, operation: Mapping[str, object]
) -> dict[str, object]:
    expected = {"op", "atom_id", *_ATOM_FIELDS}
    _require_exact_keys(operation, expected, "add_atom")
    atom_id = _atom_id(operation.get("atom_id"), "atom_id")
    if atom_id != model.next_atom_id:
        raise ValueError(f"atom_id must equal next_atom_id {model.next_atom_id}")
    atom = Atom(
        element=_element(operation.get("element")),
        x=_number(operation.get("x"), "x"),
        y=_number(operation.get("y"), "y"),
        color=_color(operation.get("color")),
        explicit_label=_boolean(operation.get("explicit_label"), "explicit_label"),
    )
    model.atoms[atom_id] = atom
    model.next_atom_id += 1
    return {"op": "add_atom", "atom_id": atom_id}


def _update_atom(
    model: MoleculeModel, operation: Mapping[str, object]
) -> dict[str, object]:
    _require_exact_keys(operation, {"op", "atom_id", "changes"}, "update_atom")
    atom_id = _atom_id(operation.get("atom_id"), "atom_id")
    atom = _existing_atom(model, atom_id)
    changes = _changes(operation.get("changes"), _ATOM_UPDATE_FIELDS, "update_atom")
    normalized: dict[str, object] = {}
    for field, value in changes.items():
        if field == "element":
            normalized[field] = _element(value)
        elif field == "color":
            normalized[field] = _color(value)
        else:
            normalized[field] = _boolean(value, "explicit_label")
    changed_fields = [
        field for field, value in normalized.items() if getattr(atom, field) != value
    ]
    if not changed_fields:
        raise ValueError("update_atom must change at least one value")
    for field in changed_fields:
        setattr(atom, field, normalized[field])
    return {
        "op": "update_atom",
        "atom_id": atom_id,
        "changed_fields": sorted(changed_fields),
    }


def _move_atom(
    state: dict[str, Any], model: MoleculeModel, operation: Mapping[str, object]
) -> dict[str, object]:
    _require_exact_keys(operation, {"op", "atom_id", "x", "y"}, "move_atom")
    atom_id = _atom_id(operation.get("atom_id"), "atom_id")
    atom = _existing_atom(model, atom_id)
    x = _number(operation.get("x"), "x")
    y = _number(operation.get("y"), "y")
    dx, dy = x - atom.x, y - atom.y
    if dx == 0.0 and dy == 0.0:
        raise ValueError("move_atom must change the atom position")
    atom.x, atom.y = x, y
    _move_ring_points(state, atom_id, x, y)
    _move_attached_marks(state, atom_id, dx, dy)
    _move_perspective_coordinate(state, atom_id, dx, dy)
    return {"op": "move_atom", "atom_id": atom_id, "x": x, "y": y}


def _add_bond(
    model: MoleculeModel, operation: Mapping[str, object]
) -> dict[str, object]:
    _require_exact_keys(
        operation, {"op", "a", "b", "order", "style", "color"}, "add_bond"
    )
    a = _atom_id(operation.get("a"), "a")
    b = _atom_id(operation.get("b"), "b")
    _existing_atom(model, a)
    _existing_atom(model, b)
    order, style, color = _bond_values(
        operation.get("order"), operation.get("style"), operation.get("color")
    )
    bond_id = model.add_bond(a, b, order)
    bond = cast("Bond", model.bonds[bond_id])
    bond.style = style
    bond.color = color
    return {"op": "add_bond", "a": a, "b": b}


def _update_bond(
    model: MoleculeModel, operation: Mapping[str, object]
) -> dict[str, object]:
    _require_exact_keys(operation, {"op", "a", "b", "changes"}, "update_bond")
    a = _atom_id(operation.get("a"), "a")
    b = _atom_id(operation.get("b"), "b")
    bond = _existing_bond(model, a, b)
    changes = _changes(operation.get("changes"), _BOND_UPDATE_FIELDS, "update_bond")
    order = changes.get("order", bond.order)
    style = changes.get("style", bond.style)
    color = changes.get("color", bond.color)
    normalized_order, normalized_style, normalized_color = _bond_values(
        order, style, color
    )
    normalized = {
        "order": normalized_order,
        "style": normalized_style,
        "color": normalized_color,
    }
    changed_fields = [
        field for field in changes if getattr(bond, field) != normalized[field]
    ]
    if not changed_fields:
        raise ValueError("update_bond must change at least one value")
    for field in changed_fields:
        setattr(bond, field, normalized[field])
    return {
        "op": "update_bond",
        "a": bond.a,
        "b": bond.b,
        "changed_fields": sorted(changed_fields),
    }


def _remove_bond(
    model: MoleculeModel, operation: Mapping[str, object]
) -> dict[str, object]:
    _require_exact_keys(operation, {"op", "a", "b"}, "remove_bond")
    a = _atom_id(operation.get("a"), "a")
    b = _atom_id(operation.get("b"), "b")
    bond = _existing_bond(model, a, b)
    model.bonds.remove(bond)
    return {"op": "remove_bond", "a": bond.a, "b": bond.b}


def _move_ring_points(state: dict[str, Any], atom_id: int, x: float, y: float) -> None:
    for ring in cast("list[dict[str, Any]]", state.get("ring_fills", [])):
        atom_ids = cast("list[object]", ring.get("atom_ids", []))
        points = cast("list[object]", ring.get("points", []))
        for index, raw_atom_id in enumerate(atom_ids):
            if _state_atom_id(raw_atom_id) == atom_id:
                points[index] = [x, y]


def _move_attached_marks(
    state: dict[str, Any], atom_id: int, dx: float, dy: float
) -> None:
    for mark in cast("list[dict[str, Any]]", state.get("marks", [])):
        if _state_atom_id(mark.get("atom_id")) == atom_id:
            mark["x"] = float(cast("Any", mark["x"])) + dx
            mark["y"] = float(cast("Any", mark["y"])) + dy


def _move_perspective_coordinate(
    state: dict[str, Any], atom_id: int, dx: float, dy: float
) -> None:
    perspective = state.get("perspective")
    if not isinstance(perspective, dict):
        return
    coordinates = perspective.get("atom_coords_3d")
    if not isinstance(coordinates, dict):
        return
    key: object | None = atom_id if atom_id in coordinates else str(atom_id)
    coords = coordinates.get(key)
    if not isinstance(coords, (list, tuple)) or len(coords) != 3:
        return
    coordinates[key] = [float(coords[0]) + dx, float(coords[1]) + dy, coords[2]]


def _document_model(state: Mapping[str, object]) -> MoleculeModel:
    model_state = state.get("model")
    if not isinstance(model_state, Mapping):
        raise ValueError("document state is missing its model")
    return deserialize_model_state(cast("Mapping[str, object]", model_state))


def _counts(state: Mapping[str, object], model: MoleculeModel) -> dict[str, int]:
    return {
        "atoms": len(model.atoms),
        "bonds": sum(item is not None for item in model.bonds),
        "components": len(inspect_components(state)),
    }


def _existing_atom(model: MoleculeModel, atom_id: int) -> Atom:
    try:
        return model.atoms[atom_id]
    except KeyError as exc:
        raise ValueError(f"atom {atom_id} does not exist") from exc


def _existing_bond(model: MoleculeModel, a: int, b: int) -> Bond:
    if a == b:
        raise ValueError("bond endpoints must be distinct")
    for bond in model.bonds:
        if bond is not None and _pair(bond.a, bond.b) == _pair(a, b):
            return bond
    raise ValueError(f"bond between atoms {min(a, b)} and {max(a, b)} does not exist")


def _changes(
    value: object, allowed: frozenset[str], operation: str
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not value or not set(value) <= allowed:
        names = ", ".join(sorted(allowed))
        raise ValueError(f"{operation} changes must be a non-empty subset of: {names}")
    return cast("Mapping[str, object]", value)


def _require_exact_keys(
    value: Mapping[str, object], expected: set[str], operation: str
) -> None:
    if set(value) != expected:
        raise ValueError(f"{operation} has missing or unknown keys")


def _atom_id(value: object, field: str) -> int:
    if type(value) is not int or cast("int", value) < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return cast("int", value)


def _state_atom_id(value: object) -> int | None:
    if type(value) is int:
        return cast("int", value)
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return None


def _element(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("element must be a non-empty string")
    return value


def _number(value: object, field: str) -> float:
    if not is_document_number(value):
        raise ValueError(f"{field} must be a finite JSON-safe number")
    return float(cast("Any", value))


def _color(value: object) -> str:
    if not is_hex_color(value):
        raise ValueError("color must be #rgb or #rrggbb hexadecimal")
    return cast("str", value)


def _boolean(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field} must be a boolean")
    return cast("bool", value)


def _bond_values(
    order_value: object, style_value: object, color_value: object
) -> tuple[int, str, str]:
    if type(order_value) is not int or order_value not in VALID_BOND_ORDERS:
        raise ValueError("bond order must be 1, 2, or 3")
    if not isinstance(style_value, str) or style_value not in VALID_BOND_STYLES:
        raise ValueError("bond style is not supported")
    if style_value in {"wedge", "hash"} and order_value != 1:
        raise ValueError("wedge/hash bonds must have order 1")
    return cast("int", order_value), style_value, _color(color_value)


def _pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)
