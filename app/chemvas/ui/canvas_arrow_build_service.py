from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen

from chemvas.domain.document import ARC_KIND_SWEEPS, VALID_ARC_KINDS, VALID_LINE_KINDS
from chemvas.features.annotations import arrow_label_html
from chemvas.features.rendering import arc_midpoint, arc_points, wavy_line_points
from chemvas.features.selection import HANDLE_ACCENT_COLOR, default_curved_control
from chemvas.ui.canvas_text_style_state import text_style_state_for
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.endpoint_snap_access import (
    SNAP_MARK_SCREEN_PX,
    scene_length_for_screen_px,
    snapped_points_among_for,
)
from chemvas.ui.graphics_items import (
    ArrowLabelItem,
    NoSelectEllipseItem,
    NoSelectPathItem,
)
from chemvas.ui.renderer_style_access import (
    bold_bond_pen_for,
    bond_length_px_for,
    bond_pen_for,
    bond_spacing_px_for,
    renderer_bond_spacing_for,
)
from chemvas.ui.scene_item_access import add_item_to_canvas_scene

if TYPE_CHECKING:
    from collections.abc import Mapping

# Role of the child text items that carry an arrow's labels. Hit testing maps
# the role back to the parent arrow, and export collects it so the label
# widens the figure bounds.
ARROW_LABEL_ROLE = "arrow_label"
# Role of the ring drawn on a preview end that has taken an existing
# endpoint. It lives on the preview, so it disappears with it.
SNAP_MARK_ROLE = "snap_mark"


class CanvasArrowBuildService:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    @property
    def settings(self):
        return tool_settings_state_for(self.canvas)

    def preview_arrow(self, start: QPointF, end: QPointF, kind: str):
        item = self.build_arrow_item(start, end, kind)
        return add_item_to_canvas_scene(self.canvas, item)

    def build_snap_mark(self, point: QPointF):
        """A ring at ``point``, in the handle accent rather than drawing ink."""
        radius = scene_length_for_screen_px(self.canvas, SNAP_MARK_SCREEN_PX) / 2.0
        mark = NoSelectEllipseItem(
            point.x() - radius, point.y() - radius, radius * 2, radius * 2
        )
        pen = QPen(QColor(HANDLE_ACCENT_COLOR))
        pen.setWidthF(1.6)
        pen.setCosmetic(True)
        mark.setPen(pen)
        mark.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        mark.setData(0, SNAP_MARK_ROLE)
        return mark

    def mark_snapped_points(self, item, points) -> None:
        """Ring each of ``points`` that has taken an existing endpoint.

        ``item`` is the preview, which is added to the scene without being
        registered as an arrow, so it is never one of the candidates and
        there is nothing to exclude.
        """
        for point in snapped_points_among_for(self.canvas, points):
            self.build_snap_mark(point).setParentItem(item)

    def build_arrow_item(self, start: QPointF, end: QPointF, kind: str):
        if kind in VALID_LINE_KINDS:
            return self.build_line_item(start, end, kind)
        if kind in VALID_ARC_KINDS:
            return self.build_arc_arrow(start, end, kind)
        if kind == "equilibrium":
            return self.build_equilibrium_item(start, end)
        if kind == "equilibrium_forward":
            return self.build_equilibrium_item(start, end, favored="forward")
        if kind == "equilibrium_reverse":
            return self.build_equilibrium_item(start, end, favored="reverse")
        if kind == "resonance":
            return self.build_double_head_arrow(start, end)
        if kind == "curved_single":
            return self.build_curved_arrow(start, end, double=False)
        if kind == "curved_double":
            return self.build_curved_arrow(start, end, double=True)
        if kind == "inhibit":
            return self.build_inhibition_arrow(start, end)
        if kind == "dotted":
            return self.build_dotted_arrow(start, end)
        return self.build_single_head_arrow(start, end)

    def build_single_head_arrow(self, start: QPointF, end: QPointF):
        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        self.add_arrow_head(path, start, end, double=False)
        item = NoSelectPathItem(path)
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    def build_double_head_arrow(self, start: QPointF, end: QPointF):
        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        self.add_arrow_head(path, start, end, double=False)
        self.add_arrow_head(path, end, start, double=False)
        item = NoSelectPathItem(path)
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    def build_dotted_arrow(self, start: QPointF, end: QPointF):
        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        self.add_arrow_head(path, start, end, double=False)
        item = NoSelectPathItem(path)
        item.setPen(self.arrow_pen(dotted=True))
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    def build_arc_arrow(self, start: QPointF, end: QPointF, kind: str):
        sweep_degrees, bulge_left = ARC_KIND_SWEEPS[kind]
        points = arc_points(
            (start.x(), start.y()),
            (end.x(), end.y()),
            sweep_degrees=sweep_degrees,
            bulge_left=bulge_left,
        )
        path = QPainterPath()
        path.moveTo(*points[0])
        for x, y in points[1:]:
            path.lineTo(x, y)
        # The head follows the arc's final tangent, not the chord.
        self.add_arrow_head(path, QPointF(*points[-2]), end, double=False)
        item = NoSelectPathItem(path)
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    def build_line_item(self, start: QPointF, end: QPointF, kind: str):
        path = QPainterPath()
        if kind == "line_wavy":
            # One half-wave per bond spacing keeps the wave in step with the
            # ACS bond metrics, so it scales with the document like a bond.
            spacing = renderer_bond_spacing_for(self.canvas)
            points = wavy_line_points(
                (start.x(), start.y()),
                (end.x(), end.y()),
                half_wavelength=spacing,
                amplitude=spacing * 0.5,
            )
            path.moveTo(*points[0])
            for x, y in points[1:]:
                path.lineTo(x, y)
        else:
            path.moveTo(start)
            path.lineTo(end)
        item = NoSelectPathItem(path)
        if kind == "line_bold":
            item.setPen(bold_bond_pen_for(self.canvas))
        else:
            item.setPen(self.arrow_pen(dotted=kind == "line_dashed"))
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    def build_curved_arrow(self, start: QPointF, end: QPointF, double: bool):
        control = default_curved_control(start, end)
        item = NoSelectPathItem(
            self.build_curved_arrow_path(start, end, control, double)
        )
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(
            2, {"start": start, "end": end, "control": control, "double": double}
        )
        return item

    def build_curved_arrow_path(
        self, start: QPointF, end: QPointF, control: QPointF, double: bool
    ) -> QPainterPath:
        """The same quadratic path and heads for creation and later edits."""
        path = QPainterPath()
        path.moveTo(start)
        path.quadTo(control, end)
        if double:
            self.add_arrow_head(path, control, end, double=False)
            self.add_arrow_head(path, control, start, double=False)
        else:
            self.add_arrow_head(path, control, end, double=False)
        return path

    def build_inhibition_arrow(self, start: QPointF, end: QPointF):
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        bar = bond_length_px_for(self.canvas) * 0.2

        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        bar_start = QPointF(end.x() - nx * bar, end.y() - ny * bar)
        bar_end = QPointF(end.x() + nx * bar, end.y() + ny * bar)
        path.moveTo(bar_start)
        path.lineTo(bar_end)
        item = NoSelectPathItem(path)
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    def build_equilibrium_item(
        self, start: QPointF, end: QPointF, favored: str | None = None
    ):
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        offset = bond_spacing_px_for(self.canvas) * 1.5
        forward_start = QPointF(start.x() - nx * offset, start.y() - ny * offset)
        forward_end = QPointF(end.x() - nx * offset, end.y() - ny * offset)
        reverse_start = QPointF(end.x() + nx * offset, end.y() + ny * offset)
        reverse_end = QPointF(start.x() + nx * offset, start.y() + ny * offset)
        # A favored direction keeps that harpoon full length and shortens the
        # other one to half, centred on the arrow, the way ChemDraw draws it.
        if favored == "forward":
            reverse_start, reverse_end = self._centered_half(reverse_start, reverse_end)
        elif favored == "reverse":
            forward_start, forward_end = self._centered_half(forward_start, forward_end)

        path = QPainterPath()
        self.add_harpoon(path, forward_start, forward_end)
        self.add_harpoon(path, reverse_start, reverse_end)

        item = NoSelectPathItem(path)
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    @staticmethod
    def _centered_half(start: QPointF, end: QPointF) -> tuple[QPointF, QPointF]:
        mid_x = (start.x() + end.x()) * 0.5
        mid_y = (start.y() + end.y()) * 0.5
        return (
            QPointF(
                mid_x + (start.x() - mid_x) * 0.5, mid_y + (start.y() - mid_y) * 0.5
            ),
            QPointF(mid_x + (end.x() - mid_x) * 0.5, mid_y + (end.y() - mid_y) * 0.5),
        )

    def apply_arrow_labels(self, item, labels: Mapping[str, str] | None) -> None:
        """Replace the label children of ``item`` from ``labels``.

        Positions come from the arrow's scene-coordinate ``start``/``end``
        (and ``control`` for a curved arrow) already stored in ``data(2)``,
        so callers set that data first. Children are parented to the arrow
        and therefore follow every later move.
        """
        for child in list(item.childItems()):
            if child.data(0) == ARROW_LABEL_ROLE:
                child.setParentItem(None)
                scene = child.scene()
                if scene is not None:
                    scene.removeItem(child)
        if not labels:
            return
        data = item.data(2) or {}
        start = data.get("start")
        end = data.get("end")
        if not isinstance(start, QPointF) or not isinstance(end, QPointF):
            return
        control = data.get("control")
        kind = str(item.data(0) or "")
        if isinstance(control, QPointF):
            # Midpoint of the quadratic curve at t = 0.5.
            mid = QPointF(
                0.25 * start.x() + 0.5 * control.x() + 0.25 * end.x(),
                0.25 * start.y() + 0.5 * control.y() + 0.25 * end.y(),
            )
        elif kind in ARC_KIND_SWEEPS:
            sweep_degrees, bulge_left = ARC_KIND_SWEEPS[kind]
            mid = QPointF(
                *arc_midpoint(
                    (start.x(), start.y()),
                    (end.x(), end.y()),
                    sweep_degrees=sweep_degrees,
                    bulge_left=bulge_left,
                )
            )
        else:
            mid = QPointF((start.x() + end.x()) * 0.5, (start.y() + end.y()) * 0.5)
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        # "Above" is the side toward smaller y whichever way the arrow was
        # drawn; a vertical arrow puts "above" on its left.
        if ny > 0.0 or (ny == 0.0 and nx > 0.0):
            nx, ny = -nx, -ny
        style = text_style_state_for(self.canvas)
        font = QFont(style.text_font_family, style.text_font_size)
        font.setWeight(style.text_font_weight)
        font.setItalic(style.text_italic)
        # Measure how far the arrow's own strokes (harpoons, barbs) reach
        # from the axis along the normal, so the label clears them at any
        # bond length; a curved arrow's or arc's chord ends are not part of
        # that, since their labels sit at the curve midpoint instead.
        path = item.path()
        arrow_extent = 0.0
        if not isinstance(control, QPointF) and kind not in ARC_KIND_SWEEPS:
            for index in range(path.elementCount()):
                element = path.elementAt(index)
                offset = (element.x - mid.x()) * nx + (element.y - mid.y()) * ny
                arrow_extent = max(arrow_extent, abs(offset))
        gap = arrow_extent + bond_spacing_px_for(self.canvas)
        for side, sign in (("above", 1.0), ("below", -1.0)):
            text = labels.get(side)
            if not text:
                continue
            child = ArrowLabelItem(item)
            child.setData(0, ARROW_LABEL_ROLE)
            child.setFont(font)
            child.setDefaultTextColor(style.text_color)
            child.setHtml(arrow_label_html(text))
            rect = child.boundingRect()
            # Half of the label box projected onto the normal, so a vertical
            # arrow clears the label's width and a horizontal one its height.
            half_extent = abs(nx) * rect.width() * 0.5 + abs(ny) * rect.height() * 0.5
            distance = gap + half_extent
            center = QPointF(
                mid.x() + nx * sign * distance, mid.y() + ny * sign * distance
            )
            top_left = QPointF(
                center.x() - rect.width() * 0.5, center.y() - rect.height() * 0.5
            )
            child.setPos(item.mapFromScene(top_left))

    def add_harpoon(self, path: QPainterPath, start: QPointF, end: QPointF) -> None:
        path.moveTo(start)
        path.lineTo(end)
        self.add_arrow_head(path, start, end, double=False, half=True)

    def add_arrow_head(
        self,
        path: QPainterPath,
        start: QPointF,
        end: QPointF,
        double: bool,
        half: bool = False,
    ) -> None:
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        head_len = bond_length_px_for(self.canvas) * self.settings.arrow_head_scale
        head_angle = math.radians(25)
        offsets = [0.0]
        if double:
            offset_mag = max(1.4, self.settings.arrow_line_width * 1.2)
            offsets = [-offset_mag, offset_mag]
        for offset in offsets:
            dx = math.cos(angle + math.pi / 2) * offset
            dy = math.sin(angle + math.pi / 2) * offset
            tip = QPointF(end.x() + dx, end.y() + dy) if double else end
            right = QPointF(
                tip.x() - head_len * math.cos(angle + head_angle),
                tip.y() - head_len * math.sin(angle + head_angle),
            )
            # A half head keeps the barb on the side the line was offset toward,
            # so an equilibrium pair carries both barbs on the outside and reads
            # as the conventional harpoon arrow rather than two full heads.
            if half:
                path.moveTo(right)
                path.lineTo(tip)
                continue
            left = QPointF(
                tip.x() - head_len * math.cos(angle - head_angle),
                tip.y() - head_len * math.sin(angle - head_angle),
            )
            path.moveTo(left)
            path.lineTo(tip)
            path.lineTo(right)

    def arrow_pen(self, dotted: bool = False):
        pen = bond_pen_for(self.canvas)
        pen.setWidthF(self.settings.arrow_line_width)
        if dotted:
            pen.setStyle(Qt.PenStyle.DashLine)
        return pen


__all__ = ["ARROW_LABEL_ROLE", "SNAP_MARK_ROLE", "CanvasArrowBuildService"]
