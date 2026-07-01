from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath, QPolygonF

from ui.atom_coords_access import current_atom_coords_3d_for
from ui.bond_geometry_primitives import (
    strip_polygon as strip_polygon_shape,
)
from ui.bond_geometry_update_service import BondGeometryUpdateService
from ui.bond_graphics_access import (
    bond_offset_unit_3d_for,
    line_normal_for,
    project_point_3d_for,
    ring_center_3d_for_bond_for,
    ring_center_for_bond_for,
)
from ui.bond_graphics_build_service import BondGraphicsBuildService
from ui.bond_graphics_draw_service import BondGraphicsDrawService
from ui.bond_graphics_factory import BondGraphicsFactory
from ui.bond_graphics_logic import refresh_bond_graphics
from ui.bond_label_geometry_access import (
    label_rect_for_atom_for,
    trim_line_for_labels_for,
)
from ui.bond_line_geometry_service import BondLineGeometryService
from ui.bond_renderer_access import bond_renderer_for
from ui.bond_ring_double_geometry_service import BondRingDoubleGeometryService
from ui.bond_style_logic import (
    DOUBLE_STYLE_DEFAULT,
)
from ui.canvas_bond_graphics_state import (
    bond_items_for,
)
from ui.canvas_graph_state import graph_state_for
from ui.canvas_model_access import bonds_for
from ui.renderer_style_access import (
    renderer_for,
)
from ui.scene_item_access import remove_item_from_canvas_scene


class BondRenderer:
    def __init__(self, canvas) -> None:
        self.canvas = canvas
        self.graph = graph_state_for(canvas)
        self.graphics = BondGraphicsFactory(renderer_for(canvas))
        self.line_geometry = BondLineGeometryService(canvas)
        self.graphics_drawer = BondGraphicsDrawService(canvas, renderer=self)
        self.graphics_builder = BondGraphicsBuildService(canvas, renderer=self, drawer=self.graphics_drawer)
        self.geometry_updater = BondGeometryUpdateService(canvas, renderer=self)
        self.ring_double_geometry = BondRingDoubleGeometryService(canvas, renderer=self)

    def trim_line_for_labels(self, a_id, b_id, x1: float, y1: float, x2: float, y2: float):
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
        return self.line_geometry.dotted_bond_path(x1, y1, x2, y2, a_id, b_id)

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
        return self.line_geometry.parallel_bond_segments(x1, y1, x2, y2, count, a_id, b_id)

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
    ) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float], tuple[float, float]]:
        return self.line_geometry.plain_double_segments(x1, y1, x2, y2, style=style, a_id=a_id, b_id=b_id)

    def wedge_polygon(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> QPolygonF:
        return self.line_geometry.wedge_polygon(x1, y1, x2, y2, a_id, b_id)

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
        return strip_polygon_shape(x1, y1, x2, y2, nx, ny, base_width, bold_width)

    def ring_double_segments(
        self,
        a,
        b,
        center: QPointF,
        a_id: int | None = None,
        b_id: int | None = None,
        center_3d: tuple[float, float, float] | None = None,
        style: str = DOUBLE_STYLE_DEFAULT,
    ) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float], tuple[float, float]]:
        return self.ring_double_geometry.ring_double_segments(a, b, center, a_id, b_id, center_3d, style)

    def draw_ring_double_bond(
        self,
        a,
        b,
        center: QPointF,
        a_id: int | None = None,
        b_id: int | None = None,
        outer_style: str = "normal",
        center_3d: tuple[float, float, float] | None = None,
        style: str = DOUBLE_STYLE_DEFAULT,
    ):
        return self.graphics_drawer.draw_ring_double_bond(
            a,
            b,
            center,
            a_id,
            b_id,
            outer_style=outer_style,
            center_3d=center_3d,
            style=style,
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
        return self.graphics_drawer.one_sided_bond_strip(x1, y1, x2, y2, nx, ny, base_width, bold_width)

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
        return self.graphics_drawer.draw_parallel_bonds(x1, y1, x2, y2, count, a_id, b_id)

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

    def draw_dotted_double_bond(
        self,
        a,
        b,
        *,
        style: str,
        a_id: int | None = None,
        b_id: int | None = None,
        ring_center: QPointF | None = None,
        center_3d: tuple[float, float, float] | None = None,
    ):
        return self.graphics_drawer.draw_dotted_double_bond(
            a,
            b,
            style=style,
            a_id=a_id,
            b_id=b_id,
            ring_center=ring_center,
            center_3d=center_3d,
        )

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

    def update_bond_geometry(self, bond_id: int) -> None:
        self.geometry_updater.update_bond_geometry(bond_id)

    def redraw_connected_bonds(self, atom_id: int, skip_bond_id: int | None = None) -> None:
        for bond_id in self.graph.atom_bond_ids.get(atom_id, ()):
            if skip_bond_id is not None and bond_id == skip_bond_id:
                continue
            self.redraw_bond(bond_id)

    def redraw_bond(self, bond_id: int) -> bool:
        return refresh_bond_graphics(
            bond_id,
            bonds=bonds_for(self.canvas),
            bond_items=bond_items_for(self.canvas),
            remove_scene_item=lambda item: remove_item_from_canvas_scene(self.canvas, item),
            add_bond_graphics=self.add_bond_graphics,
        )

    def add_bond_graphics(self, bond_id: int) -> None:
        self.graphics_builder.add_bond_graphics(bond_id)


__all__ = ["BondRenderer", "bond_renderer_for"]
