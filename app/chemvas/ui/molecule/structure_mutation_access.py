from __future__ import annotations

from chemvas.ui.canvas.canvas_tool_settings_state import tool_settings_state_for


def add_atom_for(canvas, element: str, x: float, y: float) -> int:
    return canvas.services.canvas_atom_mutation_service.add_atom(element, x, y)


def add_bond_for(canvas, a_id: int, b_id: int, order: int = 1) -> int:
    return canvas.services.canvas_bond_mutation_service.add_bond(a_id, b_id, order)


def add_bond_between_points_for(
    canvas, start, end, style: str | None = None, order: int | None = None
):
    settings = tool_settings_state_for(canvas)
    style = style or settings.active_bond_style
    order = settings.active_bond_order if order is None else order
    return canvas.services.structure_build_service.add_bond_between_points(
        start, end, style, order
    )


def add_benzene_ring_for(
    canvas,
    center,
    *,
    attach_atom_id: int | None = None,
    attach_bond_id: int | None = None,
    before_smiles_input: str | None = None,
):
    return canvas.services.structure_build_service.add_benzene_ring(
        center,
        attach_atom_id=attach_atom_id,
        attach_bond_id=attach_bond_id,
        before_smiles_input=before_smiles_input,
    )


__all__ = [
    "add_atom_for",
    "add_benzene_ring_for",
    "add_bond_between_points_for",
    "add_bond_for",
]
