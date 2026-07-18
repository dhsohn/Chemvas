from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id
from chemvas.ui.canvas_hit_testing_scene_access import scene_items_at_pos_for_canvas
from chemvas.ui.canvas_hover_state import hover_state_for
from chemvas.ui.canvas_model_access import (
    atom_for_id,
    atoms_for,
    bond_for_id,
    bonds_for,
    has_atoms_for,
)
from chemvas.ui.pick_radius_access import atom_pick_radius_for, bond_pick_radius_for
from chemvas.ui.renderer_style_access import bond_length_px_for
from chemvas.ui.spatial_index_state import (
    atom_ids_in_spatial_cell_for,
    bond_ids_in_spatial_cell_for,
    has_fresh_spatial_index_for,
    mark_spatial_index_dirty_for,
    set_spatial_index_for,
    spatial_cell_size_or_for,
)

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


class CanvasHitTestingService:
    def __init__(self, canvas: CanvasView, *, scene_pos_mapper=None) -> None:
        self.canvas = canvas
        self._scene_pos_mapper = scene_pos_mapper

    def scene_pos_from_event(self, event) -> QPointF:
        if callable(self._scene_pos_mapper):
            return self._scene_pos_mapper(event)
        raise AttributeError(
            "CanvasHitTestingService requires an injected scene_pos_mapper"
        )

    def item_at_scene_pos(self, pos: QPointF):
        bond_item = None
        ring_item = None
        other_item = None
        for item in scene_items_at_pos_for_canvas(self.canvas, pos):
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
            nearby_bond_id = self.find_bond_near(pos, bond_pick_radius_for(self.canvas))
            if nearby_bond_id is not None:
                nearby_items = bond_items_for_id(self.canvas, nearby_bond_id)
                if nearby_items:
                    return nearby_items[0]
        return bond_item or ring_item or other_item

    def item_at_event(self, event):
        return self.item_at_scene_pos(self.scene_pos_from_event(event))

    def grid_cell_size(self) -> float:
        return max(8.0, bond_length_px_for(self.canvas))

    @staticmethod
    def cell_coords(x: float, y: float, cell_size: float) -> tuple[int, int]:
        return math.floor(x / cell_size), math.floor(y / cell_size)

    def ensure_spatial_index(self) -> None:
        cell_size = self.grid_cell_size()
        if has_fresh_spatial_index_for(
            self.canvas,
            cell_size,
            atom_count=len(atoms_for(self.canvas)),
            bond_slot_count=len(bonds_for(self.canvas)),
        ):
            return
        self.rebuild_spatial_index(cell_size)

    def rebuild_spatial_index(self, cell_size: float) -> None:
        atom_grid: dict[tuple[int, int], set[int]] = {}
        for atom_id, atom in atoms_for(self.canvas).items():
            key = self.cell_coords(atom.x, atom.y, cell_size)
            atom_grid.setdefault(key, set()).add(atom_id)

        bond_grid: dict[tuple[int, int], set[int]] = {}
        for bond_id, bond in enumerate(bonds_for(self.canvas)):
            if bond is None:
                continue
            a = atom_for_id(self.canvas, bond.a)
            b = atom_for_id(self.canvas, bond.b)
            if a is None or b is None:
                continue
            min_x = min(a.x, b.x)
            max_x = max(a.x, b.x)
            min_y = min(a.y, b.y)
            max_y = max(a.y, b.y)
            min_ix, min_iy = self.cell_coords(min_x, min_y, cell_size)
            max_ix, max_iy = self.cell_coords(max_x, max_y, cell_size)
            for ix in range(min_ix, max_ix + 1):
                for iy in range(min_iy, max_iy + 1):
                    bond_grid.setdefault((ix, iy), set()).add(bond_id)

        set_spatial_index_for(
            self.canvas,
            atom_grid=atom_grid,
            bond_grid=bond_grid,
            cell_size=cell_size,
            atom_count=len(atoms_for(self.canvas)),
            bond_slot_count=len(bonds_for(self.canvas)),
        )

    def mark_spatial_index_dirty(self) -> None:
        mark_spatial_index_dirty_for(self.canvas)

    def find_atom_near(self, x: float, y: float, max_dist: float) -> int | None:
        if not has_atoms_for(self.canvas):
            return None
        self.ensure_spatial_index()
        cell_size = spatial_cell_size_or_for(self.canvas, self.grid_cell_size())
        if cell_size <= 0:
            return None
        cell_radius = math.ceil(max_dist / cell_size)
        ix, iy = self.cell_coords(x, y, cell_size)
        nearest_id = None
        nearest_dist_sq = max_dist * max_dist
        for cx in range(ix - cell_radius, ix + cell_radius + 1):
            for cy in range(iy - cell_radius, iy + cell_radius + 1):
                for atom_id in atom_ids_in_spatial_cell_for(self.canvas, (cx, cy)):
                    atom = atom_for_id(self.canvas, atom_id)
                    if atom is None:
                        continue
                    dx = atom.x - x
                    dy = atom.y - y
                    dist_sq = dx * dx + dy * dy
                    # Lowest atom id breaks exact-distance ties so the pick
                    # does not depend on set iteration order.
                    if dist_sq < nearest_dist_sq or (
                        dist_sq == nearest_dist_sq
                        and (nearest_id is None or atom_id < nearest_id)
                    ):
                        nearest_id = atom_id
                        nearest_dist_sq = dist_sq
        return nearest_id

    def find_bond_near(self, pos: QPointF, max_dist: float) -> int | None:
        if not bonds_for(self.canvas):
            return None
        self.ensure_spatial_index()
        cell_size = spatial_cell_size_or_for(self.canvas, self.grid_cell_size())
        if cell_size <= 0:
            return None
        cell_radius = math.ceil(max_dist / cell_size)
        ix, iy = self.cell_coords(pos.x(), pos.y(), cell_size)
        nearest = None
        nearest_dist = max_dist
        seen: set[int] = set()
        for cx in range(ix - cell_radius, ix + cell_radius + 1):
            for cy in range(iy - cell_radius, iy + cell_radius + 1):
                for bond_id in bond_ids_in_spatial_cell_for(self.canvas, (cx, cy)):
                    if bond_id in seen:
                        continue
                    seen.add(bond_id)
                    bond = bond_for_id(self.canvas, bond_id)
                    if bond is None:
                        continue
                    a = atom_for_id(self.canvas, bond.a)
                    b = atom_for_id(self.canvas, bond.b)
                    if a is None or b is None:
                        continue
                    dist = self.distance_point_to_segment(
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
        atom_id = self.find_atom_near(
            pos.x(), pos.y(), atom_pick_radius_for(self.canvas)
        )
        if atom_id is None:
            return None
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return None
        return atom_id, math.hypot(atom.x - pos.x(), atom.y - pos.y())

    def nearest_bond_hit(self, pos: QPointF) -> tuple[int, float] | None:
        bond_id = self.find_bond_near(pos, bond_pick_radius_for(self.canvas))
        if bond_id is None:
            return None
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None:
            return None
        atom_a = atom_for_id(self.canvas, bond.a)
        atom_b = atom_for_id(self.canvas, bond.b)
        if atom_a is None or atom_b is None:
            return None
        dist = self.distance_point_to_segment(
            pos,
            QPointF(atom_a.x, atom_a.y),
            QPointF(atom_b.x, atom_b.y),
        )
        return bond_id, dist

    def bond_id_from_event(self, event) -> int | None:
        hover_bond_id = hover_state_for(self.canvas).bond_id
        if hover_bond_id is not None:
            return hover_bond_id
        pos = self.scene_pos_from_event(event)
        return self.find_bond_near(
            pos,
            max(
                bond_length_px_for(self.canvas) * 0.35,
                bond_pick_radius_for(self.canvas),
            ),
        )


__all__ = ["CanvasHitTestingService"]
