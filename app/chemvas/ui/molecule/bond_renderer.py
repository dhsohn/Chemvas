from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath, QPolygonF

from chemvas.features.rendering import (
    DOUBLE_STYLE_DEFAULT,
    refresh_bond_graphics,
)
from chemvas.features.rendering import (
    strip_corners as strip_corners_shape,
)
from chemvas.ui.molecule.bond_geometry_plan_service import BondGeometryPlanService
from chemvas.ui.molecule.bond_geometry_update_service import BondGeometryUpdateService
from chemvas.ui.molecule.bond_graphics_build_service import BondGraphicsBuildService
from chemvas.ui.molecule.bond_graphics_draw_service import BondGraphicsDrawService
from chemvas.ui.molecule.bond_graphics_factory import BondGraphicsFactory
from chemvas.ui.molecule.bond_line_geometry_service import BondLineGeometryService
from chemvas.ui.molecule.bond_ring_double_geometry_service import (
    BondRingDoubleGeometryService,
)
from chemvas.ui.scene.scene_graphics_operations import detach_graphics_item

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem

    from chemvas.ui.scene.scene_render_context import SceneRenderContext


class BondRenderer:
    def __init__(self, context: SceneRenderContext) -> None:
        self.context = context
        self.graph = context.state.graph_state
        self.graphics = BondGraphicsFactory(context.renderer)
        self.line_geometry = BondLineGeometryService(context)
        self.graphics_drawer = BondGraphicsDrawService(context, renderer=self)
        self.ring_double_geometry = BondRingDoubleGeometryService(
            context, renderer=self
        )
        self.geometry_planner = BondGeometryPlanService(context, renderer=self)
        self.graphics_builder = BondGraphicsBuildService(
            context,
            renderer=self,
            planner=self.geometry_planner,
        )
        self.geometry_updater = BondGeometryUpdateService(
            context,
            planner=self.geometry_planner,
        )

    def trim_line_for_labels(
        self, a_id, b_id, x1: float, y1: float, x2: float, y2: float, offsets=()
    ):
        return self.context.geometry.trim_line_for_labels(
            a_id, b_id, x1, y1, x2, y2, offsets
        )

    def bond_offset_unit_3d(self, a_id: int, b_id: int, target=None):
        return self.context.geometry.bond_offset_unit_3d(a_id, b_id, target=target)

    def line_normal(self, x1: float, y1: float, x2: float, y2: float, ring_center):
        return self.context.geometry.line_normal(x1, y1, x2, y2, ring_center)

    def label_rect_for_atom(self, atom_id: int):
        return self.context.geometry.label_rect_for_atom(atom_id)

    def current_atom_coords_3d(self, atom_id: int):
        return self.context.geometry.current_atom_coords_3d(atom_id)

    def project_point_3d(self, point):
        return self.context.geometry.project_point_3d(point)

    def ring_center_for_bond(self, bond):
        return self.context.geometry.ring_center_for_bond(bond)

    def ring_center_3d_for_bond(self, bond):
        return self.context.geometry.ring_center_3d_for_bond(bond)

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

    def hash_topology_count(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> int:
        return self.line_geometry.hash_topology_count(x1, y1, x2, y2, a_id, b_id)

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
            bonds=self.context.model.bonds,
            bond_items=self.context.state.bond_graphics_state.bond_items,
            remove_scene_item=lambda item: detach_graphics_item(
                self.context.scene, cast("QGraphicsItem", item)
            ),
            add_bond_graphics=self.add_bond_graphics,
        )

    def add_bond_graphics(self, bond_id: int) -> None:
        self._relayout_bond_atom_labels(bond_id)
        self.graphics_builder.add_bond_graphics(bond_id)

    def _relayout_bond_atom_labels(self, bond_id: int) -> None:
        bonds = self.context.model.bonds
        if not 0 <= bond_id < len(bonds):
            return
        bond = bonds[bond_id]
        if bond is None:
            return
        self.context.atom_labels.relayout_atom_labels(
            {bond.a, bond.b}, skip_bond_ids={bond_id}
        )


__all__ = ["BondRenderer"]
