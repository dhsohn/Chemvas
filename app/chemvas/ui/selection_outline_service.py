from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainterPath
from PyQt6.QtWidgets import QGraphicsLineItem

from chemvas.features.selection import (
    ARROW_OBJECT_KINDS,
    bounding_box_center_for_atoms,
    selection_frame_applies,
    simplified_outline_path,
)
from chemvas.features.selection import (
    selection_line_stroke_path as build_selection_line_stroke_path,
)
from chemvas.features.selection import (
    selection_path_for_bond_item as build_selection_path_for_bond_item,
)
from chemvas.features.selection import (
    selection_path_for_object_item as build_selection_path_for_object_item,
)
from chemvas.ui.bond_graphics_access import ring_center_for_bond_for
from chemvas.ui.bond_label_geometry_access import trim_line_for_labels_for
from chemvas.ui.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id
from chemvas.ui.canvas_model_access import atom_for_id, atoms_for, bond_for_id
from chemvas.ui.mark_item_access import mark_center_for, mark_selection_radius_for
from chemvas.ui.pick_radius_access import atom_pick_radius_for
from chemvas.ui.renderer_style_access import bond_length_px_for, bond_spacing_px_for
from chemvas.ui.scene_group_operations import selected_group_rects_for
from chemvas.ui.scene_item_access import (
    add_item_to_canvas_scene,
    remove_item_from_canvas_scene,
)
from chemvas.ui.selection_collection_access import selected_ids_for
from chemvas.ui.selection_info_access import emit_selection_info_for
from chemvas.ui.selection_outline_items import (
    selection_center_outline_items,
    selection_component_outline_item,
    selection_frame_outline_items,
    selection_group_outline_item,
    selection_object_outline_item,
)
from chemvas.ui.selection_outline_state import (
    append_selection_outline_for,
    clear_selection_outlines_for,
    selection_outlines_for,
)
from chemvas.ui.selection_scene_access import scene_selected_items_for
from chemvas.ui.selection_style_access import (
    selection_bond_overlay_width_for,
    selection_color_for,
    selection_indicator_rect_for_atom_for,
    suspend_selection_outline_for,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from chemvas.ui.canvas_view import CanvasView


OBJECT_OVERLAY_KINDS = {
    *ARROW_OBJECT_KINDS,
    "ts_bracket",
    "shape",
    "image",
    "mark",
    "orbital",
}
# What the rotation knob turns about the frame's centre: the same items the
# Edit rotate command turns, minus atom-bound marks (a mark alone would spin
# about its own centre, which changes nothing).
ROTATABLE_OBJECT_KINDS = {*ARROW_OBJECT_KINDS, "orbital"}


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
        # Notes carry their own selection state, so a notes-only group has no
        # scene-selected items yet still needs its dashed group box.
        group_rects = selected_group_rects_for(self.canvas)
        if not items and not group_rects:
            self.clear_selection_outlines()
            emit_selection_info_for(self.canvas)
            return
        items = [
            item
            for item in items
            if item.data(0)
            not in {"handle", "note_box", "note_select", "selection_outline"}
        ]
        if not items and not group_rects:
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

        color = QColor(selection_color_for(self.canvas))
        candidate_bond_ids = set(bond_ids)
        graph = getattr(self.graph_service, "graph", None)
        atom_bond_ids = getattr(graph, "atom_bond_ids", {})
        for atom_id in atom_ids:
            candidate_bond_ids.update(atom_bond_ids.get(atom_id, ()))
        overlay_bond_ids: set[int] = set()
        for bond_id in candidate_bond_ids:
            bond = bond_for_id(self.canvas, bond_id)
            if bond is not None and bond.a in atom_ids and bond.b in atom_ids:
                overlay_bond_ids.add(bond_id)
        for component in self.graph_service.connected_components(atom_ids):
            component_bond_ids = {
                bond_id
                for bond_id in overlay_bond_ids
                if (bond := bond_for_id(self.canvas, bond_id)) is not None
                and bond.a in component
                and bond.b in component
            }
            self.add_selection_component_overlay(component, component_bond_ids, color)

        center = self.selection_center_for_atoms(atom_ids)
        if center is not None and self.selection_center_marker_enabled():
            self.add_selection_center_marker(center)

        for item in object_items:
            self.add_selection_object_overlay(item, color)
        for group_rect in group_rects:
            self.add_selection_group_overlay(group_rect)
        rotatable_items = [
            item for item in object_items if item.data(0) in ROTATABLE_OBJECT_KINDS
        ]
        if selection_frame_applies(len(atom_ids), len(rotatable_items)):
            frame_rect = self.selection_frame_rect(atom_ids, rotatable_items)
            if frame_rect is not None:
                self.add_selection_frame_overlay(frame_rect)
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

    def selection_path_for_bond_item(
        self, item, width: float | None = None
    ) -> QPainterPath:
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
        ring_center = (
            ring_center_for_bond_for(self.canvas, bond) if bond.order == 2 else None
        )
        if ring_center is not None:
            outer_path = self.selection_path_for_bond_item(items[0])
            if not outer_path.isEmpty():
                return outer_path
        line_items = [item for item in items if isinstance(item, QGraphicsLineItem)]
        if bond.order >= 2 and line_items and len(line_items) == len(items):
            atom_a = atom_for_id(self.canvas, bond.a)
            atom_b = atom_for_id(self.canvas, bond.b)
            if atom_a is not None and atom_b is not None:
                t0, t1 = trim_line_for_labels_for(
                    self.canvas, bond.a, bond.b, atom_a.x, atom_a.y, atom_b.x, atom_b.y
                )
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
                    base_mid = QPointF(
                        (base_x1 + base_x2) * 0.5, (base_y1 + base_y2) * 0.5
                    )
                    offsets = []
                    widths = []
                    for item in line_items:
                        line = item.line()
                        mid = item.mapToScene(
                            QPointF(
                                (line.x1() + line.x2()) * 0.5,
                                (line.y1() + line.y2()) * 0.5,
                            )
                        )
                        offsets.append(
                            (mid.x() - base_mid.x()) * nx
                            + (mid.y() - base_mid.y()) * ny
                        )
                        widths.append(
                            selection_bond_overlay_width_for(self.canvas, item.pen())
                        )
                    # A ring double bond keeps one line on the atom axis and
                    # shortens the other inside the ring; its band stays on the
                    # axis so it meets the neighbouring bands at the vertex.
                    # Only a symmetric pair (C=O) is centred between its lines.
                    on_axis_tolerance = bond_spacing_px_for(self.canvas) * 0.25
                    if any(abs(offset) <= on_axis_tolerance for offset in offsets):
                        axis_shift = 0.0
                    else:
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
        if item.data(0) == "image":
            outline = selection_group_outline_item(
                item.sceneBoundingRect().adjusted(-2.0, -2.0, 2.0, 2.0), color
            )
            outline.setData(2, {"kind": "object", "object_kind": "image"})
            add_item_to_canvas_scene(self.canvas, outline)
            append_selection_outline_for(self.canvas, outline)
            return
        path = self.selection_path_for_object_item(item)
        if path.isEmpty():
            return
        outline = selection_object_outline_item(path, color)
        outline.setData(2, {"kind": "object", "object_kind": item.data(0)})
        add_item_to_canvas_scene(self.canvas, outline)
        append_selection_outline_for(self.canvas, outline)

    def add_selection_group_overlay(self, rect) -> None:
        outline = selection_group_outline_item(
            rect, QColor(selection_color_for(self.canvas))
        )
        add_item_to_canvas_scene(self.canvas, outline)
        append_selection_outline_for(self.canvas, outline)

    def add_selection_frame_overlay(self, rect) -> None:
        for item in selection_frame_outline_items(
            rect, QColor(selection_color_for(self.canvas))
        ):
            add_item_to_canvas_scene(self.canvas, item)
            append_selection_outline_for(self.canvas, item)

    def selection_frame_rect(self, atom_ids: set[int], items: list):
        """The box the rotation frame draws: every atom mark and turning item."""
        rect = None
        atom_labels = atom_items_for(self.canvas)
        for atom_id in sorted(atom_ids):
            atom_rect = selection_indicator_rect_for_atom_for(self.canvas, atom_id)
            if atom_rect is None:
                continue
            label = atom_labels.get(atom_id)
            if label is not None:
                # A label such as "HO" is wider than its pick circle; the
                # frame encloses the whole label rather than cutting it.
                atom_rect = atom_rect.united(label.sceneBoundingRect())
            rect = atom_rect if rect is None else rect.united(atom_rect)
        for item in items:
            # An arrow's labels are its children and turn with it, so the frame
            # (and the knob above it) clears them instead of sitting on them.
            item_rect = item.sceneBoundingRect().united(
                item.mapRectToScene(item.childrenBoundingRect())
            )
            rect = item_rect if rect is None else rect.united(item_rect)
        if rect is None:
            return None
        pad = bond_length_px_for(self.canvas) * 0.12
        return rect.adjusted(-pad, -pad, pad, pad)

    def add_selection_component_overlay(
        self,
        atom_ids: set[int],
        bond_ids: set[int],
        color: QColor,
    ) -> None:
        # The outline follows the bonds. Only an atom that draws a label gets
        # its own rounded box, and an atom with no selected bond gets a ring,
        # so a selected chain reads as one band instead of a row of bubbles.
        atom_labels = atom_items_for(self.canvas)
        bonded_atom_ids: set[int] = set()
        for bond_id in bond_ids:
            bond = bond_for_id(self.canvas, bond_id)
            if bond is not None:
                bonded_atom_ids.add(bond.a)
                bonded_atom_ids.add(bond.b)
        component_path = QPainterPath()
        component_path.setFillRule(Qt.FillRule.WindingFill)
        for atom_id in atom_ids:
            if atom_id in bonded_atom_ids and atom_labels.get(atom_id) is None:
                continue
            rect = selection_indicator_rect_for_atom_for(self.canvas, atom_id)
            if rect is None:
                continue
            corner = min(rect.width(), rect.height()) / 2.0
            component_path.addRoundedRect(rect, corner, corner)
        for bond_id in bond_ids:
            bond_path = self.selection_path_for_bond(bond_id)
            if not bond_path.isEmpty():
                component_path.addPath(bond_path)
        if component_path.isEmpty():
            return
        component_path = simplified_outline_path(component_path)
        outline = selection_component_outline_item(
            component_path, color=color, atom_ids=atom_ids
        )
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
        for marker in selection_center_outline_items(
            center, outer_radius=outer_radius, inner_radius=inner_radius
        ):
            add_item_to_canvas_scene(self.canvas, marker)
            append_selection_outline_for(self.canvas, marker)


__all__ = [
    "OBJECT_OVERLAY_KINDS",
    "ROTATABLE_OBJECT_KINDS",
    "SelectionOutlineService",
]
