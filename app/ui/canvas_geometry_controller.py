from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QFontMetricsF
from PyQt6.QtWidgets import QGraphicsPolygonItem, QGraphicsTextItem

from ui.canvas_geometry_logic import (
    line_rect_clip_t as line_rect_clip_t_helper,
    line_rect_intersections as line_rect_intersections_helper,
    ray_rect_exit_distance as ray_rect_exit_distance_helper,
    segment_intersection_t as segment_intersection_t_helper,
)


class CanvasGeometryController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def ring_center_for_bond(self, bond) -> QPointF | None:
        for ring_item in self.canvas.ring_items:
            ring_atom_ids = ring_item.data(2)
            if not isinstance(ring_atom_ids, list):
                continue
            if bond.a in ring_atom_ids and bond.b in ring_atom_ids:
                xs = []
                ys = []
                for atom_id in ring_atom_ids:
                    atom = self.canvas.model.atoms.get(atom_id)
                    if atom is None:
                        continue
                    xs.append(atom.x)
                    ys.append(atom.y)
                if xs and ys:
                    return QPointF(sum(xs) / len(xs), sum(ys) / len(ys))
        return None

    def ring_center_3d_for_bond(self, bond) -> tuple[float, float, float] | None:
        for ring_item in self.canvas.ring_items:
            ring_atom_ids = ring_item.data(2)
            if not isinstance(ring_atom_ids, list):
                continue
            if bond.a in ring_atom_ids and bond.b in ring_atom_ids:
                coords = []
                for atom_id in ring_atom_ids:
                    coord = self.canvas._current_atom_coords_3d(atom_id)
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
        if not (0 <= bond_id < len(self.canvas.model.bonds)):
            return None
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return None
        for ring_item in self.canvas.ring_items:
            ring_atom_ids = ring_item.data(2)
            if not isinstance(ring_atom_ids, list):
                continue
            if bond.a in ring_atom_ids and bond.b in ring_atom_ids:
                return ring_item
        return None

    def label_rect_for_atom(self, atom_id: int) -> QRectF | None:
        item = self.canvas.atom_items.get(atom_id)
        if item is None:
            return None
        rect = item.sceneBoundingRect()
        pad = max(0.05, self.canvas.renderer.style.bond_line_width * 0.05)
        return rect.adjusted(-pad, -pad, pad, pad)

    @staticmethod
    def visible_text_rect(item: QGraphicsTextItem) -> QRectF:
        return item.mapRectToScene(QGraphicsTextItem.boundingRect(item))

    def visible_label_rect_for_atom(self, atom_id: int) -> QRectF | None:
        item = self.canvas.atom_items.get(atom_id)
        if item is None:
            return None
        rect = self.visible_text_rect(item)
        pad = max(0.05, self.canvas.renderer.style.bond_line_width * 0.05)
        return rect.adjusted(-pad, -pad, pad, pad)

    def label_cut_radius_for_atom(self, atom_id: int) -> float | None:
        item = self.canvas.atom_items.get(atom_id)
        if item is None:
            return None
        rect = item.sceneBoundingRect()
        atom = self.canvas.model.atoms.get(atom_id)
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
        pad = max(0.02, self.canvas.renderer.style.bond_line_width * 0.03)
        return (max_dist + pad) * 0.6

    def line_rect_clip_t(self, p1: QPointF, p2: QPointF, rect: QRectF) -> tuple[float, float] | None:
        return line_rect_clip_t_helper(p1, p2, rect)

    def segment_intersection_t(self, p1: QPointF, p2: QPointF, q1: QPointF, q2: QPointF) -> float | None:
        return segment_intersection_t_helper(p1, p2, q1, q2)

    def ray_rect_exit_distance(self, origin: QPointF, direction: QPointF, rect: QRectF) -> float | None:
        return ray_rect_exit_distance_helper(origin, direction, rect)

    def mark_clearance_for_kind(self, kind: str) -> float:
        gap = max(0.6, self.canvas.renderer.style.bond_length_px * 0.05)
        if kind == "radical":
            radius = max(1.2, self.canvas.renderer.style.bond_line_width * 0.7)
            return radius + gap
        if kind in {"plus", "minus"}:
            metrics = QFontMetricsF(self.canvas.renderer.atom_font())
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
        atom = self.canvas.model.atoms.get(atom_id)
        label_rect = self.canvas._visible_label_rect_for_atom(atom_id)
        if atom is None or label_rect is None:
            return 0.0
        clearance = self.canvas._mark_clearance_for_kind(kind)
        expanded_rect = label_rect.adjusted(-clearance, -clearance, clearance, clearance)
        distance = ray_rect_exit_distance_helper(
            QPointF(atom.x, atom.y),
            QPointF(direction_x, direction_y),
            expanded_rect,
        )
        return 0.0 if distance is None else distance

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
            radius = self.canvas._label_cut_radius_for_atom(atom_id)
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
            gap_t = (self.canvas.renderer.style.bond_line_width * 0.02) / length
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
