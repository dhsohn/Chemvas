from __future__ import annotations

from dataclasses import replace
from typing import Any

from chemvas.domain.document import VALID_ARROW_KINDS
from chemvas.features.selection import translate_projected_point_3d
from chemvas.ui.annotations.records import (
    moved_ts_bracket,
    require_shape_record_for,
    require_ts_bracket_record_for,
    set_shape_record_for,
    set_ts_bracket_record_for,
)
from chemvas.ui.canvas.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from chemvas.ui.canvas.canvas_bond_graphics_state import bond_items_for_id
from chemvas.ui.canvas.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas.canvas_model_access import (
    atom_for_id,
    bond_for_id,
    bonds_for,
)
from chemvas.ui.canvas.canvas_ring_fill_scene_service import rebuild_ring_fill_polygons
from chemvas.ui.canvas.canvas_scene_items_state import ring_items_for
from chemvas.ui.molecule.atom_coords_access import (
    atom_coords_3d_for_id,
    set_atom_coords_3d_for_id,
)
from chemvas.ui.molecule.bond_renderer_access import (
    bond_renderer_for,
    update_bond_geometry_for,
)
from chemvas.ui.scene.mark_item_access import mark_center_for
from chemvas.ui.selection.selection_state import selection_for
from chemvas.ui.tools.handle_state import active_handles_for, handle_target_for

# Annotation items whose geometry follows their Qt translation.
_MOVE_BY_ITEM_KINDS = frozenset(
    {
        "note",
    }
)


class CanvasMoveController:
    def __init__(self, canvas, *, hit_testing_service) -> None:
        self.canvas = canvas
        self.marks = mark_registry_for(canvas)
        self.hit_testing_service = hit_testing_service

    def move_item(
        self, item, dx: float, dy: float, update_selection: bool = True
    ) -> None:
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
            shape = require_shape_record_for(self.canvas, item)
            set_shape_record_for(
                self.canvas,
                item,
                replace(
                    shape,
                    left=shape.left + dx,
                    top=shape.top + dy,
                    right=shape.right + dx,
                    bottom=shape.bottom + dy,
                ),
            )
        elif kind == "ts_bracket":
            # Like a shape: the path is rebuilt in scene coordinates and
            # item.pos() stays at the origin.
            set_ts_bracket_record_for(
                self.canvas,
                item,
                moved_ts_bracket(
                    require_ts_bracket_record_for(self.canvas, item), dx, dy
                ),
            )
        elif kind in VALID_ARROW_KINDS:
            arrows = self.canvas.render_context.arrows
            record = arrows.record(item)
            arrows.set_record(
                item,
                replace(
                    record,
                    start=(record.start[0] + dx, record.start[1] + dy),
                    end=(record.end[0] + dx, record.end[1] + dy),
                    control=None
                    if record.control is None
                    else (record.control[0] + dx, record.control[1] + dy),
                ),
            )
        elif kind == "image":
            state = item.image_state()
            item.apply_image_state(
                {**state, "x": state["x"] + dx, "y": state["y"] + dy}
            )
        elif kind == "orbital":
            state = item.orbital_state()
            x, y = state["center"]
            item.apply_orbital_state({**state, "center": (x + dx, y + dy)})
        elif kind in _MOVE_BY_ITEM_KINDS:
            item.moveBy(dx, dy)
        self._shift_active_handles_for(item, dx, dy)
        if update_selection:
            selection_for(self.canvas).update_selection_outline()

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
        rebuild_stale_bond_topology: bool = False,
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
                    update_bond_geometry_for(
                        self.canvas,
                        bond_id,
                        allow_topology_rebuild=rebuild_stale_bond_topology,
                    )
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
            selection_for(self.canvas).update_selection_outline()

    def redraw_bonds_for_atoms(self, atom_ids: set[int]) -> None:
        for bond_id in self.bond_ids_for_atom_ids(atom_ids):
            self.redraw_bond(bond_id)

    def update_bond_geometries_for_atoms(
        self, atom_ids: set[int], *, rebuild_stale_bond_topology: bool = False
    ) -> None:
        """Refresh coordinates in place when the graphics topology is unchanged.

        One-shot applications (history replay, gesture end) pass
        ``rebuild_stale_bond_topology=True`` so a bond whose length change
        altered its derived item count (hash marks) is rebuilt instead of
        keeping the frozen mid-gesture count.
        """

        for bond_id in self.bond_ids_for_atom_ids(atom_ids):
            update_bond_geometry_for(
                self.canvas,
                bond_id,
                allow_topology_rebuild=rebuild_stale_bond_topology,
            )

    def redraw_bond(self, bond_id: int) -> bool:
        return bond_renderer_for(self.canvas).redraw_bond(bond_id)

    def redraw_connected_bonds(
        self, atom_id: int, skip_bond_id: int | None = None
    ) -> None:
        bond_renderer_for(self.canvas).redraw_connected_bonds(
            atom_id, skip_bond_id=skip_bond_id
        )

    def bond_ids_for_atom_ids(self, atom_ids: set[int]) -> set[int]:
        graph = self.canvas.runtime_state.graph_state
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
        # A ring fill is a polygon over its atoms, so moving them refits it
        # rather than translating it; the deltas are the caller's, not ours.
        rebuild_ring_fill_polygons(
            self.canvas,
            atom_ids,
            ring_items_for(self.canvas)
            if affected_ring_items is None
            else affected_ring_items,
        )

    def move_atom(self, atom_id: int, dx: float, dy: float) -> None:
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return
        atom.x += dx
        atom.y += dy
        self.hit_testing_service.mark_spatial_index_dirty()
        coords_3d = atom_coords_3d_for_id(self.canvas, atom_id)
        if coords_3d is not None:
            set_atom_coords_3d_for_id(
                self.canvas,
                atom_id,
                translate_projected_point_3d(
                    coords_3d,
                    dx,
                    dy,
                    bond_length_px=self.canvas.renderer.style.bond_length_px,
                    center_3d=self.canvas.runtime_state.rotation_state.projection_center_3d,
                ),
            )
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
