from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from typing import Any, cast

from chemvas.domain.document.clipboard_validation import (
    validate_clipboard_selection_payload,
)
from chemvas.domain.document.schema import (
    CHEMVAS_FILE_TYPE,
    DOCUMENT_SCHEMA_READERS,
    DOCUMENT_SCHEMAS,
    SUPPORTED_FILE_VERSIONS,
    VALID_ARROW_KINDS,
    VALID_BOND_ORDERS,
    VALID_BOND_STYLES,
    StateDict,
)
from chemvas.domain.document.state_validation import (
    _is_valid_choice,
    _validate_canvas_state,
    _validate_document_state,
)
from chemvas.domain.document.state_values import (
    _bond_pair_key,
    _is_hex_color,
    _is_int,
    _is_number,
    _validated_clipboard_id,
)

from .model import Atom, Bond, MoleculeModel


def atom_to_state(atom: Atom, explicit_label: bool) -> StateDict:
    return {
        "element": atom.element,
        "x": atom.x,
        "y": atom.y,
        "color": atom.color,
        "explicit_label": explicit_label or atom.explicit_label,
    }


def bond_to_state(bond: Bond | None) -> StateDict | None:
    if bond is None:
        return None
    return {
        "a": bond.a,
        "b": bond.b,
        "order": bond.order,
        "style": bond.style,
        "color": bond.color,
    }


def serialize_model_state(
    model: MoleculeModel,
    explicit_label_atom_ids: Collection[int] = (),
) -> StateDict:
    """Serialize ``model`` into a canvas-state model dict.

    Bonds are emitted as the canonical compact list: the in-memory
    deleted-slot tombstones are runtime bookkeeping and never reach the
    document. The output is also normalized to satisfy document validation
    even when the in-memory model has drifted (duplicate bonds, dangling
    endpoints, invalid styles, non-finite coordinates). Saving must never
    fail because of an editing bug — the serializer heals what it can instead
    of letting ``build_document_payload`` reject the user's work.
    """
    state, _warnings = serialize_model_state_with_warnings(
        model, explicit_label_atom_ids
    )
    return state


def serialize_model_state_with_warnings(
    model: MoleculeModel,
    explicit_label_atom_ids: Collection[int] = (),
) -> tuple[StateDict, list[str]]:
    explicit_ids = set(explicit_label_atom_ids)
    warning_counts: dict[str, int] = {}
    atoms: dict[int, StateDict] = {}
    for atom_id, atom in model.atoms.items():
        element = atom.element if isinstance(atom.element, str) else ""
        raw_atom_state = atom_to_state(
            atom,
            explicit_label=(element.upper() == "C" and atom_id in explicit_ids),
        )
        normalized_atom_state = _normalized_atom_state(raw_atom_state.copy())
        _record_atom_serialization_repairs(
            warning_counts, raw_atom_state, normalized_atom_state
        )
        atoms[atom_id] = normalized_atom_state
    bonds: list[StateDict] = []
    seen_bond_pairs: set[tuple[int, int]] = set()
    for bond in model.bonds:
        bond_state = bond_to_state(bond)
        if bond_state is None:
            continue
        a = cast("int", bond_state["a"])
        b = cast("int", bond_state["b"])
        if a == b or a not in atoms or b not in atoms:
            warning_counts["dropped_bonds"] = warning_counts.get("dropped_bonds", 0) + 1
            continue
        if _bond_pair_key(a, b) in seen_bond_pairs:
            warning_counts["duplicate_bonds"] = (
                warning_counts.get("duplicate_bonds", 0) + 1
            )
            continue
        seen_bond_pairs.add(_bond_pair_key(a, b))
        normalized_bond_state = _normalized_bond_state(bond_state.copy())
        _record_bond_serialization_repairs(
            warning_counts, bond_state, normalized_bond_state
        )
        bonds.append(normalized_bond_state)
    state = {
        "atoms": atoms,
        "bonds": bonds,
        "next_atom_id": max(int(model.next_atom_id), max(atoms, default=-1) + 1),
    }
    atom_annotations = _serialized_atom_annotations(
        model.atom_annotations, atoms.keys()
    )
    if atom_annotations:
        state["atom_annotations"] = atom_annotations
    _record_atom_annotation_serialization_repairs(
        warning_counts,
        model.atom_annotations,
        atoms.keys(),
    )
    return state, _model_serialization_warnings(warning_counts)


def _record_atom_serialization_repairs(
    warning_counts: dict[str, int],
    raw_state: Mapping[str, object],
    normalized_state: Mapping[str, object],
) -> None:
    if raw_state.get("element") != normalized_state.get("element"):
        warning_counts["atom_labels"] = warning_counts.get("atom_labels", 0) + 1
    if raw_state.get("x") != normalized_state.get("x") or raw_state.get(
        "y"
    ) != normalized_state.get("y"):
        warning_counts["atom_coordinates"] = (
            warning_counts.get("atom_coordinates", 0) + 1
        )
    if raw_state.get("color") != normalized_state.get("color"):
        warning_counts["atom_colors"] = warning_counts.get("atom_colors", 0) + 1


def _record_bond_serialization_repairs(
    warning_counts: dict[str, int],
    raw_state: Mapping[str, object],
    normalized_state: Mapping[str, object],
) -> None:
    if raw_state.get("order") != normalized_state.get("order"):
        warning_counts["bond_orders"] = warning_counts.get("bond_orders", 0) + 1
    if raw_state.get("style") != normalized_state.get("style"):
        warning_counts["bond_styles"] = warning_counts.get("bond_styles", 0) + 1
    if raw_state.get("color") != normalized_state.get("color"):
        warning_counts["bond_colors"] = warning_counts.get("bond_colors", 0) + 1


def _record_atom_annotation_serialization_repairs(
    warning_counts: dict[str, int],
    raw_annotations: Mapping[int, Mapping[str, int]],
    live_atom_ids: Collection[int],
) -> None:
    live_atom_id_set = set(live_atom_ids)
    for atom_id, annotation in raw_annotations.items():
        if atom_id not in live_atom_id_set and _normalized_atom_annotation(annotation):
            warning_counts["atom_annotations"] = (
                warning_counts.get("atom_annotations", 0) + 1
            )


def _model_serialization_warnings(warning_counts: Mapping[str, int]) -> list[str]:
    warnings: list[str] = []
    _append_count_warning(
        warnings,
        warning_counts.get("atom_labels", 0),
        "1 atom label was replaced with carbon.",
        "{} atom labels were replaced with carbon.",
    )
    _append_count_warning(
        warnings,
        warning_counts.get("atom_coordinates", 0),
        "1 atom position was reset to a finite coordinate.",
        "{} atom positions were reset to finite coordinates.",
    )
    _append_count_warning(
        warnings,
        warning_counts.get("atom_colors", 0),
        "1 atom color was reset to black.",
        "{} atom colors were reset to black.",
    )
    _append_count_warning(
        warnings,
        warning_counts.get("dropped_bonds", 0),
        "1 invalid bond was omitted.",
        "{} invalid bonds were omitted.",
    )
    _append_count_warning(
        warnings,
        warning_counts.get("duplicate_bonds", 0),
        "1 duplicate bond was omitted.",
        "{} duplicate bonds were omitted.",
    )
    _append_count_warning(
        warnings,
        warning_counts.get("bond_orders", 0),
        "1 bond order was reset.",
        "{} bond orders were reset.",
    )
    _append_count_warning(
        warnings,
        warning_counts.get("bond_styles", 0),
        "1 bond style was reset.",
        "{} bond styles were reset.",
    )
    _append_count_warning(
        warnings,
        warning_counts.get("bond_colors", 0),
        "1 bond color was reset to black.",
        "{} bond colors were reset to black.",
    )
    _append_count_warning(
        warnings,
        warning_counts.get("atom_annotations", 0),
        "1 stale atom annotation was omitted.",
        "{} stale atom annotations were omitted.",
    )
    return warnings


def _append_count_warning(
    warnings: list[str], count: int, singular: str, plural: str
) -> None:
    if count == 1:
        warnings.append(singular)
    elif count > 1:
        warnings.append(plural.format(count))


def _normalized_atom_state(atom_state: StateDict) -> StateDict:
    element = atom_state.get("element")
    if not isinstance(element, str) or not element.strip():
        atom_state["element"] = "C"
    for key in ("x", "y"):
        value = atom_state.get(key)
        atom_state[key] = float(cast("Any", value)) if _is_number(value) else 0.0
    if not _is_hex_color(atom_state.get("color")):
        atom_state["color"] = "#000000"
    atom_state["explicit_label"] = bool(atom_state.get("explicit_label"))
    return atom_state


def _normalized_bond_state(bond_state: StateDict) -> StateDict:
    order = bond_state.get("order")
    if not _is_int(order) or order not in VALID_BOND_ORDERS:
        bond_state["order"] = 1
    if not _is_valid_choice(bond_state.get("style"), VALID_BOND_STYLES):
        bond_state["style"] = "single"
    if bond_state["style"] in {"wedge", "hash"} and bond_state["order"] != 1:
        bond_state["order"] = 1
    if bond_state["style"] == "double_either" and bond_state["order"] != 2:
        bond_state["order"] = 2
    if not _is_hex_color(bond_state.get("color")):
        bond_state["color"] = "#000000"
    return bond_state


def deserialize_model_state(model_state: Mapping[str, object]) -> MoleculeModel:
    atoms_state = cast("Mapping[object, Mapping[str, object]]", model_state["atoms"])
    bonds_state = cast("list[object]", model_state["bonds"])
    model = MoleculeModel()
    model.atoms = {
        int(cast("Any", atom_id)): Atom(
            element=cast("str", atom_data["element"]),
            x=float(cast("Any", atom_data["x"])),
            y=float(cast("Any", atom_data["y"])),
            color=cast("str", atom_data["color"]),
            explicit_label=cast("bool", atom_data["explicit_label"]),
        )
        for atom_id, atom_data in atoms_state.items()
    }
    bonds: list[Bond | None] = []
    for bond_data in bonds_state:
        if not isinstance(bond_data, Mapping):
            raise ValueError("Chemvas model bonds must use the compact current form.")
        bonds.append(
            Bond(
                a=int(cast("Any", bond_data["a"])),
                b=int(cast("Any", bond_data["b"])),
                order=int(cast("Any", bond_data["order"])),
                style=cast("str", bond_data["style"]),
                color=cast("str", bond_data["color"]),
            )
        )
    model.bonds = bonds
    model.next_atom_id = max(
        int(cast("Any", model_state["next_atom_id"])),
        max(model.atoms, default=-1) + 1,
    )
    annotations_state = cast(
        "Mapping[object, Mapping[str, object]]", model_state.get("atom_annotations", {})
    )
    model.atom_annotations = {
        int(cast("Any", atom_id)): {
            key: int(cast("Any", value)) for key, value in annotation.items()
        }
        for atom_id, annotation in annotations_state.items()
    }
    return model


def serialize_settings(
    *,
    bond_length_px: float,
    arrow_line_width: float,
    arrow_head_scale: float,
    orbital_phase_enabled: bool,
    text_font_size: int,
    text_font_weight: int,
    text_italic: bool,
    sheet_size: str,
    sheet_orientation: str,
    text_font_family: str = "Arial",
    text_color: str = "#222222",
    text_alignment: str = "left",
    text_line_spacing: float = 1.0,
    note_box_enabled: bool = False,
    note_box_color: str = "#ffffff",
    note_box_alpha: float = 1.0,
    note_border_enabled: bool = False,
    note_border_color: str = "#333333",
    note_border_width: float = 1.0,
    note_padding: float = 6.0,
) -> StateDict:
    return {
        "bond_length_px": bond_length_px,
        "arrow_line_width": arrow_line_width,
        "arrow_head_scale": arrow_head_scale,
        "orbital_phase_enabled": orbital_phase_enabled,
        "text_font_family": text_font_family,
        "text_font_size": text_font_size,
        "text_font_weight": text_font_weight,
        "text_italic": text_italic,
        "text_color": text_color,
        "text_alignment": text_alignment,
        "text_line_spacing": text_line_spacing,
        "note_box_enabled": note_box_enabled,
        "note_box_color": note_box_color,
        "note_box_alpha": note_box_alpha,
        "note_border_enabled": note_border_enabled,
        "note_border_color": note_border_color,
        "note_border_width": note_border_width,
        "note_padding": note_padding,
        "sheet_size": sheet_size,
        "sheet_orientation": sheet_orientation,
    }


def selection_payload_to_canvas_state(
    selection_payload: Mapping[str, object],
    template_settings: Mapping[str, object],
) -> StateDict:
    """Convert a validated clipboard-style selection payload into a canvas state."""
    if not validate_clipboard_selection_payload(selection_payload):
        raise ValueError("Invalid clipboard payload.")

    atoms = cast("list[Mapping[str, object]]", selection_payload.get("atoms", []))
    bonds = cast("list[Mapping[str, object]]", selection_payload.get("bonds", []))
    rings = cast("list[Mapping[str, object]]", selection_payload.get("rings", []))
    marks = cast("list[Mapping[str, object]]", selection_payload.get("marks", []))
    scene_items = cast(
        "list[Mapping[str, object]]", selection_payload.get("scene_items", [])
    )

    atom_states: dict[int, StateDict] = {}
    atom_annotations: dict[int, dict[str, int]] = {}
    for atom_state in atoms:
        atom_id = _validated_clipboard_id(atom_state.get("id"))
        atom_states[atom_id] = {
            "element": atom_state["element"],
            "x": atom_state["x"],
            "y": atom_state["y"],
            "color": atom_state["color"],
            "explicit_label": atom_state["explicit_label"],
        }
        annotation = _normalized_atom_annotation(
            cast("Mapping[str, object] | None", atom_state.get("annotation"))
        )
        if annotation:
            atom_annotations[atom_id] = annotation

    ring_fills: list[StateDict] = []
    note_states: list[StateDict] = []
    arrow_states: list[StateDict] = []
    ts_bracket_states: list[StateDict] = []
    shape_states: list[StateDict] = []
    orbital_states: list[StateDict] = []
    image_states: list[StateDict] = []

    for ring_state in rings:
        ring_fills.append(
            {
                "points": ring_state["points"],
                "atom_ids": ring_state["atom_ids"],
                "color": ring_state["color"],
                "alpha": ring_state["alpha"],
            }
        )

    mark_states = [
        {
            "kind": mark_state["mark_kind"],
            "text": mark_state["text"],
            "atom_id": mark_state["atom_id"],
            "dx": mark_state["dx"],
            "dy": mark_state["dy"],
            "x": mark_state["x"],
            "y": mark_state["y"],
            **({"color": mark_state["color"]} if "color" in mark_state else {}),
        }
        for mark_state in marks
    ]

    item_refs: dict[tuple[str, int], tuple[str, int]] = {
        ("marks", index): ("marks", index) for index in range(len(mark_states))
    }
    for index, item_state in enumerate(scene_items):
        kind = item_state.get("kind")
        if kind == "note":
            item_refs["scene_items", index] = ("notes", len(note_states))
            note_state = {
                "text": item_state["text"],
                "x": item_state["x"],
                "y": item_state["y"],
            }
            if "rotation" in item_state:
                note_state["rotation"] = item_state["rotation"]
            html = item_state.get("html")
            if isinstance(html, str):
                note_state["html"] = html
            note_states.append(note_state)
        elif kind in VALID_ARROW_KINDS:
            item_refs["scene_items", index] = ("arrows", len(arrow_states))
            arrow_states.append(dict(item_state))
        elif kind == "ts_bracket":
            item_refs["scene_items", index] = ("ts_brackets", len(ts_bracket_states))
            ts_bracket_states.append(dict(item_state))
        elif kind == "shape":
            item_refs["scene_items", index] = ("shapes", len(shape_states))
            shape_states.append(dict(item_state))
        elif kind == "image":
            item_refs["scene_items", index] = ("images", len(image_states))
            image_states.append(dict(item_state))
        elif kind == "orbital":
            item_refs["scene_items", index] = ("orbitals", len(orbital_states))
            orbital_states.append(
                {
                    "kind": item_state["orbital_kind"],
                    "center": item_state["center"],
                    "scale": item_state["scale"],
                    "rotation": item_state["rotation"],
                }
            )

    model_state = {
        "atoms": atom_states,
        "bonds": [dict(bond_state) for bond_state in bonds],
        "next_atom_id": max(atom_states, default=-1) + 1,
    }
    if atom_annotations:
        model_state["atom_annotations"] = atom_annotations

    state = {
        "model": model_state,
        "ring_fills": ring_fills,
        "notes": note_states,
        "marks": mark_states,
        "arrows": arrow_states,
        "ts_brackets": ts_bracket_states,
        "shapes": shape_states,
        "orbitals": orbital_states,
        "settings": dict(template_settings),
        "last_smiles_input": None,
    }
    perspective_state = _clipboard_perspective_to_canvas_state(
        selection_payload.get("perspective")
    )
    if perspective_state is not None:
        state["perspective"] = perspective_state
    if image_states:
        state["images"] = image_states
    groups = cast("list[StateDict]", selection_payload.get("groups", []))
    if groups:
        # Clipboard scene_items become separate document collections. Keep the
        # already-selected groups, translating their selection-local references.
        state["groups"] = [
            {
                "atoms": list(group["atoms"]),
                "items": [list(item_refs[key, index]) for key, index in group["items"]],
            }
            for group in groups
        ]
    _validate_canvas_state(state)
    return state


def _clipboard_perspective_to_canvas_state(
    perspective_state: object,
) -> StateDict | None:
    if not isinstance(perspective_state, Mapping):
        return None
    coords_entries = cast(
        "list[Mapping[str, object]]", perspective_state["atom_coords_3d"]
    )
    coords_3d = {
        _validated_clipboard_id(entry["atom_id"]): (
            float(cast("Any", entry["coords"])[0]),
            float(cast("Any", entry["coords"])[1]),
            float(cast("Any", entry["coords"])[2]),
        )
        for entry in coords_entries
    }
    if not coords_3d:
        return None
    center = perspective_state.get("projection_center_3d")
    anchor = perspective_state.get("projection_anchor_2d")
    return {
        "atom_coords_3d": coords_3d,
        "projection_center_3d": tuple(float(value) for value in cast("Any", center))
        if center is not None
        else None,
        "projection_anchor_2d": tuple(float(value) for value in cast("Any", anchor))
        if anchor is not None
        else None,
    }


def build_document_payload(state: StateDict, version: int) -> StateDict:
    _validate_document_state(state, version)
    payload = {
        "type": CHEMVAS_FILE_TYPE,
        "version": version,
        "state": state,
    }
    if version in DOCUMENT_SCHEMAS:
        schema = DOCUMENT_SCHEMAS[version]
        payload.update(
            schema=schema, min_reader=DOCUMENT_SCHEMA_READERS[version, schema]
        )
    return payload


def extract_document_state(payload: object) -> StateDict:
    if not isinstance(payload, dict):
        raise ValueError("Invalid Chemvas file.")
    return _extract_wrapped_document_state(payload)


def _extract_wrapped_document_state(payload: Mapping[str, object]) -> StateDict:
    version = payload.get("version")
    if type(version) is not int:
        raise ValueError("Invalid Chemvas file. version must be an integer.")
    if version not in SUPPORTED_FILE_VERSIONS:
        supported = ", ".join(str(value) for value in sorted(SUPPORTED_FILE_VERSIONS))
        raise ValueError(
            f"Unsupported Chemvas document version {version}. "
            f"This release reads document versions: {supported}. "
            "Open it with a Chemvas release that supports this version."
        )
    expected = {"type", "version", "state"}
    if version == 8:
        expected |= {"schema", "min_reader"}
    if set(payload) != expected:
        raise ValueError(
            "Invalid Chemvas file. Expected only "
            + (
                "type, version, schema, min_reader, and state fields."
                if version == 8
                else "type, version, and state fields."
            )
        )
    state = payload.get("state")
    if payload.get("type") != CHEMVAS_FILE_TYPE or not isinstance(state, dict):
        raise ValueError("Invalid Chemvas file.")
    if version == 8:
        schema = payload.get("schema")
        min_reader = payload.get("min_reader")
        if (
            type(schema) is not int
            or schema < 1
            or not isinstance(min_reader, str)
            or re.fullmatch(
                r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", min_reader
            )
            is None
        ):
            raise ValueError("Invalid Chemvas file. Invalid schema or min_reader.")
        if schema > DOCUMENT_SCHEMAS[version]:
            raise ValueError(
                f"Newer Chemvas document: format {version}, schema {schema}. "
                f"This release reads up to schema {DOCUMENT_SCHEMAS[version]}; "
                f"open it with Chemvas {min_reader} or later."
            )
    _validate_document_state(state, version)
    return state


# --- Shared field validators -------------------------------------------------
# The .chemvas file loader and the clipboard-paste loader enforce the same
# structural rules. Each rule lives exactly once below, parameterized by the
# per-boundary error message (and id validator, where the encodings differ),
# so the two trust boundaries cannot silently drift apart.


# --- .chemvas file validation -------------------------------------------------


def _serialized_atom_annotations(
    atom_annotations: Mapping[int, Mapping[str, int]],
    atom_ids: Collection[int],
) -> dict[int, dict[str, int]]:
    serialized: dict[int, dict[str, int]] = {}
    atom_id_set = set(atom_ids)
    for atom_id, annotation in atom_annotations.items():
        if atom_id not in atom_id_set:
            continue
        normalized = _normalized_atom_annotation(annotation)
        if normalized:
            serialized[atom_id] = normalized
    return serialized


def _normalized_atom_annotation(
    annotation: Mapping[str, object] | None,
) -> dict[str, int]:
    if not isinstance(annotation, Mapping):
        return {}
    normalized: dict[str, int] = {}
    formal_charge = annotation.get("formal_charge")
    if type(formal_charge) is int and formal_charge:
        normalized["formal_charge"] = formal_charge
    radical_electrons = annotation.get("radical_electrons")
    if type(radical_electrons) is int and radical_electrons > 0:
        normalized["radical_electrons"] = radical_electrons
    return normalized
