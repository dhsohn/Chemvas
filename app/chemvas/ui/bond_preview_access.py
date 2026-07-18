from __future__ import annotations

import math

from PyQt6.QtCore import QPointF

from chemvas.ui.bond_graphics_access import (
    dotted_bond_path_for,
    draw_dotted_bond_for,
    draw_hash_bond_for,
    draw_parallel_bonds_for,
    draw_wedge_bond_for,
    hash_segments_for,
    line_normal_for,
    one_sided_bond_strip_for,
    parallel_bond_segments_for,
    strip_polygon_for,
    wedge_polygon_for,
)
from chemvas.ui.bond_preview_renderer import (
    BondPreviewBuildResolvers,
    BondPreviewConfig,
    BondPreviewUpdateResolvers,
)
from chemvas.ui.bond_preview_renderer import (
    add_bond_preview_items as add_bond_preview_items_helper,
)
from chemvas.ui.bond_preview_renderer import (
    build_bond_preview_items as build_bond_preview_items_helper,
)
from chemvas.ui.bond_preview_renderer import (
    clear_bond_preview_items as clear_bond_preview_items_helper,
)
from chemvas.ui.bond_preview_renderer import (
    update_bond_preview_items as update_bond_preview_items_helper,
)
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.renderer_style_access import (
    bold_bond_width_for,
    bond_length_px_for,
    bond_line_width_for,
    bond_pen_for,
    dotted_bond_pen_for,
    hash_spacing_px_for,
)
from chemvas.ui.scene_item_access import canvas_scene_for
from chemvas.ui.structure_geometry_access import default_bond_endpoint_for


def _preview_atom_ids(atom_ids: tuple) -> tuple[int | None, int | None]:
    a_id = atom_ids[0] if len(atom_ids) >= 1 else None
    b_id = atom_ids[1] if len(atom_ids) >= 2 else None
    return a_id, b_id


def bond_preview_config_for(
    canvas,
    *,
    style: str | None = None,
    order: int | None = None,
) -> BondPreviewConfig:
    settings = tool_settings_state_for(canvas)
    return BondPreviewConfig(
        style=style or settings.active_bond_style,
        order=settings.active_bond_order if order is None else order,
        bond_length_px=bond_length_px_for(canvas),
        bond_line_width=bond_line_width_for(canvas),
        bold_bond_width=bold_bond_width_for(canvas),
        hash_spacing_px=hash_spacing_px_for(canvas),
    )


def _bond_preview_build_resolvers_for(canvas) -> BondPreviewBuildResolvers:
    return BondPreviewBuildResolvers(
        draw_wedge_bond=lambda *args: draw_wedge_bond_for(canvas, *args),
        draw_hash_bond=lambda *args: draw_hash_bond_for(canvas, *args),
        draw_dotted_bond=lambda *args: draw_dotted_bond_for(canvas, *args),
        draw_parallel_bonds=lambda *args: draw_parallel_bonds_for(canvas, *args),
        line_normal=lambda x1, y1, x2, y2, target: line_normal_for(
            canvas, x1, y1, x2, y2, target
        ),
        one_sided_bond_strip=lambda *args: one_sided_bond_strip_for(canvas, *args),
        bond_pen=lambda: bond_pen_for(canvas),
        dotted_bond_pen=lambda: dotted_bond_pen_for(canvas),
    )


def bond_preview_update_resolvers_for(canvas) -> BondPreviewUpdateResolvers:
    return BondPreviewUpdateResolvers(
        wedge_polygon=lambda *args: wedge_polygon_for(canvas, *args),
        hash_segments=lambda *args: hash_segments_for(canvas, *args),
        dotted_bond_path=lambda *args: dotted_bond_path_for(canvas, *args),
        parallel_bond_segments=lambda *args: parallel_bond_segments_for(canvas, *args),
        line_normal=lambda *args: line_normal_for(canvas, *args),
        strip_polygon=lambda *args: strip_polygon_for(canvas, *args),
    )


def build_bond_preview_items_for(
    canvas, start: QPointF, end: QPointF, *atom_ids
) -> list:
    a_id, b_id = _preview_atom_ids(atom_ids)
    return build_bond_preview_items_helper(
        start,
        end,
        config=bond_preview_config_for(canvas),
        a_id=a_id,
        b_id=b_id,
        resolvers=_bond_preview_build_resolvers_for(canvas),
    )


def clear_bond_preview_items_for(canvas, items: list) -> list:
    return clear_bond_preview_items_helper(canvas_scene_for(canvas), items)


def add_bond_preview_items_for(canvas, items: list) -> list:
    return add_bond_preview_items_helper(canvas_scene_for(canvas), items)


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
    return update_bond_preview_items_helper(
        items,
        start,
        end,
        config=bond_preview_config_for(canvas, style=style, order=order),
        a_id=a_id,
        b_id=b_id,
        resolvers=bond_preview_update_resolvers_for(canvas),
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
    "bond_preview_config_for",
    "bond_preview_update_resolvers_for",
    "build_bond_preview_items_for",
    "clear_bond_preview_items_for",
    "update_bond_preview_items_for",
]
