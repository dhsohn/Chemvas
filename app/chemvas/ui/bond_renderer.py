from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath, QPolygonF

from chemvas.features.rendering import (
    DOUBLE_STYLE_DEFAULT,
    refresh_bond_graphics,
)
from chemvas.features.rendering import (
    strip_corners as strip_corners_shape,
)
from chemvas.ui.atom_coords_access import current_atom_coords_3d_for
from chemvas.ui.bond_geometry_plan_service import BondGeometryPlanService
from chemvas.ui.bond_geometry_update_service import BondGeometryUpdateService
from chemvas.ui.bond_graphics_access import (
    bond_offset_unit_3d_for,
    line_normal_for,
    project_point_3d_for,
    ring_center_3d_for_bond_for,
    ring_center_for_bond_for,
)
from chemvas.ui.bond_graphics_build_service import BondGraphicsBuildService
from chemvas.ui.bond_graphics_draw_service import BondGraphicsDrawService
from chemvas.ui.bond_graphics_factory import BondGraphicsFactory
from chemvas.ui.bond_label_geometry_access import (
    label_rect_for_atom_for,
    trim_line_for_labels_for,
)
from chemvas.ui.bond_line_geometry_service import BondLineGeometryService
from chemvas.ui.bond_ring_double_geometry_service import BondRingDoubleGeometryService
from chemvas.ui.canvas_bond_graphics_state import (
    bond_items_for,
)
from chemvas.ui.canvas_graph_state import graph_state_for
from chemvas.ui.canvas_model_access import bonds_for
from chemvas.ui.renderer_style_access import (
    renderer_for,
)
from chemvas.ui.scene_item_access import remove_item_from_canvas_scene

if TYPE_CHECKING:
    from collections.abc import Callable


class BondRenderer:
    def __init__(
        self,
        canvas,
        *,
        atom_label_relayout: Callable[[set[int], set[int]], None] | None = None,
    ) -> None:
        self.canvas = canvas
        self._atom_label_relayout = atom_label_relayout
        self.graph = graph_state_for(canvas)
        self.graphics = BondGraphicsFactory(renderer_for(canvas))
        self.line_geometry = BondLineGeometryService(canvas)
        self.graphics_drawer = BondGraphicsDrawService(canvas, renderer=self)
        self.ring_double_geometry = BondRingDoubleGeometryService(canvas, renderer=self)
        self.geometry_planner = BondGeometryPlanService(canvas, renderer=self)
        self.graphics_builder = BondGraphicsBuildService(
            canvas,
            renderer=self,
            planner=self.geometry_planner,
        )
        self.geometry_updater = BondGeometryUpdateService(
            canvas,
            planner=self.geometry_planner,
        )

    def trim_line_for_labels(
        self, a_id, b_id, x1: float, y1: float, x2: float, y2: float
    ):
        return trim_line_for_labels_for(self.canvas, a_id, b_id, x1, y1, x2, y2)

    def bond_offset_unit_3d(self, a_id: int, b_id: int, target=None):
        return bond_offset_unit_3d_for(self.canvas, a_id, b_id, target=target)

    def line_normal(self, x1: float, y1: float, x2: float, y2: float, ring_center):
        return line_normal_for(self.canvas, x1, y1, x2, y2, ring_center)

    def label_rect_for_atom(self, atom_id: int):
        return label_rect_for_atom_for(self.canvas, atom_id)

    def current_atom_coords_3d(self, atom_id: int):
        return current_atom_coords_3d_for(self.canvas, atom_id)

    def project_point_3d(self, point):
        return project_point_3d_for(self.canvas, point)

    def ring_center_for_bond(self, bond):
        return ring_center_for_bond_for(self.canvas, bond)

    def ring_center_3d_for_bond(self, bond):
        return ring_center_3d_for_bond_for(self.canvas, bond)

    def dotted_bond_path(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> QPainterPath:
        centers, radius = self.line_geometry.dotted_bond_dots(
            x1, y1, x2, y2, a_id, b_id
        )
        path = QPainterPath()
        for center_x, center_y in centers:
            path.addEllipse(QPointF(center_x, center_y), radius, radius)
        return path

    def parallel_bond_segments(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        count: int,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> list[tuple[float, float, float, float]]:
        return self.line_geometry.parallel_bond_segments(
            x1, y1, x2, y2, count, a_id, b_id
        )

    def plain_double_segments(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        style: str,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> tuple[
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float],
    ]:
        return self.line_geometry.plain_double_segments(
            x1, y1, x2, y2, style=style, a_id=a_id, b_id=b_id
        )

    def wedge_polygon(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> QPolygonF:
        corners = self.line_geometry.wedge_triangle(x1, y1, x2, y2, a_id, b_id)
        return QPolygonF([QPointF(x, y) for x, y in corners])

    def hash_segments(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        count: int,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> list[tuple[float, float, float, float]]:
        return self.line_geometry.hash_segments(x1, y1, x2, y2, count, a_id, b_id)

    def strip_polygon(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        nx: float,
        ny: float,
        base_width: float,
        bold_width: float,
    ) -> QPolygonF:
        corners = strip_corners_shape(x1, y1, x2, y2, nx, ny, base_width, bold_width)
        return QPolygonF([QPointF(x, y) for x, y in corners])

    def ring_double_segments(
        self,
        a,
        b,
        center: QPointF,
        a_id: int | None = None,
        b_id: int | None = None,
        center_3d: tuple[float, float, float] | None = None,
        style: str = DOUBLE_STYLE_DEFAULT,
    ) -> tuple[
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float],
    ]:
        return self.ring_double_geometry.ring_double_segments(
            a, b, center, a_id, b_id, center_3d, style
        )

    def one_sided_bond_strip(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        nx: float,
        ny: float,
        base_width: float,
        bold_width: float,
    ):
        return self.graphics_drawer.one_sided_bond_strip(
            x1, y1, x2, y2, nx, ny, base_width, bold_width
        )

    def draw_parallel_bonds(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        count: int,
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        return self.graphics_drawer.draw_parallel_bonds(
            x1, y1, x2, y2, count, a_id, b_id
        )

    def draw_dotted_bond(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        return self.graphics_drawer.draw_dotted_bond(x1, y1, x2, y2, a_id, b_id)

    def draw_wedge_bond(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        return self.graphics_drawer.draw_wedge_bond(x1, y1, x2, y2, a_id, b_id)

    def draw_hash_bond(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        return self.graphics_drawer.draw_hash_bond(x1, y1, x2, y2, a_id, b_id)

    def update_bond_geometry(
        self, bond_id: int, *, allow_topology_rebuild: bool = False
    ) -> None:
        self._relayout_bond_atom_labels(bond_id)
        if allow_topology_rebuild and self.geometry_updater.topology_is_stale(bond_id):
            # A gesture or history step just finished: keeping the mid-gesture
            # item identity would freeze a hash-mark count that reopening the
            # document will not reproduce. Mid-gesture callers keep the
            # default, because the drag transaction tracks the live items.
            self.redraw_bond(bond_id)
            return
        self.geometry_updater.update_bond_geometry(bond_id)

    def redraw_connected_bonds(
        self, atom_id: int, skip_bond_id: int | None = None
    ) -> None:
        for bond_id in self.graph.atom_bond_ids.get(atom_id, ()):
            if skip_bond_id is not None and bond_id == skip_bond_id:
                continue
            self.redraw_bond(bond_id)

    def redraw_bond(self, bond_id: int) -> bool:
        return refresh_bond_graphics(
            bond_id,
            bonds=bonds_for(self.canvas),
            bond_items=bond_items_for(self.canvas),
            remove_scene_item=lambda item: remove_item_from_canvas_scene(
                self.canvas, item
            ),
            add_bond_graphics=self.add_bond_graphics,
        )

    def add_bond_graphics(self, bond_id: int) -> None:
        self._relayout_bond_atom_labels(bond_id)
        self.graphics_builder.add_bond_graphics(bond_id)

    def _relayout_bond_atom_labels(self, bond_id: int) -> None:
        if self._atom_label_relayout is None:
            return
        bonds = bonds_for(self.canvas)
        if not 0 <= bond_id < len(bonds):
            return
        bond = bonds[bond_id]
        if bond is None:
            return
        self._atom_label_relayout({bond.a, bond.b}, {bond_id})


__all__ = ["BondRenderer"]
