from __future__ import annotations


def add_bond_for(canvas, a_id: int, b_id: int, order: int = 1) -> int:
    return canvas.services.canvas_bond_mutation_service.add_bond(a_id, b_id, order)


def add_bond_between_points_for(
    canvas, start, end, style: str | None = None, order: int | None = None
):
    settings = canvas.runtime_state.tool_settings_state
    style = style or settings.active_bond_style
    order = settings.active_bond_order if order is None else order
    return canvas.services.structure_build_service.add_bond_between_points(
        start, end, style, order
    )


__all__ = [
    "add_bond_between_points_for",
    "add_bond_for",
]
