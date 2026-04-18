from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QCursor, QTransform

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class CanvasHitTestingService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def scene_pos_from_event(self, event) -> QPointF:
        if hasattr(event, "position"):
            return self.canvas.mapToScene(event.position().toPoint())
        if hasattr(event, "pos"):
            return self.canvas.mapToScene(event.pos())
        pos = self.canvas.viewport().mapFromGlobal(QCursor.pos())
        return self.canvas.mapToScene(pos)

    def item_at_scene_pos(self, pos: QPointF):
        bond_item = None
        ring_item = None
        other_item = None
        for item in self.canvas.scene().items(
            pos,
            Qt.ItemSelectionMode.IntersectsItemShape,
            Qt.SortOrder.DescendingOrder,
            QTransform(),
        ):
            if item.data(0) == "selection_outline":
                continue
            kind = item.data(0)
            if kind in {"note_box", "note_select"}:
                continue
            if kind == "atom":
                return item
            if kind == "bond" and bond_item is None:
                bond_item = item
                continue
            if kind == "ring" and ring_item is None:
                ring_item = item
                continue
            if other_item is None:
                other_item = item
        if bond_item is None:
            find_bond_near = self._hit_method("_find_bond_near", self.find_bond_near)
            nearby_bond_id = find_bond_near(pos, self.canvas._bond_pick_radius())
            if nearby_bond_id is not None:
                nearby_items = self.canvas.bond_items.get(nearby_bond_id, [])
                if nearby_items:
                    return nearby_items[0]
        return bond_item or ring_item or other_item

    def item_at_event(self, event):
        scene_pos_from_event = self._hit_method("scene_pos_from_event", self.scene_pos_from_event)
        item_at_scene_pos = self._hit_method("item_at_scene_pos", self.item_at_scene_pos)
        return item_at_scene_pos(scene_pos_from_event(event))

    def grid_cell_size(self) -> float:
        return max(8.0, self.canvas.renderer.style.bond_length_px)

    @staticmethod
    def cell_coords(x: float, y: float, cell_size: float) -> tuple[int, int]:
        return int(math.floor(x / cell_size)), int(math.floor(y / cell_size))

    def ensure_spatial_index(self) -> None:
        grid_cell_size = self._hit_method("_grid_cell_size", self.grid_cell_size)
        rebuild_spatial_index = self._hit_method("_rebuild_spatial_index", self.rebuild_spatial_index)
        cell_size = grid_cell_size()
        if not self.canvas._spatial_index_dirty and abs(self.canvas._spatial_cell_size - cell_size) < 1e-6:
            return
        rebuild_spatial_index(cell_size)

    def rebuild_spatial_index(self, cell_size: float) -> None:
        cell_coords = self._hit_method("_cell_coords", self.cell_coords)
        atom_grid: dict[tuple[int, int], set[int]] = {}
        for atom_id, atom in self.canvas.model.atoms.items():
            key = cell_coords(atom.x, atom.y, cell_size)
            atom_grid.setdefault(key, set()).add(atom_id)

        bond_grid: dict[tuple[int, int], set[int]] = {}
        for bond_id, bond in enumerate(self.canvas.model.bonds):
            if bond is None:
                continue
            a = self.canvas.model.atoms.get(bond.a)
            b = self.canvas.model.atoms.get(bond.b)
            if a is None or b is None:
                continue
            min_x = min(a.x, b.x)
            max_x = max(a.x, b.x)
            min_y = min(a.y, b.y)
            max_y = max(a.y, b.y)
            min_ix, min_iy = cell_coords(min_x, min_y, cell_size)
            max_ix, max_iy = cell_coords(max_x, max_y, cell_size)
            for ix in range(min_ix, max_ix + 1):
                for iy in range(min_iy, max_iy + 1):
                    bond_grid.setdefault((ix, iy), set()).add(bond_id)

        self.canvas._atom_grid = atom_grid
        self.canvas._bond_grid = bond_grid
        self.canvas._spatial_cell_size = cell_size
        self.canvas._spatial_index_dirty = False

    def find_atom_near(self, x: float, y: float, max_dist: float) -> int | None:
        if not self.canvas.model.atoms:
            return None
        ensure_spatial_index = self._hit_method("_ensure_spatial_index", self.ensure_spatial_index)
        grid_cell_size = self._hit_method("_grid_cell_size", self.grid_cell_size)
        cell_coords = self._hit_method("_cell_coords", self.cell_coords)
        ensure_spatial_index()
        cell_size = self.canvas._spatial_cell_size or grid_cell_size()
        if cell_size <= 0:
            return None
        cell_radius = int(math.ceil(max_dist / cell_size))
        ix, iy = cell_coords(x, y, cell_size)
        nearest_id = None
        nearest_dist_sq = max_dist * max_dist
        for cx in range(ix - cell_radius, ix + cell_radius + 1):
            for cy in range(iy - cell_radius, iy + cell_radius + 1):
                for atom_id in self.canvas._atom_grid.get((cx, cy), ()):
                    atom = self.canvas.model.atoms.get(atom_id)
                    if atom is None:
                        continue
                    dx = atom.x - x
                    dy = atom.y - y
                    dist_sq = dx * dx + dy * dy
                    if dist_sq <= nearest_dist_sq:
                        nearest_id = atom_id
                        nearest_dist_sq = dist_sq
        return nearest_id

    def find_bond_near(self, pos: QPointF, max_dist: float) -> int | None:
        if not self.canvas.model.bonds:
            return None
        ensure_spatial_index = self._hit_method("_ensure_spatial_index", self.ensure_spatial_index)
        grid_cell_size = self._hit_method("_grid_cell_size", self.grid_cell_size)
        cell_coords = self._hit_method("_cell_coords", self.cell_coords)
        distance_point_to_segment = self._hit_method("_distance_point_to_segment", self.distance_point_to_segment)
        ensure_spatial_index()
        cell_size = self.canvas._spatial_cell_size or grid_cell_size()
        if cell_size <= 0:
            return None
        cell_radius = int(math.ceil(max_dist / cell_size))
        ix, iy = cell_coords(pos.x(), pos.y(), cell_size)
        nearest = None
        nearest_dist = max_dist
        seen: set[int] = set()
        for cx in range(ix - cell_radius, ix + cell_radius + 1):
            for cy in range(iy - cell_radius, iy + cell_radius + 1):
                for bond_id in self.canvas._bond_grid.get((cx, cy), ()):
                    if bond_id in seen:
                        continue
                    seen.add(bond_id)
                    if not (0 <= bond_id < len(self.canvas.model.bonds)):
                        continue
                    bond = self.canvas.model.bonds[bond_id]
                    if bond is None:
                        continue
                    a = self.canvas.model.atoms.get(bond.a)
                    b = self.canvas.model.atoms.get(bond.b)
                    if a is None or b is None:
                        continue
                    dist = distance_point_to_segment(
                        pos,
                        QPointF(a.x, a.y),
                        QPointF(b.x, b.y),
                    )
                    if dist <= nearest_dist:
                        nearest = bond_id
                        nearest_dist = dist
        return nearest

    @staticmethod
    def distance_point_to_segment(p: QPointF, a: QPointF, b: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        apx = p.x() - a.x()
        apy = p.y() - a.y()
        ab_len_sq = abx * abx + aby * aby
        if ab_len_sq == 0:
            return math.hypot(apx, apy)
        t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab_len_sq))
        cx = a.x() + abx * t
        cy = a.y() + aby * t
        return math.hypot(p.x() - cx, p.y() - cy)

    def nearest_atom_hit(self, pos: QPointF) -> tuple[int, float] | None:
        find_atom_near = self._hit_method("find_atom_near", self.find_atom_near)
        atom_id = find_atom_near(pos.x(), pos.y(), self.canvas._atom_pick_radius())
        if atom_id is None:
            return None
        atom = self.canvas.model.atoms.get(atom_id)
        if atom is None:
            return None
        return atom_id, math.hypot(atom.x - pos.x(), atom.y - pos.y())

    def nearest_bond_hit(self, pos: QPointF) -> tuple[int, float] | None:
        find_bond_near = self._hit_method("_find_bond_near", self.find_bond_near)
        distance_point_to_segment = self._hit_method("_distance_point_to_segment", self.distance_point_to_segment)
        bond_id = find_bond_near(pos, self.canvas._bond_pick_radius())
        if bond_id is None or not (0 <= bond_id < len(self.canvas.model.bonds)):
            return None
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return None
        atom_a = self.canvas.model.atoms.get(bond.a)
        atom_b = self.canvas.model.atoms.get(bond.b)
        if atom_a is None or atom_b is None:
            return None
        dist = distance_point_to_segment(
            pos,
            QPointF(atom_a.x, atom_a.y),
            QPointF(atom_b.x, atom_b.y),
        )
        return bond_id, dist

    def bond_id_from_event(self, event) -> int | None:
        if self.canvas.hover_bond_id is not None:
            return self.canvas.hover_bond_id
        scene_pos_from_event = self._hit_method("scene_pos_from_event", self.scene_pos_from_event)
        find_bond_near = self._hit_method("_find_bond_near", self.find_bond_near)
        pos = scene_pos_from_event(event)
        return find_bond_near(pos, max(self.canvas.renderer.style.bond_length_px * 0.35, self.canvas._bond_pick_radius()))

    def _hit_method(self, canvas_name: str, fallback):
        override = getattr(self.canvas, canvas_name, None)
        if callable(override) and getattr(self.canvas, "_hit_testing_service", None) is not self:
            return override
        return fallback


def canvas_hit_testing_service_for(canvas) -> CanvasHitTestingService:
    service = getattr(canvas, "_hit_testing_service", None)
    if isinstance(service, CanvasHitTestingService) and service.canvas is canvas:
        return service
    if service is not None and all(
        hasattr(service, name)
        for name in (
            "scene_pos_from_event",
            "item_at_scene_pos",
            "item_at_event",
            "grid_cell_size",
            "cell_coords",
            "ensure_spatial_index",
            "rebuild_spatial_index",
            "find_atom_near",
            "find_bond_near",
            "distance_point_to_segment",
            "nearest_atom_hit",
            "nearest_bond_hit",
            "bond_id_from_event",
        )
    ):
        return service
    return CanvasHitTestingService(canvas)


__all__ = ["CanvasHitTestingService", "canvas_hit_testing_service_for"]
