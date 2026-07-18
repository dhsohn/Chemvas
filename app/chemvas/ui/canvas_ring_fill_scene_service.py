from __future__ import annotations

import math
from typing import Any

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPen, QPolygonF

from chemvas.ui.canvas_model_access import atom_for_id
from chemvas.ui.canvas_scene_items_state import ring_items_for
from chemvas.ui.graphics_items import RING_FILL_Z_VALUE, NoSelectPolygonItem
from chemvas.ui.renderer_style_access import bond_length_px_for, ring_fill_brush_for
from chemvas.ui.scene_selectability import make_item_selectable


class CanvasRingFillSceneService:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def update_ring_fills_for_atoms(
        self,
        atom_ids: set[int],
        *,
        ring_items: tuple[Any, ...] | None = None,
    ) -> None:
        if not atom_ids:
            return
        candidates = ring_items_for(self.canvas) if ring_items is None else ring_items
        for ring_item in candidates:
            ring_atom_ids = ring_item.data(2)
            if not isinstance(ring_atom_ids, list):
                continue
            if not any(atom_id in atom_ids for atom_id in ring_atom_ids):
                continue
            points = []
            for atom_id in ring_atom_ids:
                atom = atom_for_id(self.canvas, atom_id)
                if atom is None:
                    continue
                points.append(QPointF(atom.x, atom.y))
            if len(points) >= 3:
                ring_item.setPolygon(QPolygonF(points))

    def rotate_ring_fills_3d(
        self,
        atom_ids: set[int],
        center: tuple[float, float, float],
        angle_x: float,
        angle_y: float,
        f: float,
    ) -> None:
        del f
        cx, cy, cz = center
        cos_y = math.cos(angle_y)
        sin_y = math.sin(angle_y)
        cos_x = math.cos(angle_x)
        sin_x = math.sin(angle_x)
        tol = bond_length_px_for(self.canvas) * 0.25
        atom_points = self._ring_fill_atom_points(atom_ids)
        if not atom_points:
            return
        for ring_item in ring_items_for(self.canvas):
            ring_atom_ids = ring_item.data(2)
            if isinstance(ring_atom_ids, list):
                if not any(atom_id in atom_ids for atom_id in ring_atom_ids):
                    continue
                points = self._ring_polygon_points_for_atom_ids(ring_atom_ids)
                if len(points) >= 3:
                    ring_item.setPolygon(QPolygonF(points))
                continue
            polygon = ring_item.polygon()
            if not self._polygon_matches_atom_points(polygon, atom_points, tol):
                continue
            rotated = QPolygonF()
            for point in polygon:
                x = point.x() - cx
                y = point.y() - cy
                z = -cz
                rx = x * cos_y + z * sin_y
                rz = -x * sin_y + z * cos_y
                ry = y * cos_x - rz * sin_x
                rotated.append(QPointF(rx + cx, ry + cy))
            ring_item.setPolygon(rotated)

    def rotate_ring_fills(
        self, atom_ids: set[int], center: QPointF, angle_rad: float
    ) -> None:
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        tol = bond_length_px_for(self.canvas) * 0.25
        atom_points = self._ring_fill_atom_points(atom_ids)
        if not atom_points:
            return
        for ring_item in ring_items_for(self.canvas):
            ring_atom_ids = ring_item.data(2)
            if isinstance(ring_atom_ids, list):
                if not any(atom_id in atom_ids for atom_id in ring_atom_ids):
                    continue
                points = self._ring_polygon_points_for_atom_ids(ring_atom_ids)
                if len(points) >= 3:
                    ring_item.setPolygon(QPolygonF(points))
                continue
            polygon = ring_item.polygon()
            if not self._polygon_matches_atom_points(polygon, atom_points, tol):
                continue
            rotated = QPolygonF()
            for point in polygon:
                dx = point.x() - center.x()
                dy = point.y() - center.y()
                rx = center.x() + dx * cos_a - dy * sin_a
                ry = center.y() + dx * sin_a + dy * cos_a
                rotated.append(QPointF(rx, ry))
            ring_item.setPolygon(rotated)

    def create_ring_fill_item(self, points: list[QPointF], atom_ids: list[int]):
        polygon = QPolygonF(points)
        ring_item = NoSelectPolygonItem(polygon)
        ring_item.setBrush(ring_fill_brush_for(self.canvas))
        ring_item.setPen(QPen(Qt.PenStyle.NoPen))
        ring_item.setData(0, "ring")
        ring_item.setData(2, list(atom_ids))
        ring_item.setZValue(RING_FILL_Z_VALUE)
        make_item_selectable(ring_item)
        return ring_item

    def _ring_fill_atom_points(self, atom_ids: set[int]) -> list[QPointF]:
        atom_points: list[QPointF] = []
        for atom_id in atom_ids:
            atom = atom_for_id(self.canvas, atom_id)
            if atom is None:
                continue
            atom_points.append(QPointF(atom.x, atom.y))
        return atom_points

    def _ring_polygon_points_for_atom_ids(
        self, ring_atom_ids: list[int]
    ) -> list[QPointF]:
        points: list[QPointF] = []
        for atom_id in ring_atom_ids:
            atom = atom_for_id(self.canvas, atom_id)
            if atom is None:
                continue
            points.append(QPointF(atom.x, atom.y))
        return points

    @staticmethod
    def _polygon_matches_atom_points(
        polygon, atom_points: list[QPointF], tol: float
    ) -> bool:
        for point in polygon:
            for atom_point in atom_points:
                if (
                    math.hypot(point.x() - atom_point.x(), point.y() - atom_point.y())
                    <= tol
                ):
                    return True
        return False


__all__ = ["CanvasRingFillSceneService"]
