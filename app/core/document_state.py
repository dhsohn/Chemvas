from __future__ import annotations

from collections.abc import Collection, Mapping

from core.model import Atom, Bond, MoleculeModel


LITEDRAW_FILE_TYPE = "litedraw"


def atom_to_state(atom: Atom, explicit_label: bool) -> dict:
    return {
        "element": atom.element,
        "x": atom.x,
        "y": atom.y,
        "color": atom.color,
        "explicit_label": explicit_label or atom.explicit_label,
    }


def bond_to_state(bond: Bond | None) -> dict | None:
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
) -> dict:
    explicit_ids = set(explicit_label_atom_ids)
    atoms = {
        atom_id: atom_to_state(
            atom,
            explicit_label=(atom.element.upper() == "C" and atom_id in explicit_ids),
        )
        for atom_id, atom in model.atoms.items()
    }
    bonds = [bond_to_state(bond) for bond in model.bonds]
    return {
        "atoms": atoms,
        "bonds": bonds,
        "next_atom_id": model.next_atom_id,
    }


def deserialize_model_state(model_state: Mapping[str, object]) -> MoleculeModel:
    atoms_state = model_state.get("atoms", {})
    bonds_state = model_state.get("bonds", [])
    model = MoleculeModel()
    if isinstance(atoms_state, Mapping):
        model.atoms = {
            int(atom_id): Atom(
                element=_mapping_value(atom_data, "element", "C"),
                x=float(_mapping_value(atom_data, "x", 0.0)),
                y=float(_mapping_value(atom_data, "y", 0.0)),
                color=_mapping_value(atom_data, "color", "#000000"),
                explicit_label=bool(_mapping_value(atom_data, "explicit_label", False)),
            )
            for atom_id, atom_data in atoms_state.items()
            if isinstance(atom_data, Mapping)
        }
    bonds: list[Bond | None] = []
    if isinstance(bonds_state, list):
        for bond_data in bonds_state:
            if bond_data is None:
                bonds.append(None)
                continue
            if not isinstance(bond_data, Mapping):
                continue
            bonds.append(
                Bond(
                    a=int(_mapping_value(bond_data, "a", 0)),
                    b=int(_mapping_value(bond_data, "b", 0)),
                    order=int(_mapping_value(bond_data, "order", 1)),
                    style=_mapping_value(bond_data, "style", "single"),
                    color=_mapping_value(bond_data, "color", "#000000"),
                )
            )
    model.bonds = bonds
    model.next_atom_id = int(model_state.get("next_atom_id", len(model.atoms)))
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
) -> dict:
    return {
        "bond_length_px": bond_length_px,
        "arrow_line_width": arrow_line_width,
        "arrow_head_scale": arrow_head_scale,
        "orbital_phase_enabled": orbital_phase_enabled,
        "text_font_size": text_font_size,
        "text_font_weight": text_font_weight,
        "text_italic": text_italic,
    }


def build_document_payload(state: dict, version: int) -> dict:
    return {
        "type": LITEDRAW_FILE_TYPE,
        "version": version,
        "state": state,
    }


def extract_document_state(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Invalid LiteDraw file.")
    state = payload.get("state", payload)
    if not isinstance(state, dict):
        raise ValueError("Invalid LiteDraw file.")
    if "model" in state:
        return state
    if "sheets" in state:
        if not isinstance(state["sheets"], list):
            raise ValueError("Invalid LiteDraw file.")
        return state
    raise ValueError("Invalid LiteDraw file.")


def _mapping_value(mapping: object, key: str, default):
    if not isinstance(mapping, Mapping):
        return default
    value = mapping.get(key, default)
    return default if value is None else value
