from __future__ import annotations

import math

from core.history import (
    CompositeCommand,
    SetAtomPositionsCommand,
    SetRingPolygonsCommand,
    UpdateBondLengthCommand,
)
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QFontMetricsF
from PyQt6.QtWidgets import QGraphicsPolygonItem, QGraphicsTextItem

from ui.atom_coords_access import current_atom_coords_3d_for
from ui.canvas_atom_graphics_state import atom_items_for
from ui.canvas_geometry_logic import (
    line_rect_clip_t as line_rect_clip_t_helper,
)
from ui.canvas_geometry_logic import (
    line_rect_intersections as line_rect_intersections_helper,
)
from ui.canvas_geometry_logic import (
    ray_rect_exit_distance as ray_rect_exit_distance_helper,
)
from ui.canvas_geometry_logic import (
    segment_intersection_t as segment_intersection_t_helper,
)
from ui.canvas_model_access import (
    atom_for_id,
    atoms_for,
    bond_for_id,
    has_atoms_for,
    rebuild_graphics_for,
    rescale_model_for,
)
from ui.canvas_scene_items_state import ring_items_for
from ui.renderer_style_access import (
    atom_font_for,
    bond_length_px_for,
    bond_line_width_for,
    set_bond_length_for,
)


class CanvasGeometryController:
    def __init__(self, canvas, *, hit_testing_service=None, history_service=None) -> None:
        self.canvas = canvas
        self.hit_testing_service = hit_testing_service
        self.history = history_service

    @staticmethod
    def _ring_atom_ids(ring_item) -> list[int] | None:
        ring_atom_ids = ring_item.data(2)
        return ring_atom_ids if isinstance(ring_atom_ids, list) else None

    def _ring_items_for_bond(self, bond):
        for ring_item in ring_items_for(self.canvas):
            ring_atom_ids = self._ring_atom_ids(ring_item)
            if ring_atom_ids is None:
                continue
            if bond.a in ring_atom_ids and bond.b in ring_atom_ids:
                yield ring_item, ring_atom_ids

    def _padded_label_rect(self, rect: QRectF) -> QRectF:
        pad = max(0.05, bond_line_width_for(self.canvas) * 0.05)
        return rect.adjusted(-pad, -pad, pad, pad)

    def ring_center_for_bond(self, bond) -> QPointF | None:
        for _, ring_atom_ids in self._ring_items_for_bond(bond):
            xs = []
            ys = []
            for atom_id in ring_atom_ids:
                atom = atom_for_id(self.canvas, atom_id)
                if atom is None:
                    continue
                xs.append(atom.x)
                ys.append(atom.y)
            if xs and ys:
                return QPointF(sum(xs) / len(xs), sum(ys) / len(ys))
        return None

    def ring_center_3d_for_bond(self, bond) -> tuple[float, float, float] | None:
        for _, ring_atom_ids in self._ring_items_for_bond(bond):
            coords = []
            for atom_id in ring_atom_ids:
                coord = current_atom_coords_3d_for(self.canvas, atom_id)
                if coord is not None:
                    coords.append(coord)
            if len(coords) < 3:
                return None
            sum_x = sum(c[0] for c in coords)
            sum_y = sum(c[1] for c in coords)
            sum_z = sum(c[2] for c in coords)
            count = len(coords)
            return (sum_x / count, sum_y / count, sum_z / count)
        return None

    def ring_for_bond(self, bond_id: int) -> QGraphicsPolygonItem | None:
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None:
            return None
        for ring_item, _ in self._ring_items_for_bond(bond):
            return ring_item
        return None

    def label_rect_for_atom(self, atom_id: int) -> QRectF | None:
        item = atom_items_for(self.canvas).get(atom_id)
        if item is None:
            return None
        return self._padded_label_rect(item.sceneBoundingRect())

    @staticmethod
    def visible_text_rect(item: QGraphicsTextItem) -> QRectF:
        return item.mapRectToScene(QGraphicsTextItem.boundingRect(item))

    def visible_label_rect_for_atom(self, atom_id: int) -> QRectF | None:
        item = atom_items_for(self.canvas).get(atom_id)
        if item is None:
            return None
        return self._padded_label_rect(self.visible_text_rect(item))

    def label_cut_radius_for_atom(self, atom_id: int) -> float | None:
        item = atom_items_for(self.canvas).get(atom_id)
        if item is None:
            return None
        rect = item.sceneBoundingRect()
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return None
        corners = [
            rect.topLeft(),
            rect.topRight(),
            rect.bottomLeft(),
            rect.bottomRight(),
        ]
        max_dist = 0.0
        for corner in corners:
            max_dist = max(max_dist, math.hypot(corner.x() - atom.x, corner.y() - atom.y))
        pad = max(0.02, bond_line_width_for(self.canvas) * 0.03)
        return (max_dist + pad) * 0.6

    def line_rect_clip_t(self, p1: QPointF, p2: QPointF, rect: QRectF) -> tuple[float, float] | None:
        return line_rect_clip_t_helper(p1, p2, rect)

    def segment_intersection_t(self, p1: QPointF, p2: QPointF, q1: QPointF, q2: QPointF) -> float | None:
        return segment_intersection_t_helper(p1, p2, q1, q2)

    def ray_rect_exit_distance(self, origin: QPointF, direction: QPointF, rect: QRectF) -> float | None:
        return ray_rect_exit_distance_helper(origin, direction, rect)

    def mark_clearance_for_kind(self, kind: str) -> float:
        gap = max(0.6, bond_length_px_for(self.canvas) * 0.05)
        if kind == "radical":
            radius = max(1.2, bond_line_width_for(self.canvas) * 0.7)
            return radius + gap
        if kind in {"plus", "minus"}:
            metrics = QFontMetricsF(atom_font_for(self.canvas))
            rect = metrics.boundingRect("+" if kind == "plus" else "-")
            half_diagonal = math.hypot(rect.width(), rect.height()) * 0.5
            return max(half_diagonal, metrics.height() * 0.35) + gap
        return gap

    def mark_target_distance_for_atom(
        self,
        atom_id: int,
        direction_x: float,
        direction_y: float,
        kind: str,
    ) -> float:
        atom = atom_for_id(self.canvas, atom_id)
        label_rect = self.visible_label_rect_for_atom(atom_id)
        if atom is None or label_rect is None:
            return 0.0
        clearance = self.mark_clearance_for_kind(kind)
        expanded_rect = label_rect.adjusted(-clearance, -clearance, clearance, clearance)
        distance = ray_rect_exit_distance_helper(
            QPointF(atom.x, atom.y),
            QPointF(direction_x, direction_y),
            expanded_rect,
        )
        return 0.0 if distance is None else distance

    def set_bond_length(self, length_px: float) -> None:
        old_length = bond_length_px_for(self.canvas)
        before_positions = {atom_id: (atom.x, atom.y) for atom_id, atom in atoms_for(self.canvas).items()}
        before_ring_polygons = [
            [(point.x(), point.y()) for point in ring_item.polygon()]
            for ring_item in ring_items_for(self.canvas)
        ]
        set_bond_length_for(self.canvas, length_px)
        if old_length <= 0 or not has_atoms_for(self.canvas):
            return
        scale = length_px / old_length
        if scale == 1.0:
            return
        if self.hit_testing_service is None:
            raise RuntimeError("CanvasGeometryController.set_bond_length requires hit_testing_service")
        rescale_model_for(self.canvas, scale)
        self.hit_testing_service.mark_spatial_index_dirty()
        rebuild_graphics_for(self.canvas)
        after_positions = {atom_id: (atom.x, atom.y) for atom_id, atom in atoms_for(self.canvas).items()}
        after_ring_polygons = [
            [(point.x(), point.y()) for point in ring_item.polygon()]
            for ring_item in ring_items_for(self.canvas)
        ]
        commands = [
            UpdateBondLengthCommand(before_length=old_length, after_length=length_px),
            SetAtomPositionsCommand(before_positions=before_positions, after_positions=after_positions),
        ]
        ring_items = ring_items_for(self.canvas)
        if ring_items:
            commands.append(
                SetRingPolygonsCommand(
                    ring_items=list(ring_items),
                    before_polygons=before_ring_polygons,
                    after_polygons=after_ring_polygons,
                )
            )
        if self.history is None:
            raise AttributeError("CanvasGeometryController requires an injected history_service")
        self.history.push(CompositeCommand(commands))

    def line_rect_intersections(self, p1: QPointF, p2: QPointF, rect: QRectF) -> list[float]:
        return line_rect_intersections_helper(p1, p2, rect)

    def trim_line_for_labels(
        self,
        a_id: int | None,
        b_id: int | None,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> tuple[float, float]:
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length == 0:
            return 0.0, 1.0
        t0 = 0.0
        t1 = 1.0
        hit_start = False
        hit_end = False
        for atom_id, is_start in ((a_id, True), (b_id, False)):
            if atom_id is None:
                continue
            radius = self.label_cut_radius_for_atom(atom_id)
            if radius is None:
                continue
            t_hit = min(1.0, radius / length)
            if is_start:
                t0 = max(t0, t_hit)
                hit_start = True
            else:
                t1 = min(t1, 1.0 - t_hit)
                hit_end = True
        if hit_start or hit_end:
            gap_t = (bond_line_width_for(self.canvas) * 0.02) / length
            if hit_start:
                t0 = min(1.0, t0 + gap_t)
            if hit_end:
                t1 = max(0.0, t1 - gap_t)
        min_span = 0.02
        if t1 - t0 < min_span:
            if hit_start and not hit_end:
                t0 = max(0.0, t1 - min_span)
            elif hit_end and not hit_start:
                t1 = min(1.0, t0 + min_span)
            else:
                mid = (t0 + t1) / 2.0
                t0 = max(0.0, mid - min_span / 2.0)
                t1 = min(1.0, mid + min_span / 2.0)
        return t0, t1

__all__ = ["CanvasGeometryController"]
