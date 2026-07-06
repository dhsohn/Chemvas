from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainterPath
from PyQt6.QtWidgets import QGraphicsLineItem

from ui.bond_graphics_access import ring_center_for_bond_for
from ui.bond_label_geometry_access import trim_line_for_labels_for
from ui.canvas_bond_graphics_state import bond_items_for_id
from ui.canvas_model_access import atom_for_id, atoms_for, bond_for_id, bonds_for
from ui.mark_item_access import mark_center_for, mark_selection_radius_for
from ui.pick_radius_access import atom_pick_radius_for
from ui.renderer_style_access import bond_length_px_for
from ui.scene_group_operations import selected_group_rects_for
from ui.scene_item_access import add_item_to_canvas_scene, remove_item_from_canvas_scene
from ui.selection_center_logic import bounding_box_center_for_atoms
from ui.selection_collection_access import selected_ids_for
from ui.selection_outline_items import (
    selection_center_outline_items,
    selection_component_outline_item,
    selection_group_outline_item,
    selection_object_outline_item,
)
from ui.selection_outline_paths import (
    ARROW_OBJECT_KINDS,
)
from ui.selection_outline_paths import (
    selection_line_stroke_path as build_selection_line_stroke_path,
)
from ui.selection_outline_paths import (
    selection_path_for_bond_item as build_selection_path_for_bond_item,
)
from ui.selection_outline_paths import (
    selection_path_for_object_item as build_selection_path_for_object_item,
)
from ui.selection_outline_state import (
    append_selection_outline_for,
    clear_selection_outlines_for,
    selection_outlines_for,
)
from ui.selection_scene_access import scene_selected_items_for
from ui.selection_style_access import (
    emit_selection_info_for,
    selection_bond_overlay_width_for,
    selection_color_for,
    selection_indicator_rect_for_atom_for,
    suspend_selection_outline_for,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


OBJECT_OVERLAY_KINDS = {
    *ARROW_OBJECT_KINDS,
    "ts_bracket",
    "shape",
    "mark",
    "orbital",
}


class SelectionOutlineService:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        graph_service,
        active_tool_name_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self.canvas = canvas
        self.graph_service = graph_service
        self._active_tool_name = active_tool_name_provider or (lambda: None)

    def update_selection_outline(self) -> None:
        if suspend_selection_outline_for(self.canvas):
            return
        items = scene_selected_items_for(self.canvas)
        if not items:
            self.clear_selection_outlines()
            emit_selection_info_for(self.canvas)
            return
        items = [
            item
            for item in items
            if item.data(0) not in {"handle", "note_box", "note_select", "selection_outline"}
        ]
        if not items:
            return
        explicit_atom_ids, bond_ids = selected_ids_for(self.canvas)
        atom_ids = set(explicit_atom_ids)
        for bond_id in bond_ids:
            bond = bond_for_id(self.canvas, bond_id)
            if bond is not None:
                atom_ids.add(bond.a)
                atom_ids.add(bond.b)
        object_items = [item for item in items if item.data(0) in OBJECT_OVERLAY_KINDS]

        self.clear_selection_outlines()

        atom_pad = bond_length_px_for(self.canvas) * 0.06
        atom_fill = QColor(selection_color_for(self.canvas))
        atom_fill.setAlpha(45)
        object_fill = QColor(selection_color_for(self.canvas))
        object_fill.setAlpha(45)
        overlay_bond_ids = {
            bond_id
            for bond_id, bond in enumerate(bonds_for(self.canvas))
            if bond is not None and bond.a in atom_ids and bond.b in atom_ids
        }
        for component in self.graph_service.connected_components(atom_ids):
            component_bond_ids = {
                bond_id
                for bond_id in overlay_bond_ids
                if (bond := bond_for_id(self.canvas, bond_id)) is not None
                and bond.a in component
                and bond.b in component
            }
            self.add_selection_component_overlay(component, component_bond_ids, atom_fill, atom_pad)

        center = self.selection_center_for_atoms(atom_ids)
        if center is not None and self.selection_center_marker_enabled():
            self.add_selection_center_marker(center)

        for item in object_items:
            self.add_selection_object_overlay(item, object_fill)
        for group_rect in selected_group_rects_for(self.canvas):
            self.add_selection_group_overlay(group_rect)
        emit_selection_info_for(self.canvas)

    def clear_selection_outlines(self) -> None:
        for outline in selection_outlines_for(self.canvas):
            remove_item_from_canvas_scene(self.canvas, outline)
        clear_selection_outlines_for(self.canvas)

    def shift_selection_outlines(self, dx: float, dy: float) -> None:
        if not selection_outlines_for(self.canvas):
            return
        for outline in selection_outlines_for(self.canvas):
            outline.moveBy(dx, dy)

    def selection_line_stroke_path(
        self,
        start: QPointF,
        end: QPointF,
        width: float,
    ) -> QPainterPath:
        return build_selection_line_stroke_path(start, end, width)

    def _selection_bond_overlay_width(self, pen) -> float:
        return selection_bond_overlay_width_for(self.canvas, pen)

    def selection_path_for_bond_item(self, item, width: float | None = None) -> QPainterPath:
        return build_selection_path_for_bond_item(
            item,
            width=width,
            default_width_for_pen=self._selection_bond_overlay_width,
            line_stroke_path=self.selection_line_stroke_path,
        )

    def selection_path_for_bond(self, bond_id: int) -> QPainterPath:
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None:
            return QPainterPath()
        items = bond_items_for_id(self.canvas, bond_id)
        if not items:
            return QPainterPath()
        ring_center = ring_center_for_bond_for(self.canvas, bond) if bond.order == 2 else None
        if ring_center is not None:
            outer_path = self.selection_path_for_bond_item(items[0])
            if not outer_path.isEmpty():
                return outer_path
        line_items = [item for item in items if isinstance(item, QGraphicsLineItem)]
        if bond.order >= 2 and line_items and len(line_items) == len(items):
            atom_a = atom_for_id(self.canvas, bond.a)
            atom_b = atom_for_id(self.canvas, bond.b)
            if atom_a is not None and atom_b is not None:
                t0, t1 = trim_line_for_labels_for(self.canvas, bond.a, bond.b, atom_a.x, atom_a.y, atom_b.x, atom_b.y)
                base_x1 = atom_a.x + (atom_b.x - atom_a.x) * t0
                base_y1 = atom_a.y + (atom_b.y - atom_a.y) * t0
                base_x2 = atom_a.x + (atom_b.x - atom_a.x) * t1
                base_y2 = atom_a.y + (atom_b.y - atom_a.y) * t1
                dx = base_x2 - base_x1
                dy = base_y2 - base_y1
                length = math.hypot(dx, dy)
                if length > 1e-6:
                    nx = -dy / length
                    ny = dx / length
                    base_mid = QPointF((base_x1 + base_x2) * 0.5, (base_y1 + base_y2) * 0.5)
                    offsets = []
                    widths = []
                    for item in line_items:
                        line = item.line()
                        mid = item.mapToScene(
                            QPointF((line.x1() + line.x2()) * 0.5, (line.y1() + line.y2()) * 0.5)
                        )
                        offsets.append((mid.x() - base_mid.x()) * nx + (mid.y() - base_mid.y()) * ny)
                        widths.append(selection_bond_overlay_width_for(self.canvas, item.pen()))
                    axis_shift = (min(offsets) + max(offsets)) * 0.5
                    overlay_width = max(widths)
                    return self.selection_line_stroke_path(
                        QPointF(base_x1 + nx * axis_shift, base_y1 + ny * axis_shift),
                        QPointF(base_x2 + nx * axis_shift, base_y2 + ny * axis_shift),
                        overlay_width,
                    )
        bond_path = QPainterPath()
        bond_path.setFillRule(Qt.FillRule.WindingFill)
        for item in items:
            item_path = self.selection_path_for_bond_item(item)
            if not item_path.isEmpty():
                bond_path.addPath(item_path)
        return bond_path

    def selection_path_for_object_item(self, item) -> QPainterPath:
        kind = item.data(0)
        pad = bond_length_px_for(self.canvas) * 0.12
        mark_center = mark_center_for(self.canvas, item) if kind == "mark" else None
        mark_radius = mark_selection_radius_for(self.canvas) if kind == "mark" else None
        return build_selection_path_for_object_item(
            item,
            kind=kind,
            pad=pad,
            mark_center=mark_center,
            mark_radius=mark_radius,
            atom_pick_radius=atom_pick_radius_for(self.canvas),
            default_width_for_pen=self._selection_bond_overlay_width,
            line_stroke_path=self.selection_line_stroke_path,
        )

    def add_selection_object_overlay(self, item, color: QColor) -> None:
        path = self.selection_path_for_object_item(item)
        if path.isEmpty():
            return
        outline = selection_object_outline_item(path, color)
        add_item_to_canvas_scene(self.canvas, outline)
        append_selection_outline_for(self.canvas, outline)

    def add_selection_group_overlay(self, rect) -> None:
        outline = selection_group_outline_item(rect, QColor(selection_color_for(self.canvas)))
        add_item_to_canvas_scene(self.canvas, outline)
        append_selection_outline_for(self.canvas, outline)

    def add_selection_component_overlay(
        self,
        atom_ids: set[int],
        bond_ids: set[int],
        color: QColor,
        atom_pad: float,
    ) -> None:
        component_path = QPainterPath()
        component_path.setFillRule(Qt.FillRule.WindingFill)
        for atom_id in atom_ids:
            rect = selection_indicator_rect_for_atom_for(self.canvas, atom_id)
            if rect is None:
                continue
            padded = rect.adjusted(-atom_pad, -atom_pad, atom_pad, atom_pad)
            corner = min(padded.width(), padded.height()) / 2.0
            component_path.addRoundedRect(padded, corner, corner)
        for bond_id in bond_ids:
            bond_path = self.selection_path_for_bond(bond_id)
            if not bond_path.isEmpty():
                component_path.addPath(bond_path)
        if component_path.isEmpty():
            return
        component_path = component_path.simplified()
        component_path.setFillRule(Qt.FillRule.WindingFill)
        outline = selection_component_outline_item(component_path, color=color, atom_ids=atom_ids)
        add_item_to_canvas_scene(self.canvas, outline)
        append_selection_outline_for(self.canvas, outline)

    def selection_center_for_atoms(self, atom_ids: set[int]) -> QPointF | None:
        if len(atom_ids) < 2:
            return None
        return bounding_box_center_for_atoms(atom_ids, atoms=atoms_for(self.canvas))

    def selection_center_marker_enabled(self) -> bool:
        return self._active_tool_name() == "perspective"

    def add_selection_center_marker(self, center: QPointF) -> None:
        outer_radius = max(3.5, bond_length_px_for(self.canvas) * 0.14)
        inner_radius = max(1.2, bond_length_px_for(self.canvas) * 0.05)
        for marker in selection_center_outline_items(center, outer_radius=outer_radius, inner_radius=inner_radius):
            add_item_to_canvas_scene(self.canvas, marker)
            append_selection_outline_for(self.canvas, marker)


__all__ = ["OBJECT_OVERLAY_KINDS", "SelectionOutlineService"]
