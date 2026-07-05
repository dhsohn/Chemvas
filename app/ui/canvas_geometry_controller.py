from __future__ import annotations

import math

from core.history import (
    CompositeCommand,
    SetAtomPositionsCommand,
    SetRingPolygonsCommand,
    UpdateBondLengthCommand,
)
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QFontMetricsF
from PyQt6.QtWidgets import QGraphicsPolygonItem, QGraphicsTextItem

from ui.atom_coords_access import atom_coords_3d_for, current_atom_coords_3d_for
from ui.canvas_atom_graphics_state import atom_items_for
from ui.canvas_geometry_logic import (
    line_rect_clip_t as line_rect_clip_t_helper,
)
from ui.canvas_geometry_logic import (
    line_rect_intersections as line_rect_intersections_helper,
)
from ui.canvas_geometry_logic import (
    ray_rect_exit_distance as ray_rect_exit_distance_helper,
)
from ui.canvas_geometry_logic import (
    segment_intersection_t as segment_intersection_t_helper,
)
from ui.canvas_model_access import (
    atom_for_id,
    atoms_for,
    bond_for_id,
    has_atoms_for,
    rebuild_graphics_for,
    rescale_model_for,
)
from ui.canvas_rotation_state import rotation_state_for
from ui.canvas_scene_items_state import ring_items_for
from ui.renderer_style_access import (
    atom_font_for,
    bond_length_px_for,
    bond_line_width_for,
    set_bond_length_for,
)


class CanvasGeometryController:
    def __init__(self, canvas, *, hit_testing_service=None, history_service=None) -> None:
        self.canvas = canvas
        self.hit_testing_service = hit_testing_service
        self.history = history_service

    @staticmethod
    def _ring_atom_ids(ring_item) -> list[int] | None:
        ring_atom_ids = ring_item.data(2)
        return ring_atom_ids if isinstance(ring_atom_ids, list) else None

    def _ring_items_for_bond(self, bond):
        for ring_item in ring_items_for(self.canvas):
            ring_atom_ids = self._ring_atom_ids(ring_item)
            if ring_atom_ids is None:
                continue
            if bond.a in ring_atom_ids and bond.b in ring_atom_ids:
                yield ring_item, ring_atom_ids

    def _padded_label_rect(self, rect: QRectF) -> QRectF:
        pad = max(0.05, bond_line_width_for(self.canvas) * 0.05)
        return rect.adjusted(-pad, -pad, pad, pad)

    def ring_center_for_bond(self, bond) -> QPointF | None:
        for _, ring_atom_ids in self._ring_items_for_bond(bond):
            xs = []
            ys = []
            for atom_id in ring_atom_ids:
                atom = atom_for_id(self.canvas, atom_id)
                if atom is None:
                    continue
                xs.append(atom.x)
                ys.append(atom.y)
            if xs and ys:
                return QPointF(sum(xs) / len(xs), sum(ys) / len(ys))
        return None

    def ring_center_3d_for_bond(self, bond) -> tuple[float, float, float] | None:
        for _, ring_atom_ids in self._ring_items_for_bond(bond):
            coords = []
            for atom_id in ring_atom_ids:
                coord = current_atom_coords_3d_for(self.canvas, atom_id)
                if coord is not None:
                    coords.append(coord)
            if len(coords) < 3:
                return None
            sum_x = sum(c[0] for c in coords)
            sum_y = sum(c[1] for c in coords)
            sum_z = sum(c[2] for c in coords)
            count = len(coords)
            return (sum_x / count, sum_y / count, sum_z / count)
        return None

    def ring_for_bond(self, bond_id: int) -> QGraphicsPolygonItem | None:
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None:
            return None
        for ring_item, _ in self._ring_items_for_bond(bond):
            return ring_item
        return None

    def label_rect_for_atom(self, atom_id: int) -> QRectF | None:
        item = atom_items_for(self.canvas).get(atom_id)
        if item is None:
            return None
        return self._padded_label_rect(item.sceneBoundingRect())

    @staticmethod
    def visible_text_rect(item: QGraphicsTextItem) -> QRectF:
        # Prefer the item's own painted content box. For a stacked hydride
        # ("N" over "H") or any typographic label, the Qt document rect only
        # covers the one-line plain text set via setPlainText, so it under-
        # reports the vertical extent a mark (charge/radical) must clear and
        # can overlap the second line. AtomLabelItem exposes the real box via
        # export_scene_bounding_rect; plain text items fall back to the doc rect.
        content_rect = getattr(item, "export_scene_bounding_rect", None)
        if callable(content_rect):
            rect = content_rect()
            if isinstance(rect, QRectF):
                return QRectF(rect)
        return item.mapRectToScene(QGraphicsTextItem.boundingRect(item))

    def visible_label_rect_for_atom(self, atom_id: int) -> QRectF | None:
        item = atom_items_for(self.canvas).get(atom_id)
        if item is None:
            return None
        return self._padded_label_rect(self.visible_text_rect(item))

    def label_cut_radius_for_atom(self, atom_id: int) -> float | None:
        item = atom_items_for(self.canvas).get(atom_id)
        if item is None:
            return None
        # Trim bonds to the anchored element glyph only, so an "NH"/"OH" label
        # keeps a shallow cut around N/O instead of clearing the whole box.
        rect = None
        anchor_scene_rect = getattr(item, "anchor_scene_rect", None)
        if callable(anchor_scene_rect):
            rect = anchor_scene_rect()
        if rect is None:
            rect = item.sceneBoundingRect()
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return None
        corners = [
            rect.topLeft(),
            rect.topRight(),
            rect.bottomLeft(),
            rect.bottomRight(),
        ]
        max_dist = 0.0
        for corner in corners:
            max_dist = max(max_dist, math.hypot(corner.x() - atom.x, corner.y() - atom.y))
        pad = max(0.02, bond_line_width_for(self.canvas) * 0.03)
        return (max_dist + pad) * 0.6

    def line_rect_clip_t(self, p1: QPointF, p2: QPointF, rect: QRectF) -> tuple[float, float] | None:
        return line_rect_clip_t_helper(p1, p2, rect)

    def segment_intersection_t(self, p1: QPointF, p2: QPointF, q1: QPointF, q2: QPointF) -> float | None:
        return segment_intersection_t_helper(p1, p2, q1, q2)

    def ray_rect_exit_distance(self, origin: QPointF, direction: QPointF, rect: QRectF) -> float | None:
        return ray_rect_exit_distance_helper(origin, direction, rect)

    def mark_clearance_for_kind(self, kind: str) -> float:
        gap = max(0.6, bond_length_px_for(self.canvas) * 0.05)
        if kind == "radical":
            radius = max(1.2, bond_line_width_for(self.canvas) * 0.7)
            return radius + gap
        if kind in {"plus", "minus"}:
            metrics = QFontMetricsF(atom_font_for(self.canvas))
            rect = metrics.boundingRect("+" if kind == "plus" else "-")
            half_diagonal = math.hypot(rect.width(), rect.height()) * 0.5
            return max(half_diagonal, metrics.height() * 0.35) + gap
        if kind in {"circled_plus", "circled_minus"}:
            radius = max(4.0, QFontMetricsF(atom_font_for(self.canvas)).height() * 0.26)
            return radius + max(0.9, bond_line_width_for(self.canvas) * 0.65) + gap
        return gap

    def mark_target_distance_for_atom(
        self,
        atom_id: int,
        direction_x: float,
        direction_y: float,
        kind: str,
    ) -> float:
        atom = atom_for_id(self.canvas, atom_id)
        label_rect = self.visible_label_rect_for_atom(atom_id)
        if atom is None or label_rect is None:
            return 0.0
        clearance = self.mark_clearance_for_kind(kind)
        expanded_rect = label_rect.adjusted(-clearance, -clearance, clearance, clearance)
        distance = ray_rect_exit_distance_helper(
            QPointF(atom.x, atom.y),
            QPointF(direction_x, direction_y),
            expanded_rect,
        )
        return 0.0 if distance is None else distance

    def set_bond_length(self, length_px: float) -> None:
        old_length = bond_length_px_for(self.canvas)
        before_positions = {atom_id: (atom.x, atom.y) for atom_id, atom in atoms_for(self.canvas).items()}
        before_coords_3d = self._atom_coords_3d_for_positions(before_positions)
        rotation_state = rotation_state_for(self.canvas)
        before_projection_center_3d = rotation_state.projection_center_3d
        before_projection_anchor_2d = rotation_state.projection_anchor_2d
        before_ring_polygons = [
            [(point.x(), point.y()) for point in ring_item.polygon()]
            for ring_item in ring_items_for(self.canvas)
        ]
        set_bond_length_for(self.canvas, length_px)
        if old_length <= 0 or not has_atoms_for(self.canvas):
            return
        scale = length_px / old_length
        if scale == 1.0:
            return
        if self.hit_testing_service is None:
            raise RuntimeError("CanvasGeometryController.set_bond_length requires hit_testing_service")
        center_x, center_y = self._model_center()
        rescale_model_for(self.canvas, scale)
        self._rescale_perspective_state(scale, center_x, center_y)
        self.hit_testing_service.mark_spatial_index_dirty()
        rebuild_graphics_for(self.canvas)
        after_positions = {atom_id: (atom.x, atom.y) for atom_id, atom in atoms_for(self.canvas).items()}
        after_coords_3d = self._atom_coords_3d_for_positions(after_positions)
        after_projection_center_3d = rotation_state.projection_center_3d
        after_projection_anchor_2d = rotation_state.projection_anchor_2d
        after_ring_polygons = [
            [(point.x(), point.y()) for point in ring_item.polygon()]
            for ring_item in ring_items_for(self.canvas)
        ]
        commands = [
            UpdateBondLengthCommand(before_length=old_length, after_length=length_px),
            SetAtomPositionsCommand(
                before_positions=before_positions,
                after_positions=after_positions,
                before_coords_3d=before_coords_3d or None,
                after_coords_3d=after_coords_3d or None,
                restore_projection_state=bool(
                    before_coords_3d
                    or after_coords_3d
                    or before_projection_center_3d is not None
                    or after_projection_center_3d is not None
                    or before_projection_anchor_2d is not None
                    or after_projection_anchor_2d is not None
                ),
                before_projection_center_3d=before_projection_center_3d,
                after_projection_center_3d=after_projection_center_3d,
                before_projection_anchor_2d=before_projection_anchor_2d,
                after_projection_anchor_2d=after_projection_anchor_2d,
            ),
        ]
        ring_items = ring_items_for(self.canvas)
        if ring_items:
            commands.append(
                SetRingPolygonsCommand(
                    ring_items=list(ring_items),
                    before_polygons=before_ring_polygons,
                    after_polygons=after_ring_polygons,
                )
            )
        if self.history is None:
            raise AttributeError("CanvasGeometryController requires an injected history_service")
        self.history.push(CompositeCommand(commands))

    def _atom_coords_3d_for_positions(self, positions: dict[int, tuple[float, float]]) -> dict[int, tuple[float, float, float]]:
        stored_coords = atom_coords_3d_for(self.canvas)
        return {atom_id: stored_coords[atom_id] for atom_id in positions if atom_id in stored_coords}

    def _model_center(self) -> tuple[float, float]:
        atoms = atoms_for(self.canvas)
        center_x = sum(atom.x for atom in atoms.values()) / len(atoms)
        center_y = sum(atom.y for atom in atoms.values()) / len(atoms)
        return center_x, center_y

    @staticmethod
    def _scaled_xy(x: float, y: float, scale: float, center_x: float, center_y: float) -> tuple[float, float]:
        return center_x + (x - center_x) * scale, center_y + (y - center_y) * scale

    def _rescale_perspective_state(self, scale: float, center_x: float, center_y: float) -> None:
        rotation_state = rotation_state_for(self.canvas)
        projection_center = rotation_state.projection_center_3d
        z_center = projection_center[2] if projection_center is not None else 0.0
        atom_ids = set(atoms_for(self.canvas))
        for atom_id, (x, y, z) in list(atom_coords_3d_for(self.canvas).items()):
            if atom_id not in atom_ids:
                continue
            scaled_x, scaled_y = self._scaled_xy(x, y, scale, center_x, center_y)
            atom_coords_3d_for(self.canvas)[atom_id] = (scaled_x, scaled_y, z_center + (z - z_center) * scale)
        if projection_center is not None:
            x, y, z = projection_center
            scaled_x, scaled_y = self._scaled_xy(x, y, scale, center_x, center_y)
            rotation_state.projection_center_3d = (scaled_x, scaled_y, z)
        if rotation_state.projection_anchor_2d is not None:
            x, y = rotation_state.projection_anchor_2d
            rotation_state.projection_anchor_2d = self._scaled_xy(x, y, scale, center_x, center_y)

    def line_rect_intersections(self, p1: QPointF, p2: QPointF, rect: QRectF) -> list[float]:
        return line_rect_intersections_helper(p1, p2, rect)

    def trim_line_for_labels(
        self,
        a_id: int | None,
        b_id: int | None,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> tuple[float, float]:
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length == 0:
            return 0.0, 1.0
        p1 = QPointF(x1, y1)
        p2 = QPointF(x2, y2)
        t0 = 0.0
        t1 = 1.0
        hit_start = False
        hit_end = False
        for atom_id, is_start in ((a_id, True), (b_id, False)):
            if atom_id is None:
                continue
            label_rect = self.visible_label_rect_for_atom(atom_id)
            if label_rect is not None:
                clipped = self.line_rect_clip_t(p1, p2, label_rect)
                if clipped is not None:
                    entry_t, exit_t = clipped
                    if is_start:
                        t0 = max(t0, min(1.0, exit_t))
                        hit_start = True
                    else:
                        t1 = min(t1, max(0.0, entry_t))
                        hit_end = True
                    continue
            radius = self.label_cut_radius_for_atom(atom_id)
            if radius is None:
                continue
            t_hit = min(1.0, radius / length)
            if is_start:
                t0 = max(t0, t_hit)
                hit_start = True
            else:
                t1 = min(t1, 1.0 - t_hit)
                hit_end = True
        if hit_start or hit_end:
            gap_t = (bond_line_width_for(self.canvas) * 0.02) / length
            if hit_start:
                t0 = min(1.0, t0 + gap_t)
            if hit_end:
                t1 = max(0.0, t1 - gap_t)
        min_span = 0.02
        if t1 - t0 < min_span:
            if hit_start and not hit_end:
                t0 = max(0.0, t1 - min_span)
            elif hit_end and not hit_start:
                t1 = min(1.0, t0 + min_span)
            else:
                mid = (t0 + t1) / 2.0
                t0 = max(0.0, mid - min_span / 2.0)
                t1 = min(1.0, mid + min_span / 2.0)
        return t0, t1

__all__ = ["CanvasGeometryController"]
