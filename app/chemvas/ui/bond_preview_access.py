from __future__ import annotations

import math

from PyQt6.QtCore import QPointF

from chemvas.ui.bond_preview_renderer import (
    add_bond_preview_items,
    build_bond_preview_items,
    clear_bond_preview_items,
    update_bond_preview_items,
)
from chemvas.ui.bond_renderer_access import bond_renderer_for
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.renderer_style_access import (
    bond_length_px_for,
    renderer_for,
)
from chemvas.ui.scene_item_access import canvas_scene_for
from chemvas.ui.structure_geometry_access import default_bond_endpoint_for


def _preview_atom_ids(atom_ids: tuple) -> tuple[int | None, int | None]:
    a_id = atom_ids[0] if len(atom_ids) >= 1 else None
    b_id = atom_ids[1] if len(atom_ids) >= 2 else None
    return a_id, b_id


def _bond_preview_style_for(
    canvas,
    *,
    style: str | None = None,
    order: int | None = None,
) -> tuple[str, int]:
    settings = tool_settings_state_for(canvas)
    return (
        style or settings.active_bond_style,
        settings.active_bond_order if order is None else order,
    )


def build_bond_preview_items_for(
    canvas, start: QPointF, end: QPointF, *atom_ids
) -> list:
    a_id, b_id = _preview_atom_ids(atom_ids)
    style, order = _bond_preview_style_for(canvas)
    return build_bond_preview_items(
        start,
        end,
        style=style,
        order=order,
        a_id=a_id,
        b_id=b_id,
        canvas_renderer=renderer_for(canvas),
        bond_renderer=bond_renderer_for(canvas),
    )


def clear_bond_preview_items_for(canvas, items: list) -> list:
    return clear_bond_preview_items(canvas_scene_for(canvas), items)


def add_bond_preview_items_for(canvas, items: list) -> list:
    return add_bond_preview_items(canvas_scene_for(canvas), items)


def update_bond_preview_items_for(
    canvas,
    items: list,
    start: QPointF,
    end: QPointF,
    *,
    a_id: int | None = None,
    b_id: int | None = None,
    style: str | None = None,
    order: int | None = None,
) -> bool:
    resolved_style, resolved_order = _bond_preview_style_for(
        canvas, style=style, order=order
    )
    return update_bond_preview_items(
        items,
        start,
        end,
        style=resolved_style,
        order=resolved_order,
        a_id=a_id,
        b_id=b_id,
        canvas_renderer=renderer_for(canvas),
        bond_renderer=bond_renderer_for(canvas),
    )


def bond_hover_endpoint_for(
    canvas,
    start: QPointF,
    pos: QPointF,
    start_atom_id: int | None = None,
) -> QPointF:
    if start_atom_id is not None:
        return default_bond_endpoint_for(canvas, start, start_atom_id)
    dx = pos.x() - start.x()
    dy = pos.y() - start.y()
    length = math.hypot(dx, dy)
    angle = 0.0 if length <= 1e-6 else math.degrees(math.atan2(dy, dx))
    step = tool_settings_state_for(canvas).snap_angle_step or 30
    snap_angle = round(angle / step) * step
    bond_len = bond_length_px_for(canvas)
    rad = math.radians(snap_angle)
    return QPointF(
        start.x() + math.cos(rad) * bond_len, start.y() + math.sin(rad) * bond_len
    )


__all__ = [
    "add_bond_preview_items_for",
    "bond_hover_endpoint_for",
    "build_bond_preview_items_for",
    "clear_bond_preview_items_for",
    "update_bond_preview_items_for",
]
