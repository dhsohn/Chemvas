from __future__ import annotations

from chemvas.domain.document import MoleculeModel
from chemvas.features.insertion import (
    build_3d_conversion_payload as build_3d_conversion_payload_state,
)
from chemvas.features.insertion import (
    build_structure_payload as build_structure_payload_state,
)
from chemvas.ui.canvas_model_access import model_for
from chemvas.ui.mark_item_access import mark_kinds_by_atom_for
from chemvas.ui.selection_collection_access import selected_structure_ids_for
from chemvas.ui.selection_geometry_access import bounds_for_atoms_for


def build_3d_conversion_payload_for(
    canvas,
) -> tuple[MoleculeModel, dict[int, dict[str, int]]]:
    atom_ids, bond_ids = selected_structure_ids_for(canvas)
    return build_3d_conversion_payload_state(
        model_for(canvas),
        atom_ids,
        bond_ids,
        mark_kinds_by_atom_for(canvas),
        bounds_getter=lambda ids, include_labels=False: bounds_for_atoms_for(
            canvas,
            ids,
            include_labels=include_labels,
        ),
    )


def build_selected_3d_conversion_payload_for(
    canvas,
) -> tuple[MoleculeModel, dict[int, dict[str, int]]]:
    try:
        atom_ids, bond_ids = selected_structure_ids_for(canvas, require_non_empty=True)
    except ValueError as exc:
        raise ValueError("No chemical structure selected.") from exc
    return build_3d_conversion_payload_state(
        model_for(canvas),
        atom_ids,
        bond_ids,
        mark_kinds_by_atom_for(canvas),
        bounds_getter=lambda ids, include_labels=False: bounds_for_atoms_for(
            canvas,
            ids,
            include_labels=include_labels,
        ),
    )


def build_selected_structure_payload_for(
    canvas,
) -> tuple[MoleculeModel, dict[int, dict[str, int]], tuple[float, float, float, float]]:
    atom_ids, bond_ids = selected_structure_ids_for(canvas, require_non_empty=True)
    return build_structure_payload_for(canvas, atom_ids, bond_ids)


def build_structure_payload_for(
    canvas,
    atom_ids: set[int],
    bond_ids: set[int],
) -> tuple[MoleculeModel, dict[int, dict[str, int]], tuple[float, float, float, float]]:
    return build_structure_payload_state(
        model_for(canvas),
        atom_ids,
        bond_ids,
        mark_kinds_by_atom_for(canvas),
        bounds_getter=lambda ids, include_labels=False: bounds_for_atoms_for(
            canvas,
            ids,
            include_labels=include_labels,
        ),
    )


__all__ = [
    "build_3d_conversion_payload_for",
    "build_selected_3d_conversion_payload_for",
    "build_selected_structure_payload_for",
    "build_structure_payload_for",
]
