from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPen, QPolygonF

from ui.graphics_items import NoSelectPolygonItem


class CanvasRingFillSceneService:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def update_ring_fills_for_atoms(self, atom_ids: set[int]) -> None:
        if not atom_ids:
            return
        for ring_item in self.canvas.ring_items:
            ring_atom_ids = ring_item.data(2)
            if not isinstance(ring_atom_ids, list):
                continue
            if not any(atom_id in atom_ids for atom_id in ring_atom_ids):
                continue
            points = []
            for atom_id in ring_atom_ids:
                atom = self.canvas.model.atoms.get(atom_id)
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
        tol = self.canvas.renderer.style.bond_length_px * 0.25
        atom_points = self._ring_fill_atom_points(atom_ids)
        if not atom_points:
            return
        for ring_item in self.canvas.ring_items:
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
                rz2 = y * sin_x + rz * cos_x
                rotated.append(QPointF(rx + cx, ry + cy))
            ring_item.setPolygon(rotated)

    def rotate_ring_fills(self, atom_ids: set[int], center: QPointF, angle_rad: float) -> None:
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        tol = self.canvas.renderer.style.bond_length_px * 0.25
        atom_points = self._ring_fill_atom_points(atom_ids)
        if not atom_points:
            return
        for ring_item in self.canvas.ring_items:
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
        ring_item.setBrush(self.canvas.renderer.ring_fill_brush())
        ring_item.setPen(QPen(Qt.PenStyle.NoPen))
        ring_item.setData(0, "ring")
        ring_item.setData(2, list(atom_ids))
        self.canvas._make_selectable(ring_item)
        return ring_item

    def _ring_fill_atom_points(self, atom_ids: set[int]) -> list[QPointF]:
        atom_points: list[QPointF] = []
        for atom_id in atom_ids:
            atom = self.canvas.model.atoms.get(atom_id)
            if atom is None:
                continue
            atom_points.append(QPointF(atom.x, atom.y))
        return atom_points

    def _ring_polygon_points_for_atom_ids(self, ring_atom_ids: list[int]) -> list[QPointF]:
        points: list[QPointF] = []
        for atom_id in ring_atom_ids:
            atom = self.canvas.model.atoms.get(atom_id)
            if atom is None:
                continue
            points.append(QPointF(atom.x, atom.y))
        return points

    @staticmethod
    def _polygon_matches_atom_points(polygon, atom_points: list[QPointF], tol: float) -> bool:
        for point in polygon:
            for atom_point in atom_points:
                if math.hypot(point.x() - atom_point.x(), point.y() - atom_point.y()) <= tol:
                    return True
        return False


def canvas_ring_fill_scene_service_for(canvas) -> CanvasRingFillSceneService:
    service = getattr(canvas, "_canvas_ring_fill_scene_service", None)
    required = (
        "update_ring_fills_for_atoms",
        "rotate_ring_fills_3d",
        "rotate_ring_fills",
        "create_ring_fill_item",
    )
    if isinstance(service, CanvasRingFillSceneService) and service.canvas is canvas:
        return service
    if service is not None and all(hasattr(service, name) for name in required):
        return service
    return CanvasRingFillSceneService(canvas)


__all__ = ["CanvasRingFillSceneService", "canvas_ring_fill_scene_service_for"]
