from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPolygonF

from ui.canvas_mark_registry import mark_registry_for


class CanvasMoveController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas
        self.marks = mark_registry_for(canvas)

    def move_item(self, item, dx: float, dy: float, update_selection: bool = True) -> None:
        kind = item.data(0)
        if kind == "atom":
            atom_id = item.data(1)
            if not isinstance(atom_id, int):
                return
            atom = self.canvas.model.atoms.get(atom_id)
            if atom is None:
                return
            atom.x += dx
            atom.y += dy
            item.moveBy(dx, dy)
            for bond_id, bond in enumerate(self.canvas.model.bonds):
                if bond is None:
                    continue
                if bond.a == atom_id or bond.b == atom_id:
                    self.canvas._redraw_bond(bond_id)
        elif kind == "bond":
            bond_id = item.data(1)
            if not isinstance(bond_id, int):
                return
            bond = self.canvas.model.bonds[bond_id]
            if bond is None:
                return
            self.canvas._move_atom(bond.a, dx, dy)
            self.canvas._move_atom(bond.b, dx, dy)
            self.canvas._redraw_connected_bonds(bond.a)
            self.canvas._redraw_connected_bonds(bond.b)
        elif kind == "mark":
            item.moveBy(dx, dy)
            data = item.data(1) or {}
            atom_id = data.get("atom_id")
            if isinstance(atom_id, int):
                atom = self.canvas.model.atoms.get(atom_id)
                if atom is not None:
                    center = self.canvas._mark_center(item)
                    data["dx"] = center.x() - atom.x
                    data["dy"] = center.y() - atom.y
                    item.setData(1, data)
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
        if update_selection:
            self.canvas._update_selection_outline()

    def move_atoms(
        self,
        atom_ids: set[int],
        dx: float,
        dy: float,
        bond_ids: set[int] | None = None,
        redraw_bond_ids: set[int] | None = None,
        update_selection: bool = True,
    ) -> None:
        if not atom_ids:
            return
        for atom_id in atom_ids:
            self.canvas._move_atom(atom_id, dx, dy)
        use_bond_sets = bond_ids is not None or redraw_bond_ids is not None
        if use_bond_sets:
            if bond_ids:
                for bond_id in bond_ids:
                    for item in self.canvas.bond_items.get(bond_id, []):
                        item.moveBy(dx, dy)
            if redraw_bond_ids:
                for bond_id in redraw_bond_ids:
                    self.canvas.update_bond_geometry(bond_id)
        else:
            self.canvas._redraw_bonds_for_atoms(atom_ids)
        self.canvas._move_rings_for_atoms(atom_ids, dx, dy)
        if update_selection:
            self.canvas._update_selection_outline()

    def move_rings_for_atoms(self, atom_ids: set[int], _dx: float, _dy: float) -> None:
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

    def move_atom(self, atom_id: int, dx: float, dy: float) -> None:
        atom = self.canvas.model.atoms.get(atom_id)
        if atom is None:
            return
        atom.x += dx
        atom.y += dy
        self.canvas._mark_spatial_index_dirty()
        if atom_id in self.canvas.atom_coords_3d:
            x, y, z = self.canvas.atom_coords_3d[atom_id]
            self.canvas.atom_coords_3d[atom_id] = (x + dx, y + dy, z)
        label = self.canvas.atom_items.get(atom_id)
        if label is not None:
            label.moveBy(dx, dy)
        dot = self.canvas.atom_dots.get(atom_id)
        if dot is not None:
            dot.moveBy(dx, dy)
        marks = self.marks.get_for_atom(atom_id)
        if marks:
            for mark in list(marks):
                mark.moveBy(dx, dy)


__all__ = ["CanvasMoveController"]
