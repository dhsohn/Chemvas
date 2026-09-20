from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING
from weakref import WeakKeyDictionary

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QFontMetricsF,
    QPainterPath,
    QPainterPathStroker,
    QPolygonF,
    QTransform,
)
from PyQt6.QtWidgets import QGraphicsTextItem

from chemvas.features.selection import project_point_3d
from chemvas.ui.canvas_geometry_logic import line_rect_clip_t as line_rect_clip_t_helper
from chemvas.ui.canvas_geometry_logic import (
    line_rect_intersections as line_rect_intersections_helper,
)
from chemvas.ui.canvas_geometry_logic import (
    ray_rect_exit_distance as ray_rect_exit_distance_helper,
)
from chemvas.ui.canvas_geometry_logic import (
    segment_intersection_t as segment_intersection_t_helper,
)
from chemvas.ui.graphics_items import AtomLabelItem

if TYPE_CHECKING:
    from chemvas.domain.document import MoleculeModel
    from chemvas.ui.scene_render_context import SceneRenderContext


def _xy(point: QPointF) -> tuple[float, float]:
    return point.x(), point.y()


def _bounds(rect: QRectF) -> tuple[float, float, float, float]:
    return rect.left(), rect.top(), rect.right(), rect.bottom()


def _glyph_clearance_path(path: QPainterPath) -> QPainterPath:
    """Close each glyph contour's open interior, not the label's hit box.

    Convex contour envelopes keep a bond out of C/N/H openings while retaining
    curved letter silhouettes and the gaps between distinct typographic runs.
    Work in scene space so rotated/scaled labels use the same visible geometry.
    """
    result = QPainterPath()
    result.setFillRule(Qt.FillRule.WindingFill)
    scale = 64.0
    for polygon in path.toSubpathPolygons(QTransform.fromScale(scale, scale)):
        points = sorted(
            {
                (point.x() / scale, point.y() / scale)
                for point in (polygon.at(i) for i in range(polygon.size()))
            }
        )
        if len(points) < 3:
            continue
        hulls = []
        for ordered in (points, list(reversed(points))):
            half: list[tuple[float, float]] = []
            for point in ordered:
                while len(half) >= 2:
                    a, b = half[-2:]
                    cross = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (
                        point[0] - a[0]
                    )
                    if cross > 0:
                        break
                    half.pop()
                half.append(point)
            hulls.extend(half[:-1])
        result.addPolygon(QPolygonF([QPointF(x, y) for x, y in hulls]))
        result.closeSubpath()
    return result


@dataclass(frozen=True)
class _GlyphClipGeometry:
    path: QPainterPath
    stroke_width: float
    outlines: tuple[tuple[QPainterPath, tuple[QPolygonF, ...]], ...]


def _prepare_glyph_clip_geometry(
    path: QPainterPath, stroke_width: float
) -> _GlyphClipGeometry:
    original_path = path
    path = _glyph_clearance_path(path)
    gap = max(0.2, stroke_width * 0.5)
    # A disk enclosing a square cap also covers round/flat bond caps. Keep
    # the small flattening allowance separate from the visible clearance.
    radius = stroke_width / math.sqrt(2.0) + gap + 0.01
    stroker = QPainterPathStroker()
    stroker.setWidth(2.0 * radius)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    stroker.setCurveThreshold(0.001)
    # Qt's default polygonization tolerance is in device coordinates. Flatten
    # at 64x to keep scene error below the 0.01 allowance, including curves.
    scale = 64.0
    transform = QTransform.fromScale(scale, scale)
    return _GlyphClipGeometry(
        original_path,
        stroke_width,
        tuple(
            (outline, tuple(outline.toSubpathPolygons(transform)))
            for outline in (path, stroker.createStroke(path))
        ),
    )


def _glyph_line_clip_t(
    p1: QPointF,
    p2: QPointF,
    path: QPainterPath,
    stroke_width: float,
    offsets: tuple[tuple[float, float], ...] = (),
    *,
    prepared: _GlyphClipGeometry | None = None,
) -> tuple[float, float] | None:
    """First/last glyph-envelope crossings with stroke extent and an air gap.

    Inspect every contour, not just the filled interval containing the atom:
    the atom may sit in O's counter, or between separate typographic runs.
    Never terminate there and leave another piece of the label on the bond.
    """
    if prepared is None:
        prepared = _prepare_glyph_clip_geometry(path, stroke_width)
    scale = 64.0
    transform = QTransform.fromScale(scale, scale)
    start, end = transform.map(p1), transform.map(p2)
    hits = []
    length = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
    ux, uy = (p2.x() - p1.x()) / length, (p2.y() - p1.y()) / length
    along = [ux * x + uy * y for x, y in offsets] or [0.0]
    across = [-uy * x + ux * y for x, y in offsets] or [0.0]
    low, high = min(across), max(across)
    for outline, polygons in prepared.outlines:
        if outline.contains(p1):
            hits.append(0.0)
        if outline.contains(p2):
            hits.append(1.0)
        for polygon in polygons:
            if offsets:
                # Inspect the entire band occupied by parallel strokes or a
                # filled strip, including ink between (not only on) its edges.
                points = [
                    (
                        (p.x() / scale - p1.x()) * ux + (p.y() / scale - p1.y()) * uy,
                        -(p.x() / scale - p1.x()) * uy + (p.y() / scale - p1.y()) * ux,
                    )
                    for p in (polygon.at(i) for i in range(polygon.size()))
                ]
                xs = [x for x, y in points if low <= y <= high]
                for index in range(len(points) - 1):
                    x0, y0 = points[index]
                    x1, y1 = points[index + 1]
                    if abs(y1 - y0) < 1e-12:
                        continue
                    for y in (low, high):
                        ratio = (y - y0) / (y1 - y0)
                        if 0 <= ratio <= 1:
                            xs.append(x0 + ratio * (x1 - x0))
                if xs:
                    first = (min(xs) - max(along)) / length
                    last = (max(xs) - min(along)) / length
                    if first <= 1 and last >= 0:
                        hits.extend((max(0.0, first), min(1.0, last)))
                continue
            for index in range(polygon.size() - 1):
                left, right = polygon.at(index), polygon.at(index + 1)
                hit = segment_intersection_t_helper(
                    _xy(start), _xy(end), _xy(left), _xy(right)
                )
                if hit is not None:
                    hits.append(hit)
    return (min(hits), max(hits)) if hits else None


def project_point_in_scene(
    point: tuple[float, float, float],
    *,
    bond_length_px: float,
    center_3d: tuple[float, float, float] | None,
    anchor_2d: tuple[float, float] | None,
) -> tuple[float, float]:
    if center_3d is None:
        return point[0], point[1]
    return project_point_3d(
        point,
        bond_length_px=bond_length_px,
        center_3d=center_3d,
        anchor_2d=anchor_2d or (center_3d[0], center_3d[1]),
    )


def current_atom_coords_in_scene(
    atom_id: int,
    *,
    model: MoleculeModel,
    stored_coords: dict[int, tuple[float, float, float]],
    bond_length_px: float,
    center_3d: tuple[float, float, float] | None,
    anchor_2d: tuple[float, float] | None,
) -> tuple[float, float, float] | None:
    atom = model.atoms.get(atom_id)
    if atom is None:
        return None
    coords = stored_coords.get(atom_id)
    if coords is not None:
        projected_x, projected_y = project_point_in_scene(
            coords,
            bond_length_px=bond_length_px,
            center_3d=center_3d,
            anchor_2d=anchor_2d,
        )
        if math.hypot(projected_x - atom.x, projected_y - atom.y) <= max(
            1.0, bond_length_px * 0.15
        ):
            return coords
    return atom.x, atom.y, 0.0


class SceneGeometry:
    """Read-only molecular geometry shared by editing and document rendering."""

    def __init__(self, context: SceneRenderContext) -> None:
        self.context = context
        # One current geometry per live label, never a document/revision cache.
        self._glyph_clip_geometry: WeakKeyDictionary[
            AtomLabelItem, _GlyphClipGeometry
        ] = WeakKeyDictionary()

    def current_atom_coords_3d(self, atom_id: int) -> tuple[float, float, float] | None:
        rotation = self.context.state.rotation_state
        return current_atom_coords_in_scene(
            atom_id,
            model=self.context.model,
            stored_coords=self.context.state.atom_coords_3d_state.atom_coords_3d,
            bond_length_px=self.context.renderer.style.bond_length_px,
            center_3d=rotation.projection_center_3d,
            anchor_2d=rotation.projection_anchor_2d,
        )

    def project_point_3d(
        self, point: tuple[float, float, float]
    ) -> tuple[float, float]:
        rotation = self.context.state.rotation_state
        return project_point_in_scene(
            point,
            bond_length_px=self.context.renderer.style.bond_length_px,
            center_3d=rotation.projection_center_3d,
            anchor_2d=rotation.projection_anchor_2d,
        )

    def bond_offset_unit_3d(self, a_id: int, b_id: int, target=None):
        atom_a = self.context.model.atoms.get(a_id)
        atom_b = self.context.model.atoms.get(b_id)
        if atom_a is None or atom_b is None:
            return None
        dx, dy = atom_b.x - atom_a.x, atom_b.y - atom_a.y
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return None
        nx, ny = -dy / length, dx / length
        if target is not None:
            tx, ty = self.project_point_3d(target)
            if (
                nx * (tx - (atom_a.x + atom_b.x) * 0.5)
                + ny * (ty - (atom_a.y + atom_b.y) * 0.5)
                < 0
            ):
                nx, ny = -nx, -ny
        return nx, ny

    @staticmethod
    def line_normal(x1: float, y1: float, x2: float, y2: float, target=None):
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return 0.0, 0.0
        nx, ny = -dy / length, dx / length
        if (
            target is not None
            and nx * (target.x() - (x1 + x2) * 0.5)
            + ny * (target.y() - (y1 + y2) * 0.5)
            < 0
        ):
            return -nx, -ny
        return nx, ny

    def _clip_label_line(self, item, p1, p2, width, offsets):
        transform = item.sceneTransform()
        if not transform.isAffine():
            return _glyph_line_clip_t(
                p1, p2, item.mapToScene(item.glyph_path()), width, offsets
            )
        linear = QTransform(
            transform.m11(), transform.m12(), transform.m21(), transform.m22(), 0, 0
        )
        path = linear.map(item.glyph_path())
        prepared = self._glyph_clip_geometry.get(item)
        if prepared is None or prepared.path != path or prepared.stroke_width != width:
            prepared = _prepare_glyph_clip_geometry(path, width)
            self._glyph_clip_geometry[item] = prepared
        origin = QPointF(transform.dx(), transform.dy())
        return _glyph_line_clip_t(
            p1 - origin, p2 - origin, path, width, offsets, prepared=prepared
        )

    @staticmethod
    def _ring_atom_ids(ring_item) -> list[int] | None:
        ring_atom_ids = ring_item.data(2)
        return ring_atom_ids if isinstance(ring_atom_ids, list) else None

    def _ring_items_for_bond(self, bond):
        for ring_item in self.context.state.scene_items_state.ring_items:
            ring_atom_ids = self._ring_atom_ids(ring_item)
            if ring_atom_ids is None:
                continue
            if bond.a in ring_atom_ids and bond.b in ring_atom_ids:
                yield ring_item, ring_atom_ids

    def _padded_label_rect(self, rect: QRectF) -> QRectF:
        pad = max(0.05, self.context.renderer.style.bond_line_width * 0.05)
        return rect.adjusted(-pad, -pad, pad, pad)

    def ring_center_for_bond(self, bond) -> QPointF | None:
        for _, ring_atom_ids in self._ring_items_for_bond(bond):
            xs = []
            ys = []
            for atom_id in ring_atom_ids:
                atom = self.context.model.atoms.get(atom_id)
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
                coord = self.current_atom_coords_3d(atom_id)
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

    def label_rect_for_atom(self, atom_id: int) -> QRectF | None:
        item = self.context.state.atom_graphics_state.atom_items.get(atom_id)
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
        # layout_scene_bounding_rect; output-only glyph bounds must not change
        # existing mark placement. Plain text items retain the document rect.
        if isinstance(item, AtomLabelItem):
            return item.layout_scene_bounding_rect()
        return item.mapRectToScene(QGraphicsTextItem.boundingRect(item))

    def visible_label_rect_for_atom(self, atom_id: int) -> QRectF | None:
        item = self.context.state.atom_graphics_state.atom_items.get(atom_id)
        if item is None:
            return None
        return self._padded_label_rect(self.visible_text_rect(item))

    def label_cut_radius_for_atom(self, atom_id: int) -> float | None:
        item = self.context.state.atom_graphics_state.atom_items.get(atom_id)
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
        atom = self.context.model.atoms.get(atom_id)
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
            max_dist = max(
                max_dist, math.hypot(corner.x() - atom.x, corner.y() - atom.y)
            )
        pad = max(0.02, self.context.renderer.style.bond_line_width * 0.03)
        return (max_dist + pad) * 0.6

    def line_rect_clip_t(
        self, p1: QPointF, p2: QPointF, rect: QRectF
    ) -> tuple[float, float] | None:
        return line_rect_clip_t_helper(_xy(p1), _xy(p2), _bounds(rect))

    def segment_intersection_t(
        self, p1: QPointF, p2: QPointF, q1: QPointF, q2: QPointF
    ) -> float | None:
        return segment_intersection_t_helper(_xy(p1), _xy(p2), _xy(q1), _xy(q2))

    def ray_rect_exit_distance(
        self, origin: QPointF, direction: QPointF, rect: QRectF
    ) -> float | None:
        return ray_rect_exit_distance_helper(_xy(origin), _xy(direction), _bounds(rect))

    def mark_clearance_for_kind(self, kind: str) -> float:
        gap = max(0.6, self.context.renderer.style.bond_length_px * 0.05)
        if kind == "radical":
            radius = max(1.2, self.context.renderer.style.bond_line_width * 0.7)
            return radius + gap
        if kind in {"plus", "minus"}:
            metrics = QFontMetricsF(self.context.renderer.atom_font())
            rect = metrics.boundingRect("+" if kind == "plus" else "-")
            half_diagonal = math.hypot(rect.width(), rect.height()) * 0.5
            return max(half_diagonal, metrics.height() * 0.35) + gap
        if kind in {"circled_plus", "circled_minus"}:
            radius = max(
                4.0, QFontMetricsF(self.context.renderer.atom_font()).height() * 0.26
            )
            return (
                radius
                + max(0.9, self.context.renderer.style.bond_line_width * 0.65)
                + gap
            )
        return gap

    def mark_target_distance_for_atom(
        self,
        atom_id: int,
        direction_x: float,
        direction_y: float,
        kind: str,
    ) -> float:
        atom = self.context.model.atoms.get(atom_id)
        label_rect = self.visible_label_rect_for_atom(atom_id)
        if atom is None or label_rect is None:
            return 0.0
        clearance = self.mark_clearance_for_kind(kind)
        expanded_rect = label_rect.adjusted(
            -clearance, -clearance, clearance, clearance
        )
        distance = ray_rect_exit_distance_helper(
            (atom.x, atom.y),
            (direction_x, direction_y),
            _bounds(expanded_rect),
        )
        return 0.0 if distance is None else distance

    def mark_offset_from_click(
        self, atom_id: int, click_pos: QPointF, *, kind: str
    ) -> QPointF:
        atom = self.context.model.atoms.get(atom_id)
        if atom is None:
            return QPointF(0.0, 0.0)
        dx = click_pos.x() - atom.x
        dy = click_pos.y() - atom.y
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            dx, dy = 1.0, -1.0
            length = math.hypot(dx, dy)
        direction_x, direction_y = dx / length, dy / length
        target = self.context.renderer.style.bond_length_px * 0.2
        label_target = self.mark_target_distance_for_atom(
            atom_id, direction_x, direction_y, kind
        )
        if label_target > target:
            target += (label_target - target) * 0.25
        return QPointF(direction_x * target, direction_y * target)

    def line_rect_intersections(
        self, p1: QPointF, p2: QPointF, rect: QRectF
    ) -> list[float]:
        return line_rect_intersections_helper(_xy(p1), _xy(p2), _bounds(rect))

    def trim_line_for_labels(
        self,
        a_id: int | None,
        b_id: int | None,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        offsets: tuple[tuple[float, float], ...] = (),
        *,
        stroke_width: float | None = None,
    ) -> tuple[float, float]:
        """Trim the supplied scene-space segment to label ink.

        ``stroke_width`` is the painted width/envelope, not the hit width;
        omitted it uses the standard bond pen. Pass actual offset coordinates
        for parallel strokes. Equal parameters mean no clear span remains and
        callers must not paint it. Non-AtomLabelItem fallbacks stay unchanged.
        """
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
        glyph_hit = False
        for atom_id, is_start in ((a_id, True), (b_id, False)):
            if atom_id is None:
                continue
            item = self.context.state.atom_graphics_state.atom_items.get(atom_id)
            if isinstance(item, AtomLabelItem):
                width = (
                    self.context.renderer.bond_line_width()
                    if stroke_width is None
                    else stroke_width
                )
                clipped = self._clip_label_line(
                    item,
                    p1,
                    p2,
                    max(0.0, float(width)),
                    offsets,
                )
                if clipped is not None:
                    glyph_hit = True
                    entry_t, exit_t = clipped
                    if is_start:
                        t0 = max(t0, exit_t)
                    else:
                        t1 = min(t1, entry_t)
                # Empty glyphs and rays that miss their envelopes need no hit
                # rectangle/radius fallback. Picking must not move visible bonds.
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
            gap_t = (self.context.renderer.style.bond_line_width * 0.02) / length
            if hit_start:
                t0 = min(1.0, t0 + gap_t)
            if hit_end:
                t1 = max(0.0, t1 - gap_t)
        if glyph_hit:
            # A forced minimum span would put ink back inside a counter or
            # overlapping labels. Leave suppression to the painting caller.
            return t0, max(t0, t1)
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


__all__ = ["SceneGeometry", "current_atom_coords_in_scene", "project_point_in_scene"]
