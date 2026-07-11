from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPolygonF

from ui.atom_coords_access import atom_coords_3d_for_id, set_atom_coords_3d_for_id
from ui.bond_renderer import bond_renderer_for
from ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from ui.canvas_bond_graphics_state import bond_items_for_id
from ui.canvas_bond_renderer_state import update_bond_geometry_for
from ui.canvas_graph_state import graph_state_for
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import atom_for_id, bond_for_id, bonds_for
from ui.canvas_scene_items_state import ring_items_for
from ui.handle_state import active_handles_for, handle_target_for
from ui.mark_item_access import mark_center_for
from ui.selection_service_access import refresh_selection_outline_for
from ui.shape_geometry import normalized_shape_kind, shape_path


class CanvasMoveController:
    def __init__(self, canvas, *, hit_testing_service) -> None:
        self.canvas = canvas
        self.marks = mark_registry_for(canvas)
        self.hit_testing_service = hit_testing_service

    def move_item(self, item, dx: float, dy: float, update_selection: bool = True) -> None:
        kind = item.data(0)
        if kind == "atom":
            atom_id = item.data(1)
            if not isinstance(atom_id, int):
                return
            if atom_for_id(self.canvas, atom_id) is None:
                return
            # Delegate to move_atom so the atom's companions move together:
            # its label/dot, attached marks, 3D coordinates, and the hit-test
            # spatial index. The grabbed ``item`` is the registered label or
            # dot, which move_atom repositions by id, so we must not also call
            # item.moveBy here (that would double-move it). This mirrors the
            # multi-atom move_atoms path and fixes single-atom drags that
            # previously left marks behind and the spatial index stale.
            self.move_atom(atom_id, dx, dy)
            for bond_id, bond in enumerate(bonds_for(self.canvas)):
                if bond is None:
                    continue
                if bond.a == atom_id or bond.b == atom_id:
                    self.redraw_bond(bond_id)
        elif kind == "bond":
            bond_id = item.data(1)
            if not isinstance(bond_id, int):
                return
            bond = bond_for_id(self.canvas, bond_id)
            if bond is None:
                return
            self.move_atom(bond.a, dx, dy)
            self.move_atom(bond.b, dx, dy)
            self.redraw_connected_bonds(bond.a)
            self.redraw_connected_bonds(bond.b)
        elif kind == "mark":
            item.moveBy(dx, dy)
            data = item.data(1) or {}
            atom_id = data.get("atom_id")
            if isinstance(atom_id, int):
                atom = atom_for_id(self.canvas, atom_id)
                if atom is not None:
                    center = mark_center_for(self.canvas, item)
                    data["dx"] = center.x() - atom.x
                    data["dy"] = center.y() - atom.y
                    item.setData(1, data)
        elif kind == "shape":
            # Move a shape by rebuilding its path in scene coordinates and keeping
            # item.pos() at the origin. Using moveBy here would leave a non-zero
            # pos that a later resize (which rebuilds the path in scene space)
            # double-applies, making the shape jump away from its handles.
            data = item.data(1) or {}
            rect = data.get("rect")
            if isinstance(rect, QRectF):
                new_rect = rect.translated(dx, dy)
                data["rect"] = new_rect
                item.setData(1, data)
                item.setPath(shape_path(new_rect, normalized_shape_kind(data.get("shape_kind"))))
        elif kind in {
            "arrow",
            "equilibrium",
            "resonance",
            "curved_single",
            "curved_double",
            "inhibit",
            "dotted",
            "ts_bracket",
            "orbital",
            "note",
        }:
            item.moveBy(dx, dy)
            if kind == "orbital":
                data = item.data(1) or {}
                center = data.get("center")
                if isinstance(center, QPointF):
                    data["center"] = QPointF(center.x() + dx, center.y() + dy)
                    item.setData(1, data)
            elif kind == "ts_bracket":
                data = item.data(1) or {}
                rect = data.get("rect")
                if isinstance(rect, QRectF):
                    data["rect"] = rect.translated(dx, dy)
                    item.setData(1, data)
            else:
                data = item.data(2) or {}
                start = data.get("start")
                end = data.get("end")
                control = data.get("control")
                if isinstance(start, QPointF) and isinstance(end, QPointF):
                    data["start"] = QPointF(start.x() + dx, start.y() + dy)
                    data["end"] = QPointF(end.x() + dx, end.y() + dy)
                if isinstance(control, QPointF):
                    data["control"] = QPointF(control.x() + dx, control.y() + dy)
                item.setData(2, data)
        self._shift_active_handles_for(item, dx, dy)
        if update_selection:
            refresh_selection_outline_for(self.canvas)

    def _shift_active_handles_for(self, item, dx: float, dy: float) -> None:
        # Keep resize/transform handles glued to their item as it is dragged.
        if item is not handle_target_for(self.canvas):
            return
        for handle in active_handles_for(self.canvas):
            handle.moveBy(dx, dy)

    def move_atoms(
        self,
        atom_ids: set[int],
        dx: float,
        dy: float,
        bond_ids: set[int] | None = None,
        redraw_bond_ids: set[int] | None = None,
        update_selection: bool = True,
        affected_ring_items: tuple[Any, ...] | None = None,
    ) -> None:
        if not atom_ids:
            return
        for atom_id in atom_ids:
            self.move_atom(atom_id, dx, dy)
        use_bond_sets = bond_ids is not None or redraw_bond_ids is not None
        if use_bond_sets:
            if bond_ids:
                for bond_id in bond_ids:
                    for item in bond_items_for_id(self.canvas, bond_id):
                        item.moveBy(dx, dy)
            if redraw_bond_ids:
                for bond_id in redraw_bond_ids:
                    update_bond_geometry_for(self.canvas, bond_id)
        else:
            self.redraw_bonds_for_atoms(atom_ids)
        if affected_ring_items is None:
            self.move_rings_for_atoms(atom_ids, dx, dy)
        else:
            self.move_rings_for_atoms(
                atom_ids,
                dx,
                dy,
                affected_ring_items=affected_ring_items,
            )
        if update_selection:
            refresh_selection_outline_for(self.canvas)

    def redraw_bonds_for_atoms(self, atom_ids: set[int]) -> None:
        for bond_id in self.bond_ids_for_atom_ids(atom_ids):
            self.redraw_bond(bond_id)

    def update_bond_geometries_for_atoms(self, atom_ids: set[int]) -> None:
        """Refresh coordinates in place when the graphics topology is unchanged."""

        for bond_id in self.bond_ids_for_atom_ids(atom_ids):
            update_bond_geometry_for(self.canvas, bond_id)

    def redraw_bond(self, bond_id: int) -> bool:
        return bond_renderer_for(self.canvas).redraw_bond(bond_id)

    def redraw_connected_bonds(self, atom_id: int, skip_bond_id: int | None = None) -> None:
        bond_renderer_for(self.canvas).redraw_connected_bonds(atom_id, skip_bond_id=skip_bond_id)

    def bond_ids_for_atom_ids(self, atom_ids: set[int]) -> set[int]:
        graph = graph_state_for(self.canvas)
        bond_ids: set[int] = set()
        for atom_id in atom_ids:
            bond_ids.update(graph.atom_bond_ids.get(atom_id, ()))
        return bond_ids

    def move_rings_for_atoms(
        self,
        atom_ids: set[int],
        _dx: float,
        _dy: float,
        *,
        affected_ring_items: tuple[Any, ...] | None = None,
    ) -> None:
        ring_items = (
            ring_items_for(self.canvas)
            if affected_ring_items is None
            else affected_ring_items
        )
        for ring_item in ring_items:
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

    def move_atom(self, atom_id: int, dx: float, dy: float) -> None:
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return
        atom.x += dx
        atom.y += dy
        self.hit_testing_service.mark_spatial_index_dirty()
        coords_3d = atom_coords_3d_for_id(self.canvas, atom_id)
        if coords_3d is not None:
            x, y, z = coords_3d
            set_atom_coords_3d_for_id(self.canvas, atom_id, (x + dx, y + dy, z))
        label = atom_items_for(self.canvas).get(atom_id)
        if label is not None:
            label.moveBy(dx, dy)
        dot = atom_dots_for(self.canvas).get(atom_id)
        if dot is not None:
            dot.moveBy(dx, dy)
        marks = self.marks.get_for_atom(atom_id)
        if marks:
            for mark in list(marks):
                mark.moveBy(dx, dy)


__all__ = ["CanvasMoveController"]
