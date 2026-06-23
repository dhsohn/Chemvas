from __future__ import annotations

from typing import Any

from ui.canvas_rdkit_state import new_rdkit_adapter, rdkit_adapter_for


def rdkit_last_error_for(canvas: Any) -> str | None:
    return getattr(rdkit_adapter_for(canvas), "last_error", None)


def smiles_to_2d_for(canvas: Any, smiles: str, *, scale: float):
    return rdkit_adapter_for(canvas).smiles_to_2d(smiles, scale=scale)


def model_to_xyz_block_for(canvas: Any, model, *, atom_annotations):
    return rdkit_adapter_for(canvas).model_to_xyz_block(model, atom_annotations=atom_annotations)


def model_to_mol_block_for(canvas: Any, model, *, atom_annotations):
    return rdkit_adapter_for(canvas).model_to_mol_block(model, atom_annotations=atom_annotations)


def rdkit_is_loaded_for(canvas: Any) -> bool:
    return bool(rdkit_adapter_for(canvas).is_loaded())


def rdkit_is_unavailable_for(canvas: Any) -> bool:
    return bool(rdkit_adapter_for(canvas).is_unavailable())


def preload_rdkit_for(canvas: Any) -> bool:
    return bool(rdkit_adapter_for(canvas).preload())


def compute_props_for(canvas: Any, model):
    return rdkit_adapter_for(canvas).compute_props(model)


def compute_identifiers_for(canvas: Any, model):
    return rdkit_adapter_for(canvas).compute_identifiers(model)


__all__ = [
    "compute_identifiers_for",
    "compute_props_for",
    "model_to_mol_block_for",
    "model_to_xyz_block_for",
    "new_rdkit_adapter",
    "preload_rdkit_for",
    "rdkit_adapter_for",
    "rdkit_is_loaded_for",
    "rdkit_is_unavailable_for",
    "rdkit_last_error_for",
    "smiles_to_2d_for",
]
